use crate::config::{ResolvedPaths, RunConfig};
use crate::document::{
    build_output_root, flatten_map, flatten_strings, path_key, set_string_at_path, EntryKey,
    LocaleDocument, PathSegment,
};
use crate::error::{EngineError, Result};
use crate::event::{emit, EngineEvent};
use crate::provider::{Provider, TranslationRequest, TranslationTask};
use crate::rules::{
    load_affects_from_files, load_proper_terms, load_roles_from_files, normalize_bracket_spacing,
    validate_translation, RuleSnapshot,
};
use crossbeam_channel::Sender;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet, HashMap};
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
    model: String,
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
    let mut files = discover_files(&paths, config.pipeline.has_prefix)?;
    let total = files.len();
    let provider = Provider::new(
        config.provider.clone(),
        config.concurrency.requests,
        events.clone(),
    )?;
    let io_limiter = Arc::new(Semaphore::new(config.concurrency.file_io.max(1)));

    emit(&events, EngineEvent::Phase { name: "rules" });
    let mut rules = RuleSnapshot::default();
    if config.rules.enable_proper {
        match load_proper_terms(&config.rules).await {
            Ok(terms) => {
                rules = rules.with_proper_terms(terms);
                let message = format!("Rust 已冻结 {} 条专有名词规则", rules.proper_count());
                emit(
                    &events,
                    EngineEvent::Log {
                        level: "info",
                        message: &message,
                    },
                );
            }
            Err(error) => {
                let message = format!("专有名词规则加载失败，将继续翻译: {error}");
                emit(
                    &events,
                    EngineEvent::Log {
                        level: "warning",
                        message: &message,
                    },
                );
            }
        }
    }

    let keyword_index = files.iter().position(is_keyword_file);
    let keyword = keyword_index.map(|index| files.remove(index));
    let model_index = files.iter().position(is_model_file);
    let model = model_index.map(|index| files.remove(index));

    let mut saved = Vec::new();
    let mut skipped = Vec::new();
    let mut fallback = Vec::new();
    let mut errors = Vec::new();
    let mut completed = 0;

    for descriptor in [keyword, model].into_iter().flatten() {
        if cancelled.load(Ordering::Relaxed) {
            return Err(EngineError::Cancelled);
        }
        let outcome = match process_file(
            &descriptor,
            &config,
            &provider,
            &rules,
            &io_limiter,
            &cancelled,
        )
        .await
        {
            Ok(outcome) => outcome,
            Err(error) => FileOutcome::Error(FileError {
                file: descriptor.name.clone(),
                message: error.to_string(),
            }),
        };
        completed += 1;
        record_outcome(
            outcome,
            completed,
            total,
            &events,
            &mut saved,
            &mut skipped,
            &mut fallback,
            &mut errors,
        );

        let cn_path = resolved_rule_output(&descriptor, config.pipeline.save_result);
        if is_keyword_file(&descriptor) && config.rules.enable_skill {
            match load_affects_from_files(&descriptor.kr, &descriptor.jp, &descriptor.en, &cn_path)
                .await
            {
                Ok(affects) => {
                    rules = rules.with_affects(affects);
                    let message = format!("Rust 已冻结 {} 条状态效果规则", rules.affect_count());
                    emit(
                        &events,
                        EngineEvent::Log {
                            level: "info",
                            message: &message,
                        },
                    );
                }
                Err(error) => {
                    let message = format!("状态效果规则加载失败: {error}");
                    emit(
                        &events,
                        EngineEvent::Log {
                            level: "warning",
                            message: &message,
                        },
                    );
                }
            }
        } else if is_model_file(&descriptor) && config.rules.enable_role {
            match load_roles_from_files(&descriptor.kr, &cn_path).await {
                Ok(roles) => {
                    rules = rules.with_roles(roles);
                    let message = format!("Rust 已冻结 {} 条角色规则", rules.role_count());
                    emit(
                        &events,
                        EngineEvent::Log {
                            level: "info",
                            message: &message,
                        },
                    );
                }
                Err(error) => {
                    let message = format!("角色规则加载失败: {error}");
                    emit(
                        &events,
                        EngineEvent::Log {
                            level: "warning",
                            message: &message,
                        },
                    );
                }
            }
        }
    }

    let file_limiter = Arc::new(Semaphore::new(config.concurrency.files.max(1)));
    emit(&events, EngineEvent::Phase { name: "translate" });
    let rules = Arc::new(rules);
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
        let rules = rules.clone();
        let io_limiter = io_limiter.clone();
        tasks.spawn(async move {
            let _permit = permit;
            if cancelled.load(Ordering::Relaxed) {
                return FileOutcome::Error(FileError {
                    file: descriptor.name,
                    message: EngineError::Cancelled.to_string(),
                });
            }
            match process_file(
                &descriptor,
                &config,
                &provider,
                &rules,
                &io_limiter,
                &cancelled,
            )
            .await
            {
                Ok(outcome) => outcome,
                Err(error) => FileOutcome::Error(FileError {
                    file: descriptor.name,
                    message: error.to_string(),
                }),
            }
        });
    }

    while let Some(result) = tasks.join_next().await {
        completed += 1;
        let outcome = result.unwrap_or_else(|error| {
            FileOutcome::Error(FileError {
                file: "<task>".to_string(),
                message: error.to_string(),
            })
        });
        record_outcome(
            outcome,
            completed,
            total,
            &events,
            &mut saved,
            &mut skipped,
            &mut fallback,
            &mut errors,
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

#[allow(clippy::too_many_arguments)]
fn record_outcome(
    outcome: FileOutcome,
    completed: usize,
    total: usize,
    events: &Sender<String>,
    saved: &mut Vec<String>,
    skipped: &mut Vec<String>,
    fallback: &mut Vec<String>,
    errors: &mut Vec<FileError>,
) {
    let file = match outcome {
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
            let file = error.file.clone();
            errors.push(error);
            file
        }
    };
    emit(
        events,
        EngineEvent::Progress {
            completed,
            total,
            file: &file,
        },
    );
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

fn is_keyword_file(descriptor: &FileDescriptor) -> bool {
    descriptor.name.eq_ignore_ascii_case("BattleKeywords.json")
}

fn is_model_file(descriptor: &FileDescriptor) -> bool {
    descriptor
        .name
        .eq_ignore_ascii_case("ScenarioModelCodes-AutoCreated.json")
}

fn is_story_file(descriptor: &FileDescriptor) -> bool {
    descriptor.relative.components().any(|component| {
        component
            .as_os_str()
            .to_string_lossy()
            .eq_ignore_ascii_case("StoryData")
    })
}

fn is_skill_file(descriptor: &FileDescriptor) -> bool {
    descriptor.name.starts_with("Skills_")
}

fn resolved_rule_output(descriptor: &FileDescriptor, save_result: bool) -> PathBuf {
    if save_result && descriptor.output.exists() {
        descriptor.output.clone()
    } else if descriptor.llc.exists() {
        descriptor.llc.clone()
    } else {
        descriptor.kr.clone()
    }
}

async fn process_file(
    descriptor: &FileDescriptor,
    config: &RunConfig,
    provider: &Provider,
    rules: &RuleSnapshot,
    io_limiter: &Arc<Semaphore>,
    cancelled: &AtomicBool,
) -> Result<FileOutcome> {
    let (kr, jp, en, llc) = tokio::join!(
        load_required(&descriptor.kr, io_limiter),
        load_optional(&descriptor.jp, io_limiter),
        load_optional(&descriptor.en, io_limiter),
        load_optional(&descriptor.llc, io_limiter),
    );
    let kr = kr?;
    let jp = jp?;
    let en = en?;
    let llc = llc?;

    if kr.is_empty() {
        if descriptor.llc.exists() {
            copy_atomic(&descriptor.llc, &descriptor.output, io_limiter).await?;
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
            copy_atomic(&descriptor.llc, &descriptor.output, io_limiter).await?;
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
        let model = kr_entry
            .get("model")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string();
        for flat in flatten_strings(kr_entry) {
            let lookup_key = path_key(&flat.path);
            units.push(TranslationUnit {
                id: units.len() + 1,
                entry_key: key.clone(),
                path: flat.path,
                kr: flat.text,
                jp: jp_flat.get(&lookup_key).cloned().unwrap_or_default(),
                en: en_flat.get(&lookup_key).cloned().unwrap_or_default(),
                model: model.clone(),
            });
        }
    }
    if units.is_empty() {
        fallback_copy(descriptor, io_limiter).await?;
        return Ok(FileOutcome::Fallback(descriptor.name.clone()));
    }

    let mut translated = HashMap::new();
    for chunk in split_units(&units, config.pipeline.max_prompt_chars, descriptor, rules)? {
        if cancelled.load(Ordering::Relaxed) {
            return Err(EngineError::Cancelled);
        }
        let mut chunk_translations = request_translations(
            provider,
            descriptor,
            &chunk,
            rules,
            TranslationTask::Translate,
            false,
        )
        .await?;

        let retry_units = chunk
            .iter()
            .filter(|unit| {
                chunk_translations
                    .get(&unit.id)
                    .and_then(|value| validated_candidate(descriptor, unit, value, rules, config))
                    .is_none()
            })
            .cloned()
            .collect::<Vec<_>>();
        if !retry_units.is_empty() {
            let supplemental = request_translations(
                provider,
                descriptor,
                &retry_units,
                rules,
                TranslationTask::Translate,
                true,
            )
            .await?;
            chunk_translations.extend(supplemental);
        }

        if config.pipeline.enable_self_check {
            let current = chunk
                .iter()
                .map(|unit| {
                    let translation = chunk_translations
                        .get(&unit.id)
                        .and_then(|value| {
                            validated_candidate(descriptor, unit, value, rules, config)
                        })
                        .unwrap_or_else(|| unit.kr.clone());
                    (unit.id, translation)
                })
                .collect::<HashMap<_, _>>();
            let checked = request_self_check(provider, descriptor, &chunk, &current, rules).await?;
            chunk_translations.extend(checked);
        }

        for unit in &chunk {
            if let Some(candidate) = chunk_translations
                .get(&unit.id)
                .and_then(|value| validated_candidate(descriptor, unit, value, rules, config))
            {
                translated.insert(unit.id, candidate);
            }
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
            .cloned()
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
            io_limiter,
        )
        .await?;
    }
    Ok(FileOutcome::Saved(descriptor.name.clone()))
}

fn split_units(
    units: &[TranslationUnit],
    max_chars: usize,
    descriptor: &FileDescriptor,
    rules: &RuleSnapshot,
) -> Result<Vec<Vec<TranslationUnit>>> {
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
    let mut refined = Vec::new();
    let mut pending = chunks;
    while let Some(chunk) = pending.pop() {
        if chunk.len() > 1 && user_prompt(&chunk, descriptor, rules)?.len() > max_chars.max(1_000) {
            let right = chunk[chunk.len() / 2..].to_vec();
            let left = chunk[..chunk.len() / 2].to_vec();
            pending.push(right);
            pending.push(left);
        } else {
            refined.push(chunk);
        }
    }
    Ok(refined)
}

fn system_prompt(descriptor: &FileDescriptor, supplemental: bool) -> String {
    let file_kind = if is_story_file(descriptor) {
        "剧情文本"
    } else if is_skill_file(descriptor) {
        "技能文本"
    } else if descriptor.relative.components().any(|component| {
        component
            .as_os_str()
            .to_string_lossy()
            .to_uppercase()
            .contains("UI")
    }) {
        "界面文本"
    } else {
        "游戏文本"
    };
    let stage_rule = if supplemental {
        "这是缺失条目的补充翻译请求，只处理输入中的条目，不要推测或补写其他 id。"
    } else {
        "这是主翻译请求。"
    };
    let type_rule = if is_story_file(descriptor) {
        "遵循 role_styles 中的角色语气，使用自然的全角中文标点。"
    } else if is_skill_file(descriptor) {
        "技能描述必须紧凑；状态效果名称遵循 affects，并保留效果 ID、标签和数值。"
    } else {
        "译文应简洁、自然并符合游戏界面语境。"
    };
    format!(
        "你是《边狱公司》的专业简体中文本地化译者。当前处理{file_kind}。\n\
         {stage_rule}\n\
         必须逐项翻译，不得合并、遗漏或改变 id。优先依据韩文，日文和英文仅作为语义参考。\n\
         glossary、affects、role_styles 是当前请求的不可变规则快照，必须保持术语一致。\n\
         {type_rule}\n\
         完整保留方括号标识、富文本标签、变量、数字和换行语义。\n\
         仅返回 JSON 对象，格式为 {{\"translations\":[{{\"id\":1,\"translation\":\"译文\"}}]}}。"
    )
}

fn user_prompt(
    units: &[TranslationUnit],
    descriptor: &FileDescriptor,
    rules: &RuleSnapshot,
) -> Result<String> {
    let mut glossary = BTreeMap::new();
    let mut affects = BTreeMap::new();
    let mut roles = BTreeMap::new();
    let mut items = Vec::with_capacity(units.len());
    for unit in units {
        let references = rules.references_for(&unit.kr, &unit.jp, &unit.en, &unit.model);
        let proper_refs = references
            .proper
            .iter()
            .map(|term| term.term.clone())
            .collect::<BTreeSet<_>>();
        let affect_refs = references
            .affects
            .iter()
            .map(|affect| format!("[{}]", affect.id))
            .collect::<BTreeSet<_>>();
        for term in references.proper {
            glossary.entry(term.term.clone()).or_insert(term);
        }
        for affect in references.affects {
            affects.entry(affect.id.clone()).or_insert(affect);
        }
        for role in references.roles {
            roles.entry(role.id.clone()).or_insert(role);
        }
        items.push(json!({
            "id": unit.id,
            "kr": unit.kr,
            "jp": unit.jp,
            "en": unit.en,
            "model": (!unit.model.is_empty()).then_some(unit.model.as_str()),
            "proper_refs": proper_refs,
            "affect_refs": affect_refs,
        }));
    }
    let mut request = json!({
        "glossary": glossary.into_values().collect::<Vec<_>>(),
        "affects": affects.into_values().collect::<Vec<_>>(),
        "text_blocks": items,
    });
    if is_story_file(descriptor) {
        request["role_styles"] = json!(roles.into_values().collect::<Vec<_>>());
    }
    if is_skill_file(descriptor) {
        request["skill_rules"] = json!([
            "状态效果中文名后保留一个半角空格，位于方括号内的 ID 除外",
            "위력译为强度，횟수译为层数",
            "保留所有效果 ID、数值、占位符和富文本标签"
        ]);
    }
    Ok(serde_json::to_string(&request)?)
}

async fn request_translations(
    provider: &Provider,
    descriptor: &FileDescriptor,
    units: &[TranslationUnit],
    rules: &RuleSnapshot,
    task: TranslationTask,
    supplemental: bool,
) -> Result<HashMap<usize, String>> {
    let raw = provider
        .translate(TranslationRequest {
            file: descriptor.name.clone(),
            task,
            system_prompt: system_prompt(descriptor, supplemental),
            user_prompt: user_prompt(units, descriptor, rules)?,
        })
        .await?;
    Ok(parse_translations(&raw)?
        .into_iter()
        .map(|item| (item.id, item.translation))
        .collect())
}

async fn request_self_check(
    provider: &Provider,
    descriptor: &FileDescriptor,
    units: &[TranslationUnit],
    translations: &HashMap<usize, String>,
    rules: &RuleSnapshot,
) -> Result<HashMap<usize, String>> {
    let base: Value = serde_json::from_str(&user_prompt(units, descriptor, rules)?)?;
    let mut items = base
        .get("text_blocks")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    for item in &mut items {
        let id = item.get("id").and_then(Value::as_u64).unwrap_or_default() as usize;
        item["translation"] = json!(translations.get(&id).cloned().unwrap_or_default());
    }
    let user_prompt = serde_json::to_string(&json!({
        "glossary": base.get("glossary").cloned().unwrap_or_else(|| json!([])),
        "affects": base.get("affects").cloned().unwrap_or_else(|| json!([])),
        "role_styles": base.get("role_styles").cloned().unwrap_or_else(|| json!([])),
        "text_blocks": items,
    }))?;
    let raw = provider
        .translate(TranslationRequest {
            file: descriptor.name.clone(),
            task: TranslationTask::SelfCheck,
            system_prompt: format!(
                "你是《边狱公司》简体中文本地化校对员。检查术语一致性、标点、标签、变量、数字和效果引用。\n\
                 不改变 id，不增删条目；只返回 JSON 对象 {{\"translations\":[{{\"id\":1,\"translation\":\"修正后译文\"}}]}}。"
            ),
            user_prompt,
        })
        .await?;
    Ok(parse_translations(&raw)?
        .into_iter()
        .map(|item| (item.id, item.translation))
        .collect())
}

fn validated_candidate(
    descriptor: &FileDescriptor,
    unit: &TranslationUnit,
    value: &str,
    rules: &RuleSnapshot,
    config: &RunConfig,
) -> Option<String> {
    let candidate = if is_skill_file(descriptor) {
        normalize_bracket_spacing(value)
    } else {
        value.to_string()
    };
    let valid = if config.pipeline.enable_rule_validation {
        validate_translation(&unit.kr, &unit.jp, &unit.en, &candidate, rules)
    } else {
        !candidate.trim().is_empty()
    };
    valid.then_some(candidate)
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

async fn load_required(path: &Path, io_limiter: &Semaphore) -> Result<LocaleDocument> {
    let _permit = io_limiter
        .acquire()
        .await
        .map_err(|_| EngineError::Cancelled)?;
    LocaleDocument::parse(&tokio::fs::read(path).await?)
}

async fn load_optional(path: &Path, io_limiter: &Semaphore) -> Result<LocaleDocument> {
    let _permit = io_limiter
        .acquire()
        .await
        .map_err(|_| EngineError::Cancelled)?;
    match tokio::fs::read(path).await {
        Ok(bytes) => LocaleDocument::parse(&bytes),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(LocaleDocument::empty()),
        Err(error) => Err(error.into()),
    }
}

async fn write_json_atomic(path: &Path, value: &Value, io_limiter: &Semaphore) -> Result<()> {
    let _permit = io_limiter
        .acquire()
        .await
        .map_err(|_| EngineError::Cancelled)?;
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

async fn copy_atomic(source: &Path, target: &Path, io_limiter: &Semaphore) -> Result<()> {
    let _permit = io_limiter
        .acquire()
        .await
        .map_err(|_| EngineError::Cancelled)?;
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

async fn fallback_copy(descriptor: &FileDescriptor, io_limiter: &Semaphore) -> Result<()> {
    for source in [
        &descriptor.llc,
        &descriptor.en,
        &descriptor.jp,
        &descriptor.kr,
    ] {
        if tokio::fs::try_exists(source).await? {
            return copy_atomic(source, &descriptor.output, io_limiter).await;
        }
    }
    Err(EngineError::Config(format!(
        "{} 没有可用的回退文件",
        descriptor.name
    )))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::rules::{AffectRule, ProperTerm, RoleRule};

    fn descriptor(name: &str, relative: &str) -> FileDescriptor {
        FileDescriptor {
            name: name.to_string(),
            relative: PathBuf::from(relative),
            kr: PathBuf::from(format!("KR_{name}")),
            jp: PathBuf::from(format!("JP_{name}")),
            en: PathBuf::from(format!("EN_{name}")),
            llc: PathBuf::from(name),
            output: PathBuf::from(name),
        }
    }

    #[test]
    fn identifies_priority_rule_sources() {
        assert!(is_keyword_file(&descriptor(
            "BattleKeywords.json",
            "KR_BattleKeywords.json"
        )));
        assert!(is_model_file(&descriptor(
            "ScenarioModelCodes-AutoCreated.json",
            "KR_ScenarioModelCodes-AutoCreated.json"
        )));
    }

    #[test]
    fn renders_only_references_used_by_the_chunk() {
        let rules = RuleSnapshot::default()
            .with_proper_terms(vec![ProperTerm {
                term: "이상".to_string(),
                translation: "李箱".to_string(),
                note: "角色名".to_string(),
            }])
            .with_roles(vec![RoleRule {
                id: "YiSang".to_string(),
                kr: "이상".to_string(),
                cn: "李箱".to_string(),
                nickname: String::new(),
            }])
            .with_affects(vec![AffectRule {
                id: "Tremor".to_string(),
                kr: "진동".to_string(),
                jp: "振動".to_string(),
                en: "Tremor".to_string(),
                cn: "震颤".to_string(),
                desc: String::new(),
            }]);
        let unit = TranslationUnit {
            id: 1,
            entry_key: EntryKey::Id("1".to_string()),
            path: vec![PathSegment::Key("text".to_string())],
            kr: "이상은 [Tremor] 진동 효과를 얻는다 ".to_string(),
            jp: "振動".to_string(),
            en: "Tremor".to_string(),
            model: "YiSang".to_string(),
        };

        let rendered = user_prompt(
            &[unit],
            &descriptor("Story.json", "StoryData/KR_Story.json"),
            &rules,
        )
        .unwrap();
        let value: Value = serde_json::from_str(&rendered).unwrap();

        assert_eq!(value["glossary"][0]["translation"], "李箱");
        assert_eq!(value["affects"][0]["cn"], "震颤");
        assert_eq!(value["role_styles"][0]["id"], "YiSang");
        assert_eq!(value["text_blocks"][0]["affect_refs"][0], "[Tremor]");
    }
}
