use crate::error::{EngineError, Result};
use serde_json::{Map, Value};
use std::collections::{BTreeMap, HashMap};

const AVOID_KEYS: &[&str] = &["usage", "id", "model"];

#[derive(Debug, Clone, Hash, PartialEq, Eq)]
pub enum EntryKey {
    Id(String),
    Position(usize),
}

#[derive(Debug, Clone, Hash, PartialEq, Eq)]
pub enum PathSegment {
    Key(String),
    Index(usize),
}

#[derive(Debug, Clone)]
pub struct FlatText {
    pub path: Vec<PathSegment>,
    pub text: String,
}

#[derive(Debug, Clone)]
pub struct LocaleDocument {
    pub root: Value,
    pub entries: Vec<Value>,
    pub index: HashMap<EntryKey, usize>,
}

impl LocaleDocument {
    pub fn parse(bytes: &[u8]) -> Result<Self> {
        let bytes = bytes.strip_prefix(&[0xEF, 0xBB, 0xBF]).unwrap_or(bytes);
        let root: Value = serde_json::from_slice(bytes)?;
        let entries = match &root {
            Value::Object(object) => object
                .get("dataList")
                .and_then(Value::as_array)
                .cloned()
                .unwrap_or_default(),
            Value::Array(array) => array.clone(),
            _ => Vec::new(),
        };
        let uses_ids = entries
            .first()
            .and_then(Value::as_object)
            .is_some_and(|object| object.contains_key("id"));
        let mut index = HashMap::with_capacity(entries.len());
        for (position, entry) in entries.iter().enumerate() {
            let key = if uses_ids {
                let id = entry.get("id").and_then(Value::as_str).ok_or_else(|| {
                    EngineError::InvalidResponse("dataList 中存在无 id 条目".to_string())
                })?;
                EntryKey::Id(id.to_string())
            } else {
                EntryKey::Position(position)
            };
            index.insert(key, position);
        }
        Ok(Self {
            root,
            entries,
            index,
        })
    }

    pub fn empty() -> Self {
        Self {
            root: Value::Object(Map::new()),
            entries: Vec::new(),
            index: HashMap::new(),
        }
    }

    pub fn entry(&self, key: &EntryKey) -> Option<&Value> {
        self.index
            .get(key)
            .and_then(|position| self.entries.get(*position))
    }

    pub fn key_at(&self, position: usize) -> EntryKey {
        self.index
            .iter()
            .find_map(|(key, value)| (*value == position).then(|| key.clone()))
            .unwrap_or(EntryKey::Position(position))
    }

    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }
}

pub fn flatten_strings(value: &Value) -> Vec<FlatText> {
    let mut output = Vec::new();
    flatten_into(value, &mut Vec::new(), &mut output);
    output
}

fn flatten_into(value: &Value, path: &mut Vec<PathSegment>, output: &mut Vec<FlatText>) {
    match value {
        Value::Object(object) => {
            for (key, child) in object {
                if AVOID_KEYS.contains(&key.as_str()) {
                    continue;
                }
                path.push(PathSegment::Key(key.clone()));
                flatten_into(child, path, output);
                path.pop();
            }
        }
        Value::Array(array) => {
            for (index, child) in array.iter().enumerate() {
                path.push(PathSegment::Index(index));
                flatten_into(child, path, output);
                path.pop();
            }
        }
        Value::String(text) if !text.is_empty() && text != "-" => {
            output.push(FlatText {
                path: path.clone(),
                text: text.clone(),
            });
        }
        _ => {}
    }
}

pub fn flatten_map(value: &Value) -> BTreeMap<String, String> {
    flatten_strings(value)
        .into_iter()
        .map(|item| (path_key(&item.path), item.text))
        .collect()
}

pub fn path_key(path: &[PathSegment]) -> String {
    path.iter()
        .map(|segment| match segment {
            PathSegment::Key(key) => format!("k:{key}"),
            PathSegment::Index(index) => format!("i:{index}"),
        })
        .collect::<Vec<_>>()
        .join("/")
}

pub fn set_string_at_path(value: &mut Value, path: &[PathSegment], replacement: String) -> bool {
    if path.is_empty() {
        *value = Value::String(replacement);
        return true;
    }
    let mut current = value;
    for segment in &path[..path.len() - 1] {
        current = match segment {
            PathSegment::Key(key) => match current
                .as_object_mut()
                .and_then(|object| object.get_mut(key))
            {
                Some(child) => child,
                None => return false,
            },
            PathSegment::Index(index) => match current
                .as_array_mut()
                .and_then(|array| array.get_mut(*index))
            {
                Some(child) => child,
                None => return false,
            },
        };
    }
    match path.last() {
        Some(PathSegment::Key(key)) => current
            .as_object_mut()
            .and_then(|object| object.get_mut(key))
            .map(|slot| *slot = Value::String(replacement))
            .is_some(),
        Some(PathSegment::Index(index)) => current
            .as_array_mut()
            .and_then(|array| array.get_mut(*index))
            .map(|slot| *slot = Value::String(replacement))
            .is_some(),
        None => false,
    }
}

pub fn build_output_root(original: &Value, entries: Vec<Value>) -> Value {
    match original {
        Value::Array(_) => Value::Array(entries),
        Value::Object(object) => {
            let mut result = object.clone();
            result.insert("dataList".to_string(), Value::Array(entries));
            Value::Object(result)
        }
        _ => {
            let mut result = Map::new();
            result.insert("dataList".to_string(), Value::Array(entries));
            Value::Object(result)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn flattens_and_updates_nested_strings() {
        let mut value = json!({"id":"A", "name":"원문", "nested":[{"desc":"설명"}]});
        let flattened = flatten_strings(&value);
        assert_eq!(flattened.len(), 2);
        assert!(set_string_at_path(
            &mut value,
            &flattened[0].path,
            "译文".to_string()
        ));
        assert_eq!(value["name"], "译文");
    }
}
