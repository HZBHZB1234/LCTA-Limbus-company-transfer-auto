use crate::config::{OpenAiConfig, ProviderConfig};
use crate::diagnostics::{rounded_seconds, sanitize_text, HttpAttemptRecord, ProviderTrace};
use crate::error::{EngineError, Result};
use crate::event::{emit, EngineEvent};
use crossbeam_channel::Sender;
use reqwest::header::{AUTHORIZATION, CONTENT_TYPE};
use serde_json::{json, Value};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::Semaphore;

#[derive(Debug, Clone)]
pub struct TranslationRequest {
    pub file: String,
    pub task: TranslationTask,
    pub system_prompt: String,
    pub user_prompt: String,
}

#[derive(Debug, Clone, Copy)]
pub enum TranslationTask {
    Translate,
    SelfCheck,
}

#[derive(Clone)]
pub struct Provider {
    kind: ProviderKind,
    limiter: Arc<Semaphore>,
    events: Sender<String>,
}

#[derive(Clone)]
enum ProviderKind {
    OpenAi {
        config: OpenAiConfig,
        client: reqwest::Client,
        endpoint: String,
    },
    Null,
}

impl Provider {
    pub fn new(config: ProviderConfig, concurrency: usize, events: Sender<String>) -> Result<Self> {
        let kind = match config {
            ProviderConfig::OpenAiCompatible(config) => {
                let endpoint = if config
                    .base_url
                    .trim_end_matches('/')
                    .ends_with("chat/completions")
                {
                    config.base_url.clone()
                } else {
                    format!("{}/chat/completions", config.base_url.trim_end_matches('/'))
                };
                let client = reqwest::Client::builder()
                    .pool_max_idle_per_host(concurrency.max(1))
                    .tcp_keepalive(Duration::from_secs(60))
                    .http2_adaptive_window(true)
                    .build()?;
                ProviderKind::OpenAi {
                    config,
                    client,
                    endpoint,
                }
            }
            ProviderConfig::Null => ProviderKind::Null,
        };
        Ok(Self {
            kind,
            limiter: Arc::new(Semaphore::new(concurrency.max(1))),
            events,
        })
    }

    pub async fn translate(
        &self,
        request: TranslationRequest,
        trace: &mut ProviderTrace,
    ) -> Result<String> {
        let queue_started = Instant::now();
        let _permit = self
            .limiter
            .acquire()
            .await
            .map_err(|_| EngineError::Cancelled)?;
        trace.queue_wait_seconds = rounded_seconds(queue_started.elapsed());
        match &self.kind {
            ProviderKind::Null => {
                let value: Value = serde_json::from_str(&request.user_prompt)?;
                let translations = value
                    .get("text_blocks")
                    .and_then(Value::as_array)
                    .into_iter()
                    .flatten()
                    .map(|item| {
                        let translation = match request.task {
                            TranslationTask::Translate => {
                                item.get("kr").and_then(Value::as_str).unwrap_or_default()
                            }
                            TranslationTask::SelfCheck => item
                                .get("translation")
                                .and_then(Value::as_str)
                                .unwrap_or_default(),
                        };
                        json!({
                            "id": item.get("id").and_then(Value::as_u64).unwrap_or_default(),
                            "translation": translation,
                        })
                    })
                    .collect::<Vec<_>>();
                Ok(json!({ "translations": translations }).to_string())
            }
            ProviderKind::OpenAi {
                config,
                client,
                endpoint,
            } => {
                let mut body = json!({
                    "model": config.model,
                    "temperature": config.temperature,
                    "messages": [
                        {"role": "system", "content": request.system_prompt},
                        {"role": "user", "content": request.user_prompt}
                    ],
                    "response_format": {"type": "json_object"}
                });
                if let Some(max_tokens) = config.max_tokens {
                    body["max_tokens"] = json!(max_tokens);
                }
                if let Some(object) = body.as_object_mut() {
                    for (key, value) in &config.extra_body {
                        object.insert(key.clone(), value.clone());
                    }
                }

                let mut last_error = None;
                for attempt in 0..=config.max_retries {
                    let attempt_started = Instant::now();
                    let response = client
                        .post(endpoint)
                        .header(CONTENT_TYPE, "application/json")
                        .header(AUTHORIZATION, format!("Bearer {}", config.api_key))
                        .timeout(Duration::from_secs(config.timeout_seconds))
                        .json(&body)
                        .send()
                        .await;
                    match response {
                        Ok(response) => {
                            let status = response.status();
                            let response_text = match response.text().await {
                                Ok(text) => text,
                                Err(error) => {
                                    trace.http_attempts.push(HttpAttemptRecord {
                                        attempt: attempt + 1,
                                        status_code: Some(status.as_u16()),
                                        elapsed_seconds: rounded_seconds(attempt_started.elapsed()),
                                        retryable: false,
                                        retry_delay_ms: None,
                                        error: Some(sanitize_text(&error.to_string())),
                                        response_body: None,
                                    });
                                    return Err(EngineError::Network(error));
                                }
                            };
                            if status.is_success() {
                                trace.http_attempts.push(HttpAttemptRecord {
                                    attempt: attempt + 1,
                                    status_code: Some(status.as_u16()),
                                    elapsed_seconds: rounded_seconds(attempt_started.elapsed()),
                                    retryable: false,
                                    retry_delay_ms: None,
                                    error: None,
                                    response_body: Some(sanitize_text(&response_text)),
                                });
                                let value: Value = serde_json::from_str(&response_text)?;
                                return value
                                    .pointer("/choices/0/message/content")
                                    .and_then(Value::as_str)
                                    .map(str::to_string)
                                    .ok_or_else(|| {
                                        EngineError::InvalidResponse(
                                            "响应缺少 choices[0].message.content".to_string(),
                                        )
                                    });
                            }
                            let retryable = status.as_u16() == 429 || status.is_server_error();
                            let retry_delay_ms = (retryable && attempt < config.max_retries)
                                .then(|| 500_u64.saturating_mul(2_u64.pow(attempt.min(5) as u32)));
                            trace.http_attempts.push(HttpAttemptRecord {
                                attempt: attempt + 1,
                                status_code: Some(status.as_u16()),
                                elapsed_seconds: rounded_seconds(attempt_started.elapsed()),
                                retryable,
                                retry_delay_ms,
                                error: Some(format!("HTTP {}", status.as_u16())),
                                response_body: Some(sanitize_text(&response_text)),
                            });
                            if !retryable || attempt == config.max_retries {
                                return Err(EngineError::Api {
                                    status: status.as_u16(),
                                    body: sanitize_text(&response_text),
                                });
                            }
                            last_error = Some(format!("HTTP {}", status.as_u16()));
                        }
                        Err(error) => {
                            let retryable = attempt < config.max_retries;
                            let retry_delay_ms = retryable
                                .then(|| 500_u64.saturating_mul(2_u64.pow(attempt.min(5) as u32)));
                            trace.http_attempts.push(HttpAttemptRecord {
                                attempt: attempt + 1,
                                status_code: error.status().map(|status| status.as_u16()),
                                elapsed_seconds: rounded_seconds(attempt_started.elapsed()),
                                retryable,
                                retry_delay_ms,
                                error: Some(sanitize_text(&error.to_string())),
                                response_body: None,
                            });
                            if attempt == config.max_retries {
                                return Err(EngineError::Network(error));
                            }
                            last_error = Some(error.to_string());
                        }
                    }
                    let delay_ms = trace
                        .http_attempts
                        .last()
                        .and_then(|entry| entry.retry_delay_ms)
                        .unwrap_or_else(|| {
                            500_u64.saturating_mul(2_u64.pow(attempt.min(5) as u32))
                        });
                    let reason = last_error.as_deref().unwrap_or("temporary error");
                    emit(
                        &self.events,
                        EngineEvent::RequestRetry {
                            file: &request.file,
                            attempt: attempt + 2,
                            delay_ms,
                            reason,
                        },
                    );
                    tokio::time::sleep(Duration::from_millis(delay_ms)).await;
                }
                Err(EngineError::InvalidResponse(
                    last_error.unwrap_or_else(|| "未知请求错误".to_string()),
                ))
            }
        }
    }
}
