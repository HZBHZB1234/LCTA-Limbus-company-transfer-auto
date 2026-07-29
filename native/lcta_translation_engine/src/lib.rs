mod config;
mod diagnostics;
mod document;
mod engine;
mod error;
mod event;
mod matcher;
mod provider;
mod response;
mod rules;

use config::{ProviderConfig, RunConfig};
use crossbeam_channel::{bounded, Receiver};
use diagnostics::ProviderTrace;
use provider::{Provider, TranslationRequest, TranslationTask};
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use serde::Deserialize;
use serde_json::{json, Value};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Condvar, Mutex};
use std::thread;

struct JobState {
    events: Mutex<Receiver<String>>,
    result: Mutex<Option<std::result::Result<String, String>>>,
    completed: Condvar,
    finished: AtomicBool,
    cancelled: Arc<AtomicBool>,
}

#[pyclass]
struct TranslationJob {
    state: Arc<JobState>,
}

#[pymethods]
impl TranslationJob {
    fn is_finished(&self) -> bool {
        self.state.finished.load(Ordering::Acquire)
    }
    fn cancel(&self) {
        self.state.cancelled.store(true, Ordering::Release);
    }

    #[pyo3(signature = (max_items=100))]
    fn drain_events(&self, max_items: usize) -> Vec<String> {
        let receiver = self.state.events.lock().expect("event receiver poisoned");
        receiver.try_iter().take(max_items).collect()
    }

    fn wait(&self, py: Python<'_>) -> PyResult<String> {
        py.allow_threads(|| {
            let mut result = self.state.result.lock().expect("job result poisoned");
            while result.is_none() {
                result = self
                    .state
                    .completed
                    .wait(result)
                    .expect("job condition variable poisoned");
            }
            match result.as_ref().expect("result checked above") {
                Ok(summary) => Ok(summary.clone()),
                Err(error) => Err(PyRuntimeError::new_err(error.clone())),
            }
        })
    }
}

#[pyfunction]
fn start_translation(config_json: &str) -> PyResult<TranslationJob> {
    let config: RunConfig = serde_json::from_str(config_json)
        .map_err(|error| PyValueError::new_err(error.to_string()))?;
    let (event_sender, event_receiver) = bounded(4096);
    let cancelled = Arc::new(AtomicBool::new(false));
    let state = Arc::new(JobState {
        events: Mutex::new(event_receiver),
        result: Mutex::new(None),
        completed: Condvar::new(),
        finished: AtomicBool::new(false),
        cancelled: cancelled.clone(),
    });
    let worker_state = state.clone();
    thread::Builder::new()
        .name("lcta-translation-engine".to_string())
        .spawn(move || {
            let result = tokio::runtime::Builder::new_multi_thread()
                .enable_all()
                .thread_name("lcta-tokio")
                .build()
                .map_err(|error| error.to_string())
                .and_then(|runtime| {
                    runtime
                        .block_on(engine::run(config, event_sender, cancelled))
                        .and_then(|summary| serde_json::to_string(&summary).map_err(Into::into))
                        .map_err(|error| error.to_string())
                });
            *worker_state.result.lock().expect("job result poisoned") = Some(result);
            worker_state.finished.store(true, Ordering::Release);
            worker_state.completed.notify_all();
        })
        .map_err(|error| PyRuntimeError::new_err(error.to_string()))?;
    Ok(TranslationJob { state })
}

#[derive(Debug, Deserialize)]
struct ProviderTestConfig {
    provider: ProviderConfig,
}

#[pyfunction]
fn test_provider(py: Python<'_>, config_json: &str) -> PyResult<String> {
    let config: ProviderTestConfig = serde_json::from_str(config_json)
        .map_err(|error| PyValueError::new_err(error.to_string()))?;
    py.allow_threads(|| {
        let runtime = tokio::runtime::Builder::new_multi_thread()
            .worker_threads(2)
            .enable_all()
            .thread_name("lcta-provider-test")
            .build()
            .map_err(|error| PyRuntimeError::new_err(error.to_string()))?;
        runtime.block_on(async move {
            let (events, _) = bounded(32);
            let provider = Provider::new(config.provider, 3, events)
                .map_err(|error| PyRuntimeError::new_err(error.to_string()))?;
            let user_prompt = json!({
                "text_blocks": [
                    {"id": 1, "kr": "안녕"},
                    {"id": 2, "kr": "Hello"},
                    {"id": 3, "kr": "こんにちは"}
                ]
            })
            .to_string();
            let raw = provider
                .translate(
                    TranslationRequest {
                        file: "<provider-test>".to_string(),
                        task: TranslationTask::Translate,
                        system_prompt:
                            "将每个输入条目翻译为简体中文。不得改变 id，只返回 translations JSON。"
                                .to_string(),
                        user_prompt,
                    },
                    &mut ProviderTrace::default(),
                )
                .await
                .map_err(|error| PyRuntimeError::new_err(error.to_string()))?;
            let trimmed = raw.trim();
            let normalized = if trimmed.starts_with("```") {
                trimmed
                    .trim_start_matches("```json")
                    .trim_start_matches("```")
                    .trim_end_matches("```")
                    .trim()
            } else {
                trimmed
            };
            let response: Value = serde_json::from_str(normalized)
                .map_err(|error| PyRuntimeError::new_err(error.to_string()))?;
            let translations = response
                .get("translations")
                .and_then(Value::as_array)
                .or_else(|| response.as_array())
                .ok_or_else(|| PyRuntimeError::new_err("API 测试响应缺少 translations"))?;
            let mut by_id = std::collections::HashMap::new();
            for item in translations {
                if let (Some(id), Some(translation)) = (
                    item.get("id").and_then(Value::as_u64),
                    item.get("translation").and_then(Value::as_str),
                ) {
                    by_id.insert(id, translation.to_string());
                }
            }
            serde_json::to_string(&json!({
                "kr": by_id.get(&1).cloned().unwrap_or_default(),
                "en": by_id.get(&2).cloned().unwrap_or_default(),
                "jp": by_id.get(&3).cloned().unwrap_or_default(),
            }))
            .map_err(|error| PyRuntimeError::new_err(error.to_string()))
        })
    })
}

#[pymodule]
fn _lcta_native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<TranslationJob>()?;
    module.add_function(wrap_pyfunction!(start_translation, module)?)?;
    module.add_function(wrap_pyfunction!(test_provider, module)?)?;
    Ok(())
}
