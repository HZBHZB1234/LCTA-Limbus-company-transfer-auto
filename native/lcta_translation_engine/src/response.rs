use crate::error::{EngineError, Result};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeSet;

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct TranslationItem {
    pub id: usize,
    pub translation: String,
}

#[derive(Debug)]
pub struct ParsedTranslations {
    pub items: Vec<TranslationItem>,
    pub value: Value,
    pub repairs: Vec<String>,
}

pub fn parse_translations(raw: &str) -> Result<ParsedTranslations> {
    let normalized = raw.trim().trim_start_matches('\u{feff}').trim();
    let mut candidates = Vec::new();
    let mut seen = BTreeSet::new();
    push_candidate(
        &mut candidates,
        &mut seen,
        normalized.to_string(),
        Vec::new(),
    );

    if let Some(fenced) = strip_markdown_fence(normalized) {
        push_candidate(
            &mut candidates,
            &mut seen,
            fenced,
            vec!["markdown_fence_removed".to_string()],
        );
    }
    if let Some(extracted) = extract_balanced_json(normalized) {
        push_candidate(
            &mut candidates,
            &mut seen,
            extracted,
            vec!["embedded_json_extracted".to_string()],
        );
    }

    let mut last_error = None;
    let mut index = 0;
    while index < candidates.len() {
        let (candidate, repairs) = candidates[index].clone();
        match decode_candidate(&candidate) {
            Ok((items, value, decoded_string)) => {
                let mut repairs = repairs;
                if decoded_string {
                    repairs.push("json_string_unwrapped".to_string());
                }
                return Ok(ParsedTranslations {
                    items,
                    value,
                    repairs,
                });
            }
            Err(error) => last_error = Some(error.to_string()),
        }

        let mut repaired = candidate;
        let mut repaired_steps = repairs;
        for (name, repair) in [
            (
                "trailing_commas_removed",
                remove_trailing_commas as fn(&str) -> String,
            ),
            ("non_finite_numbers_replaced", replace_non_finite_numbers),
            (
                "single_quoted_strings_converted",
                convert_single_quoted_strings,
            ),
            ("control_characters_escaped", escape_control_characters),
        ] {
            let next = repair(&repaired);
            if next == repaired {
                continue;
            }
            repaired = next;
            repaired_steps.push(name.to_string());
            push_candidate(
                &mut candidates,
                &mut seen,
                repaired.clone(),
                repaired_steps.clone(),
            );
        }
        index += 1;
    }

    Err(EngineError::InvalidResponse(format!(
        "无法解析 translations JSON{}",
        last_error
            .map(|error| format!(": {error}"))
            .unwrap_or_default()
    )))
}

fn push_candidate(
    candidates: &mut Vec<(String, Vec<String>)>,
    seen: &mut BTreeSet<String>,
    candidate: String,
    repairs: Vec<String>,
) {
    if !candidate.is_empty() && seen.insert(candidate.clone()) {
        candidates.push((candidate, repairs));
    }
}

fn decode_candidate(candidate: &str) -> Result<(Vec<TranslationItem>, Value, bool)> {
    let value: Value = serde_json::from_str(candidate)?;
    if let Value::String(inner) = &value {
        let inner_value: Value = serde_json::from_str(inner)?;
        let items = items_from_value(&inner_value)?;
        return Ok((items, inner_value, true));
    }
    let items = items_from_value(&value)?;
    Ok((items, value, false))
}

fn items_from_value(value: &Value) -> Result<Vec<TranslationItem>> {
    let items_value = match value {
        Value::Object(object) => object.get("translations").cloned().ok_or_else(|| {
            EngineError::InvalidResponse("响应缺少 translations 字段".to_string())
        })?,
        Value::Array(_) => value.clone(),
        _ => {
            return Err(EngineError::InvalidResponse(
                "translations 响应必须是对象或数组".to_string(),
            ))
        }
    };
    serde_json::from_value(items_value).map_err(Into::into)
}

fn strip_markdown_fence(value: &str) -> Option<String> {
    let trimmed = value.trim();
    if !trimmed.starts_with("```") {
        return None;
    }
    let content_start = trimmed.find('\n').map(|index| index + 1)?;
    let content_end = trimmed.rfind("```")?;
    (content_end >= content_start).then(|| trimmed[content_start..content_end].trim().to_string())
}

fn extract_balanced_json(value: &str) -> Option<String> {
    let mut start = None;
    let mut stack = Vec::new();
    let mut quote = None;
    let mut escaped = false;
    for (index, character) in value.char_indices() {
        if let Some(active_quote) = quote {
            if escaped {
                escaped = false;
            } else if character == '\\' {
                escaped = true;
            } else if character == active_quote {
                quote = None;
            }
            continue;
        }
        if matches!(character, '"' | '\'') && start.is_some() {
            quote = Some(character);
            continue;
        }
        match character {
            '{' => {
                start.get_or_insert(index);
                stack.push('}');
            }
            '[' => {
                start.get_or_insert(index);
                stack.push(']');
            }
            '}' | ']' if start.is_some() => {
                if stack.pop() != Some(character) {
                    return None;
                }
                if stack.is_empty() {
                    return start
                        .map(|start| value[start..index + character.len_utf8()].to_string());
                }
            }
            _ => {}
        }
    }
    None
}

fn remove_trailing_commas(value: &str) -> String {
    let mut output = String::with_capacity(value.len());
    let mut quote = None;
    let mut escaped = false;
    let characters = value.char_indices().collect::<Vec<_>>();
    let mut position = 0;
    while position < characters.len() {
        let (_, character) = characters[position];
        if let Some(active_quote) = quote {
            output.push(character);
            if escaped {
                escaped = false;
            } else if character == '\\' {
                escaped = true;
            } else if character == active_quote {
                quote = None;
            }
            position += 1;
            continue;
        }
        if matches!(character, '"' | '\'') {
            quote = Some(character);
            output.push(character);
            position += 1;
            continue;
        }
        if character == ',' {
            let next = characters[position + 1..]
                .iter()
                .find(|(_, next)| !next.is_whitespace())
                .map(|(_, next)| *next);
            if matches!(next, Some('}' | ']')) {
                position += 1;
                continue;
            }
        }
        output.push(character);
        position += 1;
    }
    output
}

fn replace_non_finite_numbers(value: &str) -> String {
    let mut output = String::with_capacity(value.len());
    let mut quote = None;
    let mut escaped = false;
    let mut cursor = 0;
    while cursor < value.len() {
        let character = value[cursor..].chars().next().expect("valid cursor");
        if let Some(active_quote) = quote {
            output.push(character);
            cursor += character.len_utf8();
            if escaped {
                escaped = false;
            } else if character == '\\' {
                escaped = true;
            } else if character == active_quote {
                quote = None;
            }
            continue;
        }
        if matches!(character, '"' | '\'') {
            quote = Some(character);
            output.push(character);
            cursor += character.len_utf8();
            continue;
        }
        let remaining = &value[cursor..];
        let matched = ["-Infinity", "Infinity", "NaN"]
            .into_iter()
            .find(|token| remaining.starts_with(token) && token_boundary(remaining, token.len()));
        if let Some(token) = matched {
            output.push_str("null");
            cursor += token.len();
        } else {
            output.push(character);
            cursor += character.len_utf8();
        }
    }
    output
}

fn token_boundary(value: &str, end: usize) -> bool {
    value[end..]
        .chars()
        .next()
        .is_none_or(|character| !character.is_ascii_alphanumeric() && character != '_')
}

fn convert_single_quoted_strings(value: &str) -> String {
    let mut output = String::with_capacity(value.len());
    let mut in_double = false;
    let mut in_single = false;
    let mut escaped = false;
    let mut characters = value.chars().peekable();
    while let Some(character) = characters.next() {
        if in_double {
            output.push(character);
            if escaped {
                escaped = false;
            } else if character == '\\' {
                escaped = true;
            } else if character == '"' {
                in_double = false;
            }
            continue;
        }
        if in_single {
            if escaped {
                match character {
                    '\'' => output.push('\''),
                    '"' => output.push_str("\\\""),
                    _ => {
                        output.push('\\');
                        output.push(character);
                    }
                }
                escaped = false;
            } else if character == '\\' {
                escaped = true;
            } else if character == '\'' {
                let closes_string = characters.peek().is_none_or(|next| {
                    next.is_whitespace() || matches!(next, ',' | '}' | ']' | ':')
                });
                if closes_string {
                    output.push('"');
                    in_single = false;
                } else {
                    output.push('\'');
                }
            } else if character == '"' {
                output.push_str("\\\"");
            } else {
                output.push(character);
            }
            continue;
        }
        match character {
            '"' => {
                in_double = true;
                output.push(character);
            }
            '\'' => {
                in_single = true;
                output.push('"');
            }
            _ => output.push(character),
        }
    }
    if escaped {
        output.push('\\');
    }
    output
}

fn escape_control_characters(value: &str) -> String {
    let mut output = String::with_capacity(value.len());
    let mut in_string = false;
    let mut escaped = false;
    for character in value.chars() {
        if !in_string {
            output.push(character);
            if character == '"' {
                in_string = true;
            }
            continue;
        }
        if escaped {
            output.push(character);
            escaped = false;
            continue;
        }
        match character {
            '\\' => {
                output.push(character);
                escaped = true;
            }
            '"' => {
                output.push(character);
                in_string = false;
            }
            '\n' => output.push_str("\\n"),
            '\r' => output.push_str("\\r"),
            '\t' => output.push_str("\\t"),
            character if character < ' ' => {
                output.push_str(&format!("\\u{:04x}", character as u32));
            }
            _ => output.push(character),
        }
    }
    output
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_strict_envelope_and_array() {
        let envelope =
            parse_translations(r#"{"translations":[{"id":1,"translation":"你好"}]}"#).unwrap();
        assert_eq!(envelope.items[0].translation, "你好");
        assert!(envelope.repairs.is_empty());

        let array = parse_translations(r#"[{"id":2,"translation":"世界"}]"#).unwrap();
        assert_eq!(array.items[0].id, 2);
    }

    #[test]
    fn extracts_json_from_fence_and_explanation() {
        let parsed = parse_translations(
            "处理完成：\n```json\n{\"translations\":[{\"id\":1,\"translation\":\"包含 } 字符\"}]}\n```\n请查收",
        )
        .unwrap();
        assert_eq!(parsed.items[0].translation, "包含 } 字符");
        assert!(parsed
            .repairs
            .contains(&"embedded_json_extracted".to_string()));
    }

    #[test]
    fn repairs_trailing_commas_single_quotes_and_non_finite_values() {
        let parsed = parse_translations(
            "{'translations':[{'id':1,'translation':'你好','confidence':NaN,},],}",
        )
        .unwrap();
        assert_eq!(parsed.items[0].translation, "你好");
        assert!(parsed
            .repairs
            .contains(&"single_quoted_strings_converted".to_string()));
        assert!(parsed
            .repairs
            .contains(&"non_finite_numbers_replaced".to_string()));
        assert!(parsed
            .repairs
            .contains(&"trailing_commas_removed".to_string()));
    }

    #[test]
    fn preserves_apostrophes_inside_single_quoted_values() {
        let parsed =
            parse_translations("{'translations':[{'id':1,'translation':'Don\'t stop'}]}").unwrap();
        assert_eq!(parsed.items[0].translation, "Don't stop");
    }

    #[test]
    fn repairs_raw_control_characters_inside_strings() {
        let parsed = parse_translations(
            "{\"translations\":[{\"id\":1,\"translation\":\"第一行\n第二行\"}]}",
        )
        .unwrap();
        assert_eq!(parsed.items[0].translation, "第一行\n第二行");
        assert!(parsed
            .repairs
            .contains(&"control_characters_escaped".to_string()));
    }

    #[test]
    fn rejects_missing_translation_collection() {
        let error = parse_translations(r#"{"other":[]}"#).unwrap_err();
        assert!(error.to_string().contains("translations"));
    }
}
