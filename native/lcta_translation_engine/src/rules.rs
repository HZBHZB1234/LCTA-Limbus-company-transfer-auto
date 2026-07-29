pub fn bracket_tokens(text: &str) -> Vec<&str> {
    let mut tokens = Vec::new();
    let mut start = None;
    for (index, byte) in text.as_bytes().iter().enumerate() {
        match (*byte, start) {
            (b'[', None) => start = Some(index),
            (b']', Some(open)) => {
                if let Some(token) = text.get(open..=index) {
                    tokens.push(token);
                }
                start = None;
            }
            _ => {}
        }
    }
    tokens
}

pub fn validate_translation(source: &str, translation: &str) -> bool {
    !translation.trim().is_empty()
        && bracket_tokens(source)
            .into_iter()
            .all(|token| translation.contains(token))
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

fn is_identifier(value: &str) -> bool {
    let mut chars = value.chars();
    matches!(chars.next(), Some(first) if first.is_ascii_alphabetic())
        && chars.all(|character| character.is_ascii_alphanumeric() || character == '_')
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn preserves_bracket_tokens() {
        assert!(validate_translation("[Hit] 공격", "[Hit] 攻击"));
        assert!(!validate_translation("[Hit] 공격", "攻击"));
    }

    #[test]
    fn fixes_skill_bracket_spacing() {
        assert_eq!(
            normalize_bracket_spacing("[ Effect_ID ] 발동"),
            "[Effect_ID] 발동"
        );
        assert_eq!(normalize_bracket_spacing("[ 震颤 ]触发"), "震颤 触发");
    }
}
