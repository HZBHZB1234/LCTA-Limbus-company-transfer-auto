use std::collections::{BTreeSet, HashMap, VecDeque};

#[derive(Debug, Clone, Default)]
pub struct AhoMatcher {
    nodes: Vec<Node>,
}

#[derive(Debug, Clone, Default)]
struct Node {
    transitions: HashMap<char, usize>,
    failure: usize,
    outputs: Vec<usize>,
}

impl AhoMatcher {
    pub fn build<I, S>(patterns: I) -> Self
    where
        I: IntoIterator<Item = (S, usize)>,
        S: AsRef<str>,
    {
        let mut matcher = Self {
            nodes: vec![Node::default()],
        };
        for (pattern, value) in patterns {
            let pattern = pattern.as_ref();
            if pattern.is_empty() {
                continue;
            }
            let mut state = 0;
            for character in pattern.chars() {
                let next = if let Some(next) = matcher.nodes[state].transitions.get(&character) {
                    *next
                } else {
                    let next = matcher.nodes.len();
                    matcher.nodes.push(Node::default());
                    matcher.nodes[state].transitions.insert(character, next);
                    next
                };
                state = next;
            }
            matcher.nodes[state].outputs.push(value);
        }
        matcher.build_failure_links();
        matcher
    }

    pub fn search(&self, text: &str) -> Vec<usize> {
        if self.nodes.is_empty() {
            return Vec::new();
        }
        let mut state = 0;
        let mut matches = BTreeSet::new();
        for character in text.chars() {
            while state != 0 && !self.nodes[state].transitions.contains_key(&character) {
                state = self.nodes[state].failure;
            }
            if let Some(next) = self.nodes[state].transitions.get(&character) {
                state = *next;
            } else {
                state = 0;
            }
            matches.extend(self.nodes[state].outputs.iter().copied());
        }
        matches.into_iter().collect()
    }

    fn build_failure_links(&mut self) {
        let mut queue = VecDeque::new();
        let root_children = self.nodes[0]
            .transitions
            .values()
            .copied()
            .collect::<Vec<_>>();
        for child in root_children {
            queue.push_back(child);
        }

        while let Some(state) = queue.pop_front() {
            let transitions = self.nodes[state]
                .transitions
                .iter()
                .map(|(character, next)| (*character, *next))
                .collect::<Vec<_>>();
            for (character, next) in transitions {
                queue.push_back(next);
                let mut failure = self.nodes[state].failure;
                while failure != 0 && !self.nodes[failure].transitions.contains_key(&character) {
                    failure = self.nodes[failure].failure;
                }
                if let Some(target) = self.nodes[failure].transitions.get(&character) {
                    self.nodes[next].failure = *target;
                }
                let inherited = self.nodes[self.nodes[next].failure].outputs.clone();
                self.nodes[next].outputs.extend(inherited);
                self.nodes[next].outputs.sort_unstable();
                self.nodes[next].outputs.dedup();
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn finds_overlapping_unicode_patterns_once() {
        let matcher = AhoMatcher::build([("震颤", 0), ("颤", 1), ("Burn", 2)]);
        assert_eq!(matcher.search("震颤与Burn震颤"), vec![0, 1, 2]);
    }
}
