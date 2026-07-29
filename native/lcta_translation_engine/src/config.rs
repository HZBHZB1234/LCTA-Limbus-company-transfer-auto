use serde::Deserialize;
use serde_json::{Map, Value};
use std::path::PathBuf;

fn default_file_concurrency() -> usize {
    12
}
fn default_request_concurrency() -> usize {
    16
}
fn default_file_io_concurrency() -> usize {
    32
}
fn default_max_prompt_chars() -> usize {
    18_000
}
fn default_timeout_seconds() -> u64 {
    120
}
fn default_max_retries() -> usize {
    3
}
fn default_true() -> bool {
    true
}
fn default_proper_endpoint() -> String {
    "https://paratranz.cn/api/projects/6860/terms".to_string()
}
fn default_page_size() -> usize {
    800
}
fn default_max_pages() -> usize {
    10
}
fn default_model() -> String {
    "gpt-4o-mini".to_string()
}
fn default_base_url() -> String {
    "https://api.openai.com/v1".to_string()
}

#[derive(Debug, Clone, Deserialize)]
pub struct RunConfig {
    pub game_path: PathBuf,
    pub output_dir: PathBuf,
    #[serde(default)]
    pub paths: PathOverrides,
    pub provider: ProviderConfig,
    #[serde(default)]
    pub concurrency: ConcurrencyConfig,
    #[serde(default)]
    pub pipeline: PipelineConfig,
    #[serde(default)]
    pub rules: RuleConfig,
}

#[derive(Debug, Clone, Default, Deserialize)]
pub struct PathOverrides {
    pub kr: Option<PathBuf>,
    pub jp: Option<PathBuf>,
    pub en: Option<PathBuf>,
    pub llc: Option<PathBuf>,
}

#[derive(Debug, Clone, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum ProviderConfig {
    OpenAiCompatible(OpenAiConfig),
    Null,
}

#[derive(Debug, Clone, Deserialize)]
pub struct OpenAiConfig {
    #[serde(default)]
    pub api_key: String,
    #[serde(default = "default_base_url")]
    pub base_url: String,
    #[serde(default = "default_model")]
    pub model: String,
    #[serde(default)]
    pub temperature: f64,
    pub max_tokens: Option<u64>,
    #[serde(default)]
    pub extra_body: Map<String, Value>,
    #[serde(default = "default_timeout_seconds")]
    pub timeout_seconds: u64,
    #[serde(default = "default_max_retries")]
    pub max_retries: usize,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ConcurrencyConfig {
    #[serde(default = "default_file_concurrency")]
    pub files: usize,
    #[serde(default = "default_request_concurrency")]
    pub requests: usize,
    #[serde(default = "default_file_io_concurrency")]
    pub file_io: usize,
}

impl Default for ConcurrencyConfig {
    fn default() -> Self {
        Self {
            files: default_file_concurrency(),
            requests: default_request_concurrency(),
            file_io: default_file_io_concurrency(),
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct PipelineConfig {
    #[serde(default = "default_true")]
    pub has_prefix: bool,
    #[serde(default = "default_true")]
    pub save_result: bool,
    #[serde(default = "default_max_prompt_chars")]
    pub max_prompt_chars: usize,
    #[serde(default)]
    pub enable_self_check: bool,
    #[serde(default = "default_true")]
    pub enable_rule_validation: bool,
}

impl Default for PipelineConfig {
    fn default() -> Self {
        Self {
            has_prefix: true,
            save_result: true,
            max_prompt_chars: default_max_prompt_chars(),
            enable_self_check: false,
            enable_rule_validation: true,
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct RuleConfig {
    #[serde(default)]
    pub enable_proper: bool,
    #[serde(default)]
    pub enable_role: bool,
    #[serde(default)]
    pub enable_skill: bool,
    #[serde(default)]
    pub auto_fetch_proper: bool,
    pub proper_path: Option<PathBuf>,
    #[serde(default = "default_proper_endpoint")]
    pub proper_endpoint: String,
    #[serde(default = "default_page_size")]
    pub proper_page_size: usize,
    #[serde(default = "default_max_pages")]
    pub proper_max_pages: usize,
}

impl Default for RuleConfig {
    fn default() -> Self {
        Self {
            enable_proper: false,
            enable_role: false,
            enable_skill: false,
            auto_fetch_proper: false,
            proper_path: None,
            proper_endpoint: default_proper_endpoint(),
            proper_page_size: default_page_size(),
            proper_max_pages: default_max_pages(),
        }
    }
}

#[derive(Debug, Clone)]
pub struct ResolvedPaths {
    pub kr: PathBuf,
    pub jp: PathBuf,
    pub en: PathBuf,
    pub llc: PathBuf,
    pub output: PathBuf,
}

impl RunConfig {
    pub fn resolve_paths(&self) -> ResolvedPaths {
        let assets = self
            .game_path
            .join("LimbusCompany_Data")
            .join("Assets")
            .join("Resources_moved")
            .join("Localize");
        let lang = self.game_path.join("LimbusCompany_Data").join("lang");
        ResolvedPaths {
            kr: self.paths.kr.clone().unwrap_or_else(|| assets.join("kr")),
            jp: self.paths.jp.clone().unwrap_or_else(|| assets.join("jp")),
            en: self.paths.en.clone().unwrap_or_else(|| assets.join("en")),
            llc: self
                .paths
                .llc
                .clone()
                .unwrap_or_else(|| lang.join("LLC_zh-CN")),
            output: self.output_dir.join("LLc-CN-LCTA"),
        }
    }
}
