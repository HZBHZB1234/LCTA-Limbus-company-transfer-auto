use thiserror::Error;

#[derive(Debug, Error)]
pub enum EngineError {
    #[error("配置错误: {0}")]
    Config(String),
    #[error("文件操作失败: {0}")]
    Io(#[from] std::io::Error),
    #[error("JSON 解析失败: {0}")]
    Json(#[from] serde_json::Error),
    #[error("网络请求失败: {0}")]
    Network(#[from] reqwest::Error),
    #[error("API 返回错误: HTTP {status}: {body}")]
    Api { status: u16, body: String },
    #[error("翻译响应格式错误: {0}")]
    InvalidResponse(String),
    #[error("任务已取消")]
    Cancelled,
}

pub type Result<T> = std::result::Result<T, EngineError>;
