use crate::error::EngineError;
use serde::Serialize;
use serde_json::{json, Value};
use std::collections::BTreeSet;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};
use tokio::io::AsyncWriteExt;
use tokio::sync::mpsc;
use tokio::task::JoinHandle;

const SCHEMA_VERSION: u8 = 2;
const MAX_CAPTURE_CHARS: usize = 16_384;
static CALL_SEQUENCE: AtomicU64 = AtomicU64::new(1);

#[derive(Debug, Clone, Default, Serialize)]
pub struct ProviderTrace {
    pub queue_wait_seconds: f64,
    pub http_attempts: Vec<HttpAttemptRecord>,
}

#[derive(Debug, Clone, Serialize)]
pub struct HttpAttemptRecord {
    pub attempt: usize,
    pub status_code: Option<u16>,
    pub elapsed_seconds: f64,
    pub retryable: bool,
    pub retry_delay_ms: Option<u64>,
    pub error: Option<String>,
    pub response_body: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ExceptionRecord {
    #[serde(rename = "type")]
    pub kind: String,
    pub message: String,
}

#[derive(Debug, Serialize)]
pub struct ApiCallRecord {
    pub call_id: String,
    pub stage: String,
    pub part: Option<usize>,
    pub attempt: usize,
    pub format: &'static str,
    pub system_prompt: String,
    pub user_prompt: String,
    pub response_format: &'static str,
    pub timeout: u64,
    pub raw_response: Option<String>,
    pub parsed_response: Option<Value>,
    pub parse_errors: Vec<Value>,
    pub validation_errors: Vec<Value>,
    pub http_attempts: Vec<HttpAttemptRecord>,
    pub exception: Option<ExceptionRecord>,
    pub status: &'static str,
    pub failure_kind: Option<&'static str>,
    pub metadata: Value,
    pub started_at: String,
    pub finished_at: String,
    pub elapsed_seconds: f64,
}

impl ApiCallRecord {
    pub fn new(
        stage: &str,
        part: Option<usize>,
        system_prompt: String,
        user_prompt: String,
        timeout: u64,
        requested_ids: &[usize],
    ) -> Self {
        Self {
            call_id: format!(
                "native-{}-{}",
                unix_millis(),
                CALL_SEQUENCE.fetch_add(1, Ordering::Relaxed)
            ),
            stage: stage.to_string(),
            part,
            attempt: 1,
            format: "json",
            system_prompt,
            user_prompt,
            response_format: "json_object",
            timeout,
            raw_response: None,
            parsed_response: None,
            parse_errors: Vec::new(),
            validation_errors: Vec::new(),
            http_attempts: Vec::new(),
            exception: None,
            status: "success",
            failure_kind: None,
            metadata: json!({
                "requested_ids": requested_ids,
                "queue_wait_seconds": 0.0,
            }),
            started_at: now_iso8601(),
            finished_at: String::new(),
            elapsed_seconds: 0.0,
        }
    }

    pub fn finish(&mut self, started: Instant, trace: ProviderTrace) {
        self.elapsed_seconds = rounded_seconds(started.elapsed());
        self.finished_at = now_iso8601();
        self.http_attempts = trace.http_attempts;
        self.metadata["queue_wait_seconds"] = json!(trace.queue_wait_seconds);
    }

    pub fn fail(&mut self, error: &EngineError, failure_kind: &'static str) {
        self.status = "failed";
        self.failure_kind = Some(failure_kind);
        self.exception = Some(exception_record(error));
    }
}

#[derive(Debug, Serialize)]
pub struct FileDiagnosticRecord {
    pub schema_version: u8,
    pub timestamp: String,
    pub file_name: String,
    pub text_blocks: Vec<Value>,
    pub reference: Value,
    pub api_calls: Vec<ApiCallRecord>,
    pub outcome: String,
    pub outcome_extra: Value,
    pub exception: Option<ExceptionRecord>,
    pub call_summary: Value,
    pub elapsed_seconds: f64,
    #[serde(skip)]
    started: Instant,
}

impl FileDiagnosticRecord {
    pub fn new(file_name: String, reference: Value) -> Self {
        Self {
            schema_version: SCHEMA_VERSION,
            timestamp: now_iso8601(),
            file_name,
            text_blocks: Vec::new(),
            reference,
            api_calls: Vec::new(),
            outcome: String::new(),
            outcome_extra: json!({}),
            exception: None,
            call_summary: json!({"total": 0, "failed": 0}),
            elapsed_seconds: 0.0,
            started: Instant::now(),
        }
    }

    pub fn push_call(&mut self, call: ApiCallRecord) -> usize {
        self.api_calls.push(call);
        self.api_calls.len() - 1
    }

    pub fn add_validation_errors(&mut self, call_index: usize, errors: Vec<Value>) {
        if errors.is_empty() {
            return;
        }
        if let Some(call) = self.api_calls.get_mut(call_index) {
            call.validation_errors.extend(errors);
            call.status = "validation_error";
            call.failure_kind = Some("rule_validation");
        }
    }

    pub fn mark_recovered(&mut self, call_index: usize) {
        if let Some(call) = self.api_calls.get_mut(call_index) {
            if call.status == "validation_error" {
                call.status = "recovered";
                call.failure_kind = Some("supplemental_recovery");
            }
        }
    }

    pub fn finish_success(&mut self, outcome: &str, extra: Value) {
        self.outcome = outcome.to_string();
        self.outcome_extra = extra;
        self.finish_common();
    }

    pub fn finish_error(&mut self, error: &EngineError) {
        self.outcome = match error {
            EngineError::Json(_) => "JSON_DECODE_ERROR",
            EngineError::InvalidResponse(_) => "TRANSLATION_MISMATCH",
            _ => "SAVE_ERROR",
        }
        .to_string();
        self.outcome_extra = json!({"reason": error.to_string()});
        self.exception = Some(exception_record(error));
        self.finish_common();
    }

    fn finish_common(&mut self) {
        self.elapsed_seconds = rounded_seconds(self.started.elapsed());
        let failed = self
            .api_calls
            .iter()
            .filter(|call| !matches!(call.status, "success" | "recovered"))
            .count();
        self.call_summary = json!({
            "total": self.api_calls.len(),
            "failed": failed,
        });
    }
}

#[derive(Clone)]
pub struct DiagnosticsSink {
    sender: mpsc::Sender<FileDiagnosticRecord>,
}

impl DiagnosticsSink {
    pub async fn start(
        paths: Vec<PathBuf>,
    ) -> std::io::Result<(Self, JoinHandle<std::io::Result<()>>)> {
        let mut unique_paths = BTreeSet::new();
        for path in paths {
            unique_paths.insert(path);
        }
        let mut files = Vec::with_capacity(unique_paths.len());
        for path in unique_paths {
            if let Some(parent) = path.parent() {
                tokio::fs::create_dir_all(parent).await?;
            }
            files.push(tokio::fs::File::create(path).await?);
        }
        let (sender, mut receiver) = mpsc::channel::<FileDiagnosticRecord>(256);
        let writer = tokio::spawn(async move {
            while let Some(record) = receiver.recv().await {
                let mut line = serde_json::to_vec(&record)
                    .map_err(|error| std::io::Error::other(error.to_string()))?;
                line.push(b'\n');
                for file in &mut files {
                    file.write_all(&line).await?;
                }
            }
            for file in &mut files {
                file.flush().await?;
            }
            Ok(())
        });
        Ok((Self { sender }, writer))
    }

    pub async fn record(&self, record: FileDiagnosticRecord) {
        let _ = self.sender.send(record).await;
    }
}

pub fn exception_record(error: &EngineError) -> ExceptionRecord {
    ExceptionRecord {
        kind: error_kind(error).to_string(),
        message: sanitize_text(&error.to_string()),
    }
}

pub fn error_kind(error: &EngineError) -> &'static str {
    match error {
        EngineError::Config(_) => "ConfigError",
        EngineError::Io(_) => "IoError",
        EngineError::Json(_) => "JsonDecodeError",
        EngineError::Network(_) => "NetworkError",
        EngineError::Api { .. } => "ApiError",
        EngineError::InvalidResponse(_) => "InvalidResponse",
        EngineError::Cancelled => "CancelledError",
    }
}

pub fn failure_kind(error: &EngineError) -> &'static str {
    match error {
        EngineError::Network(_) => "network_error",
        EngineError::Api { .. } => "api_error",
        EngineError::Json(_) | EngineError::InvalidResponse(_) => "provider_response_error",
        EngineError::Cancelled => "cancelled",
        EngineError::Config(_) => "config_error",
        EngineError::Io(_) => "io_error",
    }
}

pub fn sanitize_text(value: &str) -> String {
    let mut sanitized = redact_after_marker(value, "Bearer ");
    for marker in [
        "api_key=",
        "api-key=",
        "access_token=",
        "refresh_token=",
        "client_secret=",
        "password=",
        "secret=",
    ] {
        sanitized = redact_after_marker(&sanitized, marker);
    }
    truncate_chars(&sanitized, MAX_CAPTURE_CHARS)
}

fn redact_after_marker(value: &str, marker: &str) -> String {
    let lower = value.to_ascii_lowercase();
    let marker_lower = marker.to_ascii_lowercase();
    let mut output = String::with_capacity(value.len());
    let mut cursor = 0;
    while let Some(relative) = lower[cursor..].find(&marker_lower) {
        let start = cursor + relative;
        let secret_start = start + marker.len();
        output.push_str(&value[cursor..secret_start]);
        output.push_str("<redacted>");
        let rest = &value[secret_start..];
        let secret_len = rest
            .char_indices()
            .find(|(_, character)| {
                character.is_whitespace() || matches!(character, ',' | ';' | '"' | '\'')
            })
            .map(|(index, _)| index)
            .unwrap_or(rest.len());
        cursor = secret_start + secret_len;
    }
    output.push_str(&value[cursor..]);
    output
}

fn truncate_chars(value: &str, limit: usize) -> String {
    let mut end = value.len();
    if let Some((index, _)) = value.char_indices().nth(limit) {
        end = index;
    }
    if end == value.len() {
        value.to_string()
    } else {
        format!("{}…<truncated>", &value[..end])
    }
}

pub fn rounded_seconds(duration: Duration) -> f64 {
    (duration.as_secs_f64() * 1_000_000.0).round() / 1_000_000.0
}

fn unix_millis() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
}

pub fn now_iso8601() -> String {
    let duration = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default();
    let total_seconds = duration.as_secs() as i64;
    let days = total_seconds.div_euclid(86_400);
    let seconds_of_day = total_seconds.rem_euclid(86_400);
    let (year, month, day) = civil_from_days(days);
    let hour = seconds_of_day / 3_600;
    let minute = seconds_of_day % 3_600 / 60;
    let second = seconds_of_day % 60;
    format!(
        "{year:04}-{month:02}-{day:02}T{hour:02}:{minute:02}:{second:02}.{:03}Z",
        duration.subsec_millis()
    )
}

fn civil_from_days(days_since_epoch: i64) -> (i64, i64, i64) {
    let days = days_since_epoch + 719_468;
    let era = if days >= 0 { days } else { days - 146_096 } / 146_097;
    let day_of_era = days - era * 146_097;
    let year_of_era =
        (day_of_era - day_of_era / 1_460 + day_of_era / 36_524 - day_of_era / 146_096) / 365;
    let mut year = year_of_era + era * 400;
    let day_of_year = day_of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100);
    let month_prime = (5 * day_of_year + 2) / 153;
    let day = day_of_year - (153 * month_prime + 2) / 5 + 1;
    let month = month_prime + if month_prime < 10 { 3 } else { -9 };
    year += i64::from(month <= 2);
    (year, month, day)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn civil_date_matches_unix_epoch() {
        assert_eq!(civil_from_days(0), (1970, 1, 1));
        assert_eq!(civil_from_days(20_663), (2026, 7, 29));
    }

    #[test]
    fn redacts_and_truncates_sensitive_text() {
        let value = sanitize_text("Authorization: Bearer secret-token api_key=hidden next");
        assert!(!value.contains("secret-token"));
        assert!(!value.contains("hidden"));
        assert!(value.contains("<redacted>"));
    }

    #[tokio::test]
    async fn writes_schema_v2_jsonl_with_single_async_writer() {
        let path = std::env::temp_dir().join(format!(
            "lcta-native-diagnostics-{}-{}.jsonl",
            std::process::id(),
            unix_millis()
        ));
        let (sink, writer) = DiagnosticsSink::start(vec![path.clone()]).await.unwrap();
        let mut record = FileDiagnosticRecord::new("Example.json".to_string(), json!({}));
        record.finish_success("SUCCESS_SAVED", json!({"saved": true}));
        sink.record(record).await;
        drop(sink);
        writer.await.unwrap().unwrap();

        let content = tokio::fs::read_to_string(&path).await.unwrap();
        let value: Value = serde_json::from_str(content.trim()).unwrap();
        assert_eq!(value["schema_version"], 2);
        assert_eq!(value["file_name"], "Example.json");
        assert_eq!(value["outcome"], "SUCCESS_SAVED");
        tokio::fs::remove_file(path).await.unwrap();
    }
}
