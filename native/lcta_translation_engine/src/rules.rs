use crate::config::RuleConfig;
use crate::document::LocaleDocument;
use crate::error::{EngineError, Result};
use crate::matcher::AhoMatcher;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::{BTreeSet, HashMap};
use std::path::Path;
use std::sync::Arc;
use std::time::Duration;
use tokio::task::JoinSet;

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ProperTerm {
    #[serde(default)]
    pub term: String,
    #[serde(default)]
    pub translation: String,
    #[serde(default)]
    pub note: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct RoleRule {
    pub id: String,
    pub kr: String,
    pub cn: String,
    #[serde(rename = "nickName")]
    pub nickname: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct AffectRule {
    pub id: String,
    pub kr: String,
    pub jp: String,
    pub en: String,
    pub cn: String,
    pub desc: String,
}

#[derive(Debug, Clone, Default)]
pub struct UnitReferences {
    pub proper: Vec<ProperTerm>,
    pub affects: Vec<AffectRule>,
    pub roles: Vec<RoleRule>,
}

#[derive(Debug, Clone, Default)]
pub struct RuleSnapshot {
    proper: Arc<Vec<ProperTerm>>,
    roles: Arc<Vec<RoleRule>>,
    affects: Arc<Vec<AffectRule>>,
    proper_matcher: Arc<AhoMatcher>,
    role_matcher: Arc<AhoMatcher>,
    affect_id_matcher: Arc<AhoMatcher>,
    affect_name_matcher: Arc<AhoMatcher>,
    role_by_id: Arc<HashMap<String, usize>>,
    affect_by_id: Arc<HashMap<String, usize>>,
}

impl RuleSnapshot {
    pub fn with_proper_terms(mut self, terms: Vec<ProperTerm>) -> Self {
        let matcher = AhoMatcher::build(
            terms
                .iter()
                .enumerate()
                .filter(|(_, term)| !term.term.is_empty())
                .map(|(index, term)| (term.term.as_str(), index)),
        );
        self.proper = Arc::new(terms);
        self.proper_matcher = Arc::new(matcher);
        self
    }

    pub fn with_roles(mut self, roles: Vec<RoleRule>) -> Self {
        let matcher = AhoMatcher::build(
            roles
                .iter()
                .enumerate()
                .filter(|(_, role)| !role.id.is_empty())
                .map(|(index, role)| (role.id.as_str(), index)),
        );
        self.role_by_id = Arc::new(
            roles
                .iter()
                .enumerate()
                .map(|(index, role)| (role.id.clone(), index))
                .collect(),
        );
        self.roles = Arc::new(roles);
        self.role_matcher = Arc::new(matcher);
        self
    }

    pub fn with_affects(mut self, affects: Vec<AffectRule>) -> Self {
        let id_matcher = AhoMatcher::build(
            affects
                .iter()
                .enumerate()
                .filter(|(_, affect)| !affect.id.is_empty())
                .map(|(index, affect)| (format!("[{}]", affect.id), index)),
        );
        let name_matcher = AhoMatcher::build(
            affects
                .iter()
                .enumerate()
                .filter(|(_, affect)| !affect.kr.is_empty())
                .map(|(index, affect)| (format!("{} ", affect.kr), index)),
        );
        self.affect_by_id = Arc::new(
            affects
                .iter()
                .enumerate()
                .map(|(index, affect)| (affect.id.clone(), index))
                .collect(),
        );
        self.affects = Arc::new(affects);
        self.affect_id_matcher = Arc::new(id_matcher);
        self.affect_name_matcher = Arc::new(name_matcher);
        self
    }

    pub fn references_for(&self, kr: &str, jp: &str, en: &str, model: &str) -> UnitReferences {
        let proper = self
            .proper_matcher
            .search(kr)
            .into_iter()
            .filter_map(|index| self.proper.get(index).cloned())
            .collect();

        let mut affect_indices = BTreeSet::new();
        affect_indices.extend(self.affect_id_matcher.search(kr));
        for index in self.affect_name_matcher.search(kr) {
            let Some(affect) = self.affects.get(index) else {
                continue;
            };
            let has_reference_language_match =
                (!affect.jp.is_empty() && !jp.is_empty() && jp != kr && jp.contains(&affect.jp))
                    || (!affect.en.is_empty()
                        && !en.is_empty()
                        && en != kr
                        && en.to_lowercase().contains(&affect.en.to_lowercase()));
            let lacks_reference_language = (affect.jp.is_empty() || jp.is_empty() || jp == kr)
                && (affect.en.is_empty() || en.is_empty() || en == kr);
            if has_reference_language_match || lacks_reference_language {
                affect_indices.insert(index);
            }
        }
        let affects = affect_indices
            .into_iter()
            .filter_map(|index| self.affects.get(index).cloned())
            .collect();

        let mut role_indices = BTreeSet::new();
        if let Some(index) = self.role_by_id.get(model) {
            role_indices.insert(*index);
        } else if model.is_empty() {
            role_indices.extend(self.role_matcher.search(kr));
        }
        let roles = role_indices
            .into_iter()
            .filter_map(|index| self.roles.get(index).cloned())
            .collect();

        UnitReferences {
            proper,
            affects,
            roles,
        }
    }

    pub fn effect_cn_name(&self, id: &str) -> Option<&str> {
        self.affect_by_id
            .get(id)
            .and_then(|index| self.affects.get(*index))
            .map(|affect| affect.cn.as_str())
            .filter(|name| !name.is_empty())
    }

    pub fn proper_count(&self) -> usize {
        self.proper.len()
    }

    pub fn role_count(&self) -> usize {
        self.roles.len()
    }

    pub fn affect_count(&self) -> usize {
        self.affects.len()
    }
}

#[derive(Debug, Deserialize)]
struct ProperPage {
    #[serde(default)]
    results: Vec<ProperTerm>,
}

pub async fn load_proper_terms(config: &RuleConfig) -> Result<Vec<ProperTerm>> {
    if !config.enable_proper {
        return Ok(Vec::new());
    }
    if config.auto_fetch_proper {
        return fetch_proper_terms(config).await;
    }
    let path = config
        .proper_path
        .as_deref()
        .ok_or_else(|| EngineError::Config("启用本地专有名词时必须提供 proper_path".to_string()))?;
    let bytes = tokio::fs::read(path).await?;
    parse_proper_terms(&bytes)
}

async fn fetch_proper_terms(config: &RuleConfig) -> Result<Vec<ProperTerm>> {
    let client = reqwest::Client::builder()
        .pool_max_idle_per_host(config.proper_max_pages.max(1))
        .tcp_keepalive(Duration::from_secs(60))
        .build()?;
    let mut tasks = JoinSet::new();
    for page in 1..=config.proper_max_pages.max(1) {
        let client = client.clone();
        let endpoint = config.proper_endpoint.clone();
        let page_size = config.proper_page_size.max(1);
        tasks.spawn(async move {
            let response = client
                .get(endpoint)
                .query(&[("pageSize", page_size), ("page", page)])
                .timeout(Duration::from_secs(20))
                .send()
                .await?
                .error_for_status()?;
            let payload = response.json::<ProperPage>().await?;
            Ok::<_, reqwest::Error>((page, payload.results))
        });
    }

    let mut pages = Vec::new();
    while let Some(result) = tasks.join_next().await {
        let (page, terms) = result
            .map_err(|error| EngineError::Config(format!("专有名词抓取任务失败: {error}")))??;
        pages.push((page, terms));
    }
    pages.sort_by_key(|(page, _)| *page);
    let mut output = Vec::new();
    for (_, terms) in pages {
        if terms.is_empty() {
            break;
        }
        output.extend(terms.into_iter().filter(|term| !term.term.is_empty()));
    }
    Ok(output)
}

fn parse_proper_terms(bytes: &[u8]) -> Result<Vec<ProperTerm>> {
    let bytes = bytes.strip_prefix(&[0xEF, 0xBB, 0xBF]).unwrap_or(bytes);
    let value: Value = serde_json::from_slice(bytes)?;
    let values = match value {
        Value::Array(values) => values,
        Value::Object(mut object) => object
            .remove("results")
            .or_else(|| object.remove("terms"))
            .and_then(|value| value.as_array().cloned())
            .unwrap_or_default(),
        _ => Vec::new(),
    };
    values
        .into_iter()
        .map(serde_json::from_value)
        .collect::<std::result::Result<Vec<_>, _>>()
        .map(|terms| {
            terms
                .into_iter()
                .filter(|term: &ProperTerm| !term.term.is_empty())
                .collect()
        })
        .map_err(Into::into)
}

pub async fn load_roles_from_files(kr: &Path, cn: &Path) -> Result<Vec<RoleRule>> {
    let (kr, cn) = tokio::join!(load_document(kr), load_document_optional(cn));
    let kr = kr?;
    let cn = cn?;
    let mut roles = Vec::new();
    for (position, kr_entry) in kr.entries.iter().enumerate() {
        let key = kr.key_at(position);
        let cn_entry = cn.entry(&key).unwrap_or(kr_entry);
        let id = field_string(kr_entry, "id");
        if id.is_empty() {
            continue;
        }
        roles.push(RoleRule {
            id,
            kr: field_string(kr_entry, "name"),
            cn: field_string(cn_entry, "name"),
            nickname: field_string(cn_entry, "nickName"),
        });
    }
    Ok(roles)
}

pub async fn load_affects_from_files(
    kr: &Path,
    jp: &Path,
    en: &Path,
    cn: &Path,
) -> Result<Vec<AffectRule>> {
    let (kr, jp, en, cn) = tokio::join!(
        load_document(kr),
        load_document_optional(jp),
        load_document_optional(en),
        load_document_optional(cn),
    );
    let kr = kr?;
    let jp = jp?;
    let en = en?;
    let cn = cn?;
    let mut affects = Vec::new();
    for (position, kr_entry) in kr.entries.iter().enumerate() {
        let key = kr.key_at(position);
        let jp_entry = jp.entry(&key);
        let en_entry = en.entry(&key);
        let cn_entry = cn.entry(&key).unwrap_or(kr_entry);
        let id = field_string(kr_entry, "id");
        if id.is_empty() {
            continue;
        }
        affects.push(AffectRule {
            id,
            kr: field_string(kr_entry, "name"),
            jp: jp_entry
                .map(|entry| field_string(entry, "name"))
                .unwrap_or_default(),
            en: en_entry
                .map(|entry| field_string(entry, "name"))
                .unwrap_or_default(),
            cn: field_string(cn_entry, "name"),
            desc: field_string(cn_entry, "desc"),
        });
    }
    Ok(affects)
}

async fn load_document(path: &Path) -> Result<LocaleDocument> {
    LocaleDocument::parse(&tokio::fs::read(path).await?)
}

async fn load_document_optional(path: &Path) -> Result<LocaleDocument> {
    match tokio::fs::read(path).await {
        Ok(bytes) => LocaleDocument::parse(&bytes),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(LocaleDocument::empty()),
        Err(error) => Err(error.into()),
    }
}

fn field_string(value: &Value, key: &str) -> String {
    match value.get(key) {
        Some(Value::String(value)) => value.clone(),
        Some(Value::Number(value)) => value.to_string(),
        Some(Value::Bool(value)) => value.to_string(),
        _ => String::new(),
    }
}

pub fn bracket_tokens(text: &str) -> Vec<&str> {
    delimited_tokens(text, '[', ']')
}

pub fn validate_translation(
    source: &str,
    jp: &str,
    en: &str,
    translation: &str,
    snapshot: &RuleSnapshot,
) -> bool {
    translation_validation_errors(source, jp, en, translation, snapshot).is_empty()
}

pub fn translation_validation_errors(
    source: &str,
    jp: &str,
    en: &str,
    translation: &str,
    snapshot: &RuleSnapshot,
) -> Vec<String> {
    let mut errors = Vec::new();
    if translation.trim().is_empty() {
        errors.push("translation_is_empty".to_string());
        return errors;
    }
    for token in bracket_tokens(source) {
        let inner = token.trim_matches(['[', ']']);
        if is_identifier(inner) {
            if let Some(cn_name) = snapshot.effect_cn_name(inner) {
                if translation.contains(token) || translation.contains(cn_name) {
                    continue;
                }
            }
        }
        if !translation.contains(token) {
            errors.push(format!("missing_bracket_token:{token}"));
        }
    }
    for source_text in [source, jp, en] {
        for effect_id in effect_ids(source_text) {
            let token = format!("[{effect_id}]");
            if translation.contains(&token)
                || snapshot
                    .effect_cn_name(effect_id)
                    .is_some_and(|name| translation.contains(name))
            {
                continue;
            }
            errors.push(format!("missing_effect_reference:{effect_id}"));
        }
    }
    for token in delimited_tokens(source, '<', '>') {
        if !translation.contains(token) {
            errors.push(format!("missing_tag:{token}"));
        }
    }
    for token in delimited_tokens(source, '{', '}') {
        if !translation.contains(token) {
            errors.push(format!("missing_placeholder:{token}"));
        }
    }
    for number in numeric_tokens(source) {
        if !translation.contains(number) {
            errors.push(format!("missing_number:{number}"));
        }
    }
    errors.sort();
    errors.dedup();
    errors
}

pub fn normalize_bracket_spacing(text: &str) -> String {
    let mut output = String::with_capacity(text.len());
    let mut cursor = 0;
    while let Some(relative_open) = text[cursor..].find('[') {
        let open = cursor + relative_open;
        output.push_str(&text[cursor..open]);
        let Some(relative_close) = text[open + 1..].find(']') else {
            output.push_str(&text[open..]);
            return output;
        };
        let close = open + 1 + relative_close;
        let inner = &text[open + 1..close];
        let trimmed = inner.trim();
        if inner == trimmed || trimmed.is_empty() {
            output.push_str(&text[open..=close]);
        } else if is_identifier(trimmed) {
            output.push('[');
            output.push_str(trimmed);
            output.push(']');
        } else {
            output.push_str(trimmed);
            output.push(' ');
        }
        cursor = close + 1;
    }
    output.push_str(&text[cursor..]);
    output
}

fn delimited_tokens(text: &str, open: char, close: char) -> Vec<&str> {
    let mut tokens = Vec::new();
    let mut start = None;
    for (index, character) in text.char_indices() {
        if character == open && start.is_none() {
            start = Some(index);
        } else if character == close {
            if let Some(open_index) = start.take() {
                let end = index + character.len_utf8();
                if let Some(token) = text.get(open_index..end) {
                    tokens.push(token);
                }
            }
        }
    }
    tokens
}

fn effect_ids(text: &str) -> Vec<&str> {
    bracket_tokens(text)
        .into_iter()
        .map(|token| token.trim_matches(['[', ']']))
        .filter(|token| is_identifier(token))
        .collect()
}

fn numeric_tokens(text: &str) -> Vec<&str> {
    let mut output = Vec::new();
    let mut start = None;
    for (index, character) in text.char_indices() {
        if character.is_ascii_digit() || (start.is_some() && matches!(character, '.' | ',' | '%')) {
            start.get_or_insert(index);
        } else if let Some(number_start) = start.take() {
            output.push(&text[number_start..index]);
        }
    }
    if let Some(number_start) = start {
        output.push(&text[number_start..]);
    }
    output
}

fn is_identifier(value: &str) -> bool {
    let mut chars = value.chars();
    matches!(chars.next(), Some(first) if first.is_ascii_alphabetic())
        && chars.all(|character| character.is_ascii_alphanumeric() || character == '_')
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn preserves_known_effect_by_id_or_chinese_name() {
        let snapshot = RuleSnapshot::default().with_affects(vec![AffectRule {
            id: "Tremor".to_string(),
            kr: "진동".to_string(),
            jp: String::new(),
            en: String::new(),
            cn: "震颤".to_string(),
            desc: String::new(),
        }]);
        assert!(validate_translation(
            "[Tremor] 2 부여",
            "",
            "",
            "施加2层震颤 ",
            &snapshot,
        ));
        assert!(!validate_translation(
            "[Unknown] 2 부여",
            "",
            "",
            "施加2层效果",
            &snapshot,
        ));
    }

    #[test]
    fn fixes_skill_bracket_spacing() {
        assert_eq!(
            normalize_bracket_spacing("[ Effect_ID ] 触发"),
            "[Effect_ID] 触发"
        );
        assert_eq!(normalize_bracket_spacing("[ 震颤 ]触发"), "震颤 触发");
    }
}
