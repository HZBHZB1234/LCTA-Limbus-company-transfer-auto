# 公告汉化服务端（参考实现）

给 LCTA 的「公告汉化」功能自建翻译服务用。**不属于 LCTA 运行时**，是独立进程，
可以放在任意机器上跑。HTTP 层为 **FastAPI + Uvicorn**（Python 3.9+），
LLM 输出解析用 **json_repair** 容错；`store` / `pipeline` / `config` 为纯标准库实现。

## 它做什么

LCTA 客户端只把**官方公告文件名**发过来（无需鉴权），服务端负责：

1. 查译文缓存 → 命中就直接返回整篇译好的公告 JSON；
2. 未命中 → 拉官方原文 → 交给大模型翻译 → 自检 → 落盘，然后返回译文；
3. 翻译是**异步**的：首次请求立刻回 `pending` 并在后台翻译，
   客户端会按指数退避自动重试同一文件名，重试时命中缓存即拿到 `ok`。

所以单个请求永远秒回，不会挂住连接，服务端也不需要长轮询。

## 快速开始

先装依赖（只需要跑服务端的机器装）：

```bash
pip install -r tools/notice_server/requirements.txt
```

不配 API Key，用假后端把「客户端 ↔ 服务端」链路跑通：

```bash
python -m tools.notice_server.server --backend fake
```

输出里会给出监听地址（默认 `http://127.0.0.1:8000`）。把这个地址填进
LCTA「公告汉化」页面的**服务地址**，点「测试服务连接」和「开始同步并汉化」。

假后端给每段文本加 `【中】` 前缀，产物形如 `【中】Official Twitter` ——
客户端会正常收下，但游戏里看到的就是这个，只用来确认链路通不通。

确认没问题后换成真实后端：

```bash
cp tools/notice_server/config.example.json tools/notice_server/config.json
# 编辑 config.json，填 translate.api_key / base_url / model
python -m tools.notice_server.server --config tools/notice_server/config.json
```

也可以不写配置文件，全部走命令行 / 环境变量：

```bash
export LCTA_NOTICE_API_KEY=sk-xxxx
python -m tools.notice_server.server \
    --base-url https://api.deepseek.com/v1 --model deepseek-chat
```

浏览器打开服务地址（`http://127.0.0.1:8000/`）可以看到状态页：缓存了多少篇、
正在翻译哪些、最近一次失败原因。`/docs` 是 FastAPI 自带的交互式接口文档页
（无需额外配置）。

## 接口协议

```
GET {任意前缀}/{官方文件名}
```

路径前缀随便写（LCTA 侧的「请求路径模板」可配，默认 `/noticeDetails/{file}`），
服务端只取最后一段做文件名，并要求它匹配
`noticeDetail_<id>_<KR|EN|JP>_<rev>.json` —— 这条白名单同时挡住了路径穿越。

响应恒为 HTTP 200 + JSON 信封：

```json
{"status": "ok",      "data": { …整篇公告 JSON… }}
{"status": "pending", "message": "未命中缓存，正在翻译"}
{"status": "error",   "message": "TranslationError: 翻译接口返回 HTTP 401 …"}
```

`data` 与官方 `NoticeDetail` 同结构，只有 `title` 与
`content.list[*].formatValue` 被换成中文；`id` / `noticeType` / `startDate` /
`endDate` / `sprList` / 每个条目的 `formatKey` 全部原样保留。

`/`、`/status`、`/healthz` 返回状态 JSON（不是公告信封）；`/docs` 为接口文档页。

## 翻译规则（写死在 `translator.py`）

| 字段 | 处理 |
| --- | --- |
| `title` | 翻译 |
| `content.list[*].formatValue`，`formatKey` = `Text` | 翻译，保留换行与 `●`/`※`/`-`/编号 |
| 同上，`formatKey` = `SubTitle` | 翻译；`<...>` / `[...]` 包裹**确定性地**还原，不依赖模型听话 |
| 同上，`formatKey` = `HyperLink` | **不翻译**（裸 URL，如 `https://twitter.com/LimbusCompany_B`） |
| `id` / `noticeType` / `sprList` / `formatKey` / 日期 | 一律不动 |

一次请求把所有待译文本打包成 JSON 数组发给模型，要求**等长数组**返回。
模型输出先经三级容错解析：剥 `<think>` 标签 / 代码围栏 → 严格 `json.loads` →
`json_repair` 修复（**截断、未转义换行、单引号、尾逗号、前后废话**都能救回）；
修不回来或**长度 / 类型不符**才重试（默认 2 次），重试耗尽则回 `error` ——
**宁可报错也不缓存一篇结构错乱的公告**（客户端的硬门也会拒收，但那时看不出真正原因）。

## 配置项

默认值集中在 `config.py`（`DEFAULT_CONFIG`），加载顺序：默认值 < `config.json`
（`translate` 子对象深合并）< CLI 参数；密钥额外支持环境变量。

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `host` / `port` | `127.0.0.1` / `8000` | 监听地址。要给别的机器用改成 `0.0.0.0` |
| `cache_dir` | `cache` | 译文缓存目录，一篇公告一个 JSON |
| `official_base_url` | 官方公告 CDN | 官方原文来源 |
| `official_timeout` | `30` | 拉官方原文超时（秒） |
| `max_concurrency` | `2` | 同时翻译的公告数上限 |
| `translate.backend` | `openai` | `openai` 或 `fake` |
| `translate.base_url` | — | OpenAI 兼容接口地址（DeepSeek / OpenAI / Ollama / vLLM） |
| `translate.api_key` | — | 密钥；留空则不发 `Authorization` 头（本地 Ollama 用） |
| `translate.model` | — | 模型名 |
| `translate.timeout` | `120` | 单次翻译请求超时（秒） |
| `translate.max_retries` | `2` | 失败重试次数 |
| `translate.target_language` | `简体中文` | 目标语言，写进提示词 |
| `translate.temperature` | `0.2` | 采样温度 |

密钥也可用环境变量 `LCTA_NOTICE_API_KEY` 或 `OPENAI_API_KEY`（配置文件优先）。

## 常见问题

**一直回 `pending`，客户端等满 60 秒后说「服务端未就绪」**
翻译没成功。打开状态页看 `last_errors`，或看服务端 stderr 日志。
最常见的是没配 `api_key`（接口回 401）或 `base_url` / `model` 写错。

**客户端报「服务可用，但该公告尚未命中缓存」**
这是**正常**的：连通性测试只发一次请求，首次必然是未命中。同步时会自动等待重试。

**模型把 `<Official Twitter>` 的尖括号弄丢了**
不用管。包裹符号由 `restore_wrapper()` 按原文形式重新套上，不看模型脸色。

**模型输出被截断 / JSON 里带裸换行会怎样**
`json_repair` 大多数情况能直接修复（缺右括号、未转义控制字符等）；
修复后仍要过「等长 + 字符串」语义门，过不了照常重试报错。

**想清空缓存重译**
删掉 `cache_dir` 里的 JSON 即可（一篇一个文件）。

**术语翻译不准**
改 `translator.py` 里的 `SYSTEM_PROMPT`。想加术语表，在提示词里附上对照表最直接。
