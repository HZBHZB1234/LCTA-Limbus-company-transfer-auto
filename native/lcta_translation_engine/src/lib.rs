mod config;
mod document;
mod engine;
mod error;
mod event;
mod provider;
mod rules;

use config::RunConfig;
use crossbeam_channel::{bounded, Receiver};
use pyo3::exceptions::{PyRuntimeError, PyValueError};
use pyo3::prelude::*;
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

#[pymodule]
fn _lcta_native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<TranslationJob>()?;
    module.add_function(wrap_pyfunction!(start_translation, module)?)?;
    Ok(())
}
