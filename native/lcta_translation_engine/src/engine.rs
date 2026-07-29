use crate::config::{ResolvedPaths, RunConfig};
use crate::document::{
    build_output_root, flatten_map, flatten_strings, path_key, set_string_at_path, EntryKey,
    LocaleDocument, PathSegment,
};
use crate::error::{EngineError, Result};
use crate::event::{emit, EngineEvent};
use crate::provider::{Provider, TranslationRequest};
use crate::rules::{normalize_bracket_spacing, validate_translation};
use crossbeam_channel::Sender;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use tokio::sync::Semaphore;
use tokio::task::JoinSet;
use walkdir::WalkDir;

#[derive(Debug, Clone, Serialize)]
pub struct TranslationSummary {
    pub total: usize,
    pub saved: Vec<String>,
    pub skipped: Vec<String>,
    pub fallback: Vec<String>,
    pub errors: Vec<FileError>,
}

#[derive(Debug, Clone, Serialize)]
pub struct FileError {
    pub file: String,
    pub message: String,
}

#[derive(Debug)]
enum FileOutcome {
    Saved(String),
    Skipped(String),
    Fallback(String),
    Error(FileError),
}

#[derive(Debug, Clone)]
struct FileDescriptor {
    name: String,
    relative: PathBuf,
    kr: PathBuf,
    jp: PathBuf,
    en: PathBuf,
    llc: PathBuf,
    output: PathBuf,
}

#[derive(Debug, Clone)]
struct TranslationUnit {
    id: usize,
    entry_key: EntryKey,
    path: Vec<PathSegment>,
    kr: String,
    jp: String,
    en: String,
}

#[derive(Debug, Deserialize)]
struct TranslationEnvelope {
    translations: Vec<TranslationItem>,
}

#[derive(Debug, Deserialize)]
struct TranslationItem {
    id: usize,
    translation: String,
}

pub async fn run(
    config: RunConfig,
    events: Sender<String>,
    cancelled: Arc<AtomicBool>,
) -> Result<TranslationSummary> {
    emit(&events, EngineEvent::Phase { name: "scan" });
    let paths = config.resolve_paths();
    tokio::fs::create_dir_all(&paths.output).await?;
    let files = discover_files(&paths, config.pipeline.has_prefix)?;
    let total = files.len();
    let provider = Provider::new(
        config.provider.clone(),
        config.concurrency.requests,
        events.clone(),
    )?;
    let file_limiter = Arc::new(Semaphore::new(config.concurrency.files.max(1)));
    emit(&events, EngineEvent::Phase { name: "translate" });

    let mut tasks = JoinSet::new();
    for descriptor in files {
        let permit = file_limiter
            .clone()
            .acquire_owned()
            .await
            .map_err(|_| EngineError::Cancelled)?;
        let provider = provider.clone();
        let config = config.clone();
        let cancelled = cancelled.clone();
        tasks.spawn(async move {
            let _permit = permit;
            if cancelled.load(Ordering::Relaxed) {
                return FileOutcome::Error(FileError {
                    file: descriptor.name,
                    message: EngineError::Cancelled.to_string(),
                });
            }
            match process_file(&descriptor, &config, &provider, &cancelled).await {
                Ok(outcome) => outcome,
                Err(error) => FileOutcome::Error(FileError {
                    file: descriptor.name,
                    message: error.to_string(),
                }),
            }
        });
    }

    let mut saved = Vec::new();
    let mut skipped = Vec::new();
    let mut fallback = Vec::new();
    let mut errors = Vec::new();
    let mut completed = 0;
    while let Some(result) = tasks.join_next().await {
        completed += 1;
        let outcome = result.unwrap_or_else(|error| {
            FileOutcome::Error(FileError {
                file: "<task>".to_string(),
                message: error.to_string(),
            })
        });
        let file = match &outcome {
            FileOutcome::Saved(file) => {
                saved.push(file.clone());
                file
            }
            FileOutcome::Skipped(file) => {
                skipped.push(file.clone());
                file
            }
            FileOutcome::Fallback(file) => {
                fallback.push(file.clone());
                file
            }
            FileOutcome::Error(error) => {
                errors.push(error.clone());
                &error.file
            }
        };
        emit(
            &events,
            EngineEvent::Progress {
                completed,
                total,
                file,
            },
        );
    }
    emit(&events, EngineEvent::Phase { name: "complete" });
    Ok(TranslationSummary {
        total,
        saved,
        skipped,
        fallback,
        errors,
    })
}

fn discover_files(paths: &ResolvedPaths, has_prefix: bool) -> Result<Vec<FileDescriptor>> {
    if !paths.kr.exists() {
        return Err(EngineError::Config(format!(
            "韩文目录不存在: {}",
            paths.kr.display()
        )));
    }
    let mut files = Vec::new();
    for entry in WalkDir::new(&paths.kr)
        .into_iter()
        .filter_map(std::result::Result::ok)
    {
        if !entry.file_type().is_file()
            || entry.path().extension().and_then(|value| value.to_str()) != Some("json")
        {
            continue;
        }
        let relative = entry
            .path()
            .strip_prefix(&paths.kr)
            .map_err(|error| EngineError::Config(error.to_string()))?
            .to_path_buf();
        let file_name = relative
            .file_name()
            .and_then(|value| value.to_str())
            .unwrap_or("unknown.json");
        let logical_name = if has_prefix {
            file_name.strip_prefix("KR_").unwrap_or(file_name)
        } else {
            file_name
        };
        let output_relative = relative.with_file_name(logical_name);
        let jp_relative = if has_prefix {
            relative.with_file_name(format!("JP_{logical_name}"))
        } else {
            relative.clone()
        };
        let en_relative = if has_prefix {
            relative.with_file_name(format!("EN_{logical_name}"))
        } else {
            relative.clone()
        };
        files.push(FileDescriptor {
            name: logical_name.to_string(),
            relative: relative.clone(),
            kr: entry.path().to_path_buf(),
            jp: paths.jp.join(jp_relative),
            en: paths.en.join(en_relative),
            llc: paths.llc.join(&output_relative),
            output: paths.output.join(&output_relative),
        });
    }
    files.sort_by(|left, right| left.relative.cmp(&right.relative));
    Ok(files)
}

async fn process_file(
    descriptor: &FileDescriptor,
    config: &RunConfig,
    provider: &Provider,
    cancelled: &AtomicBool,
) -> Result<FileOutcome> {
    let (kr, jp, en, llc) = tokio::join!(
        load_required(&descriptor.kr),
        load_optional(&descriptor.jp),
        load_optional(&descriptor.en),
        load_optional(&descriptor.llc),
    );
    let kr = kr?;
    let jp = jp?;
    let en = en?;
    let llc = llc?;

    if kr.is_empty() {
        if descriptor.llc.exists() {
            copy_atomic(&descriptor.llc, &descriptor.output).await?;
        }
        return Ok(FileOutcome::Skipped(descriptor.name.clone()));
    }

    let missing_keys = kr
        .index
        .keys()
        .filter(|key| !llc.index.contains_key(*key))
        .cloned()
        .collect::<Vec<_>>();
    if missing_keys.is_empty() {
        if descriptor.llc.exists() {
            copy_atomic(&descriptor.llc, &descriptor.output).await?;
        }
        return Ok(FileOutcome::Skipped(descriptor.name.clone()));
    }

    let mut units = Vec::new();
    for key in &missing_keys {
        let Some(kr_entry) = kr.entry(key) else {
            continue;
        };
        let jp_flat = jp.entry(key).map(flatten_map).unwrap_or_default();
        let en_flat = en.entry(key).map(flatten_map).unwrap_or_default();
        for flat in flatten_strings(kr_entry) {
            let lookup_key = path_key(&flat.path);
            units.push(TranslationUnit {
                id: units.len() + 1,
                entry_key: key.clone(),
                path: flat.path,
                kr: flat.text,
                jp: jp_flat.get(&lookup_key).cloned().unwrap_or_default(),
                en: en_flat.get(&lookup_key).cloned().unwrap_or_default(),
            });
        }
    }
    if units.is_empty() {
        fallback_copy(descriptor).await?;
        return Ok(FileOutcome::Fallback(descriptor.name.clone()));
    }

    let mut translated = HashMap::new();
    for chunk in split_units(&units, config.pipeline.max_prompt_chars) {
        if cancelled.load(Ordering::Relaxed) {
            return Err(EngineError::Cancelled);
        }
        let raw = provider
            .translate(TranslationRequest {
                file: descriptor.name.clone(),
                system_prompt: system_prompt(descriptor),
                user_prompt: user_prompt(&chunk)?,
            })
            .await?;
        for item in parse_translations(&raw)? {
            translated.insert(item.id, item.translation);
        }
    }

    let mut updated_entries = HashMap::new();
    for key in &missing_keys {
        if let Some(entry) = kr.entry(key) {
            updated_entries.insert(key.clone(), entry.clone());
        }
    }
    for unit in &units {
        let candidate = translated
            .get(&unit.id)
            .map(|value| {
                if descriptor.name.starts_with("Skills_") {
                    normalize_bracket_spacing(value)
                } else {
                    value.clone()
                }
            })
            .filter(|value| validate_translation(&unit.kr, value))
            .unwrap_or_else(|| unit.kr.clone());
        if let Some(entry) = updated_entries.get_mut(&unit.entry_key) {
            set_string_at_path(entry, &unit.path, candidate);
        }
    }

    let mut output_entries = Vec::with_capacity(kr.entries.len());
    for (position, kr_entry) in kr.entries.iter().enumerate() {
        let key = kr.key_at(position);
        if let Some(existing) = llc.entry(&key) {
            output_entries.push(existing.clone());
        } else if let Some(translated_entry) = updated_entries.remove(&key) {
            output_entries.push(translated_entry);
        } else {
            output_entries.push(kr_entry.clone());
        }
    }
    if config.pipeline.save_result {
        write_json_atomic(
            &descriptor.output,
            &build_output_root(&kr.root, output_entries),
        )
        .await?;
    }
    Ok(FileOutcome::Saved(descriptor.name.clone()))
}

fn split_units(units: &[TranslationUnit], max_chars: usize) -> Vec<Vec<TranslationUnit>> {
    let mut chunks = Vec::new();
    let mut current = Vec::new();
    let mut current_size = 0;
    for unit in units {
        let size = unit.kr.len() + unit.jp.len() + unit.en.len() + 128;
        if !current.is_empty() && current_size + size > max_chars.max(1_000) {
            chunks.push(std::mem::take(&mut current));
            current_size = 0;
        }
        current.push(unit.clone());
        current_size += size;
    }
    if !current.is_empty() {
        chunks.push(current);
    }
    chunks
}

fn system_prompt(descriptor: &FileDescriptor) -> String {
    let file_kind = if descriptor
        .relative
        .components()
        .any(|component| component.as_os_str() == "StoryData")
    {
        "剧情文本"
    } else if descriptor.name.starts_with("Skills_") {
        "技能文本"
    } else {
        "游戏文本"
    };
    format!(
        "你是《边狱公司》的专业简体中文本地化译者。当前处理{file_kind}。\n\
         必须逐项翻译，不得合并、遗漏或改变 id。优先依据韩文，日文和英文仅作为语义参考。\n\
         完整保留方括号标识、格式标签、变量、数字和换行语义。\n\
         仅返回 JSON 对象，格式为 {{\"translations\":[{{\"id\":1,\"translation\":\"译文\"}}]}}。"
    )
}

fn user_prompt(units: &[TranslationUnit]) -> Result<String> {
    let items = units
        .iter()
        .map(|unit| {
            json!({
                "id": unit.id, "kr": unit.kr, "jp": unit.jp, "en": unit.en,
            })
        })
        .collect::<Vec<_>>();
    Ok(serde_json::to_string(&json!({ "text_blocks": items }))?)
}

fn parse_translations(raw: &str) -> Result<Vec<TranslationItem>> {
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
    if let Ok(envelope) = serde_json::from_str::<TranslationEnvelope>(normalized) {
        return Ok(envelope.translations);
    }
    if let Ok(items) = serde_json::from_str::<Vec<TranslationItem>>(normalized) {
        return Ok(items);
    }
    Err(EngineError::InvalidResponse(
        "无法解析 translations JSON".to_string(),
    ))
}

async fn load_required(path: &Path) -> Result<LocaleDocument> {
    LocaleDocument::parse(&tokio::fs::read(path).await?)
}

async fn load_optional(path: &Path) -> Result<LocaleDocument> {
    match tokio::fs::read(path).await {
        Ok(bytes) => LocaleDocument::parse(&bytes),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(LocaleDocument::empty()),
        Err(error) => Err(error.into()),
    }
}

async fn write_json_atomic(path: &Path, value: &Value) -> Result<()> {
    if let Some(parent) = path.parent() {
        tokio::fs::create_dir_all(parent).await?;
    }
    let mut bytes = vec![0xEF, 0xBB, 0xBF];
    bytes.extend_from_slice(serde_json::to_string_pretty(value)?.as_bytes());
    let temporary = path.with_extension("json.lcta-tmp");
    tokio::fs::write(&temporary, bytes).await?;
    if tokio::fs::try_exists(path).await? {
        tokio::fs::remove_file(path).await?;
    }
    tokio::fs::rename(temporary, path).await?;
    Ok(())
}

async fn copy_atomic(source: &Path, target: &Path) -> Result<()> {
    if let Some(parent) = target.parent() {
        tokio::fs::create_dir_all(parent).await?;
    }
    let temporary = target.with_extension("json.lcta-tmp");
    tokio::fs::copy(source, &temporary).await?;
    if tokio::fs::try_exists(target).await? {
        tokio::fs::remove_file(target).await?;
    }
    tokio::fs::rename(temporary, target).await?;
    Ok(())
}

async fn fallback_copy(descriptor: &FileDescriptor) -> Result<()> {
    for source in [
        &descriptor.llc,
        &descriptor.en,
        &descriptor.jp,
        &descriptor.kr,
    ] {
        if tokio::fs::try_exists(source).await? {
            return copy_atomic(source, &descriptor.output).await;
        }
    }
    Err(EngineError::Config(format!(
        "{} 没有可用的回退文件",
        descriptor.name
    )))
}
