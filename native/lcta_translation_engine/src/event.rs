use crossbeam_channel::Sender;
use serde::Serialize;

#[derive(Debug, Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum EngineEvent<'a> {
    Phase {
        name: &'a str,
    },
    Progress {
        completed: usize,
        total: usize,
        file: &'a str,
    },
    RequestRetry {
        file: &'a str,
        attempt: usize,
        delay_ms: u64,
        reason: &'a str,
    },
}

pub fn emit(sender: &Sender<String>, event: EngineEvent<'_>) {
    if let Ok(serialized) = serde_json::to_string(&event) {
        let _ = sender.try_send(serialized);
    }
}
