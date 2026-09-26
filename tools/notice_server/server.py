# -*- coding: utf-8 -*-
"""LCTA 公告汉化 —— 服务端参考实现（FastAPI + Uvicorn）。

给 LCTA 的「公告汉化」功能做翻译服务用。客户端只把**官方公告文件名**发过来
（无需鉴权），服务端查缓存 / 拉官方原文 / 翻译，按 `{status}` 信封响应：

    GET /noticeDetails/{官方文件名}

    {"status": "ok",      "data": {…整篇公告 JSON…}}   译文就绪
    {"status": "pending", "message": "…"}               未命中缓存，已丢进后台翻译
    {"status": "error",   "message": "…"}               翻译失败（原因原样带出）

**翻译是异步的**：首次请求立刻回 `pending` 并在后台线程翻译，客户端会按
指数退避（1→2→4→8→16 秒，上限 60 秒）自动重试同一文件名，重试时命中缓存即
拿到 `ok`。所以单个请求永远秒回，不会挂住连接。

**定时预热**（`refresher.py`）：默认每 30 分钟拉一次官方 `noticeMeta.json`，
把清单里还没有译文的公告提前翻译好，客户端第一次请求通常就直接命中缓存。
间隔由 `refresh_interval` 控制（0 = 关闭），预热语言由 `refresh_languages` 控制。

HTTP 层是 FastAPI（`create_app()` 路由工厂），由 Uvicorn 承载；
`translator` / `store` / `pipeline` 等业务模块仍是纯标准库实现，
`json_repair` 负责 LLM 输出的容错解析。默认配置集中在 `config.py`。

启动：

    pip install -r tools/notice_server/requirements.txt
    python -m tools.notice_server.server --config tools/notice_server/config.json
    python -m tools.notice_server.server --backend fake        # 不调接口，先跑通链路

浏览器打开服务地址可看到状态页（缓存数、正在翻译的文件、最近错误、预热轮次），
`/docs` 是 FastAPI 自带的接口文档页。
"""
from __future__ import annotations

import argparse
import json
import posixpath
import sys
import threading
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

if __package__ in (None, ""):  # 支持 `python tools/notice_server/server.py` 直接跑
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from tools.notice_server.config import load_config
    from tools.notice_server.pipeline import NoticePipeline
    from tools.notice_server.refresher import DEFAULT_LANGUAGES, NoticeRefresher
    from tools.notice_server.store import (
        NoticeStore,
        NoticeStoreError,
        is_valid_notice_name,
    )
    from tools.notice_server.translator import (
        FakeTranslator,
        OpenAIChatTranslator,
        TranslationError,
    )
else:
    from .config import load_config
    from .pipeline import NoticePipeline
    from .refresher import DEFAULT_LANGUAGES, NoticeRefresher
    from .store import NoticeStore, NoticeStoreError, is_valid_notice_name
    from .translator import FakeTranslator, OpenAIChatTranslator, TranslationError


def error_envelope(message: str) -> dict:
    return {"status": "error", "message": str(message)}


# --------------------------------------------------------------------------
# 业务核心（与 HTTP 解耦，便于单测）
# --------------------------------------------------------------------------
class NoticeService:
    """缓存命中判定 + 异步调度 + 错误留存。"""

    def __init__(self, store: NoticeStore, pipeline: NoticePipeline, max_concurrency: int = 2):
        self.store = store
        self.pipeline = pipeline
        self.max_concurrency = max(1, int(max_concurrency))
        self._lock = threading.Lock()
        self._active = set()   # 正在翻译（或已排队）的文件名
        self._running = 0
        self._errors = {}      # 文件名 → 最近一次失败原因（只上报一次）
        self._translated = 0
        self._failed = 0

    # -- 对外 -------------------------------------------------------------
    def respond(self, file_name: str):
        """返回 `(HTTP 状态码, 信封)`。"""
        if not is_valid_notice_name(file_name):
            return 400, error_envelope(
                "文件名不合法（应为 noticeDetail_<id>_<KR|EN|JP>_<rev>.json）"
            )

        cached = self._read_cached(file_name)
        if cached is not None:
            return 200, {"status": "ok", "data": cached}

        with self._lock:
            failure = self._errors.pop(file_name, None)
        if failure:
            # 只上报一次：客户端会把这篇记为失败并展示原因，
            # 下次同步再来时会重新排队翻译（而不是一直吐旧错误）
            return 200, error_envelope(failure)

        if self._schedule(file_name):
            return 200, {"status": "pending", "message": "未命中缓存，正在翻译"}
        # `reason: busy` 供服务端内部（定时预热）区分「并发已满」与「正在翻译」，
        # 客户端只认 status，多出的字段会被忽略
        return 200, {
            "status": "pending",
            "reason": "busy",
            "message": "并发已满，稍后重试时会再排队",
        }

    def status(self) -> dict:
        with self._lock:
            active = sorted(self._active)
            errors = dict(self._errors)
            running = self._running
        return {
            "service": "lcta-notice-server",
            "state": "ok",
            "cache_dir": str(self.store.cache_dir),
            "official_base_url": self.store.official_base_url,
            "cached": len(self.store.cached_names()),
            "running": running,
            "max_concurrency": self.max_concurrency,
            "active": active,
            "translated": self._translated,
            "failed": self._failed,
            "last_errors": errors,
        }

    # -- 内部 -------------------------------------------------------------
    def _read_cached(self, file_name):
        raw = self.store.read_translated(file_name)
        if raw is None:
            return None
        try:
            payload = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, ValueError):
            payload = None
        if isinstance(payload, dict):
            return payload
        # 缓存损坏（半截文件 / 手工改坏）：删掉重来，避免永远返回坏内容
        try:
            self.store.cached_path(file_name).unlink()
        except OSError:
            pass
        return None

    def _schedule(self, file_name: str) -> bool:
        """排队翻译；并发已满或已在跑时返回 False。"""
        with self._lock:
            if file_name in self._active:
                return True
            if self._running >= self.max_concurrency:
                return False
            self._active.add(file_name)
            self._running += 1
        threading.Thread(
            target=self._job, args=(file_name,), daemon=True, name="notice-translate"
        ).start()
        return True

    def _job(self, file_name: str) -> None:
        try:
            self.pipeline.translate(file_name)
            with self._lock:
                self._translated += 1
                self._errors.pop(file_name, None)
        except Exception as exc:
            # 后台线程里兜住一切：失败原因要留给下一次请求上报，
            # 不能让线程带着异常悄悄死掉（客户端只会看到一直 pending）
            with self._lock:
                self._failed += 1
                self._errors[file_name] = "{}: {}".format(type(exc).__name__, exc)
        finally:
            with self._lock:
                self._active.discard(file_name)
                self._running -= 1


# --------------------------------------------------------------------------
# HTTP 层（FastAPI）
# --------------------------------------------------------------------------
def create_app(service: NoticeService, refresher: NoticeRefresher = None) -> FastAPI:
    """按 service 构建 FastAPI 应用，路由与 `{status}` 信封协议完全同构。

    * `/`、`/status`、`/healthz` —— 状态页，必须注册在 catch-all 之前；
      传入 `refresher` 时一并带出定时预热状态（间隔 / 上一轮摘要）；
    * `/{file_path:path}`       —— 兜底路由：任意前缀 + 官方文件名。
      只取最后一段做文件名（前缀随便写，客户端内置模板为 `/noticeDetails/{file}`），
      文件名本身仍走 `NOTICE_NAME_RE` 白名单校验（挡路径穿越）。

    端点一律用同步 `def`：Starlette 会把它们放进线程池执行，
    `service.respond()` 里的缓存文件读取与锁等待不会阻塞事件循环；
    翻译仍在独立后台线程里跑，与请求生命周期无关。
    """
    app = FastAPI(
        title="LCTA 公告汉化服务端",
        description=(
            "给 LCTA 的「公告汉化」功能自建翻译服务用的参考实现。"
            "客户端只发官方公告文件名，服务端查缓存 / 拉官方原文 / 翻译，"
            "按 `{status: ok|pending|error}` 信封响应。"
        ),
        version="1.0.0",
    )

    @app.get("/", include_in_schema=False)
    @app.get("/status", summary="服务状态（缓存数 / 正在翻译 / 最近错误 / 预热）")
    @app.get("/healthz", summary="存活探针（同 /status）")
    def get_status() -> dict:
        info = service.status()
        info["refresh"] = refresher.status() if refresher is not None else None
        return info

    @app.get(
        "/{file_path:path}",
        summary="按官方文件名取译文（路径前缀任意，只取最后一段）",
        description=(
            "响应恒为 JSON 信封：`ok` 带 `data`（整篇公告 JSON）；"
            "`pending` 表示已在后台翻译，客户端按指数退避重试同一文件名即可；"
            "`error` 带失败原因（只上报一次）。文件名不合法时回 HTTP 400。"
        ),
    )
    def get_notice(file_path: str) -> JSONResponse:
        # 只取 basename：路径前缀随便写（url_template 可配），文件名本身仍走白名单校验
        file_name = posixpath.basename(file_path)
        code, envelope = service.respond(file_name)
        # JSONResponse：UTF-8 + ensure_ascii=False，与旧 stdlib 版 _send_json 字节语义一致
        return JSONResponse(status_code=code, content=envelope)

    return app


# --------------------------------------------------------------------------
# 配置 / CLI
# --------------------------------------------------------------------------
def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="notice_server",
        description="LCTA 公告汉化服务端（FastAPI + OpenAI 兼容翻译后端）",
    )
    parser.add_argument("--config", help="JSON 配置文件路径（见 config.example.json）")
    parser.add_argument("--host", help="监听地址，默认 127.0.0.1")
    parser.add_argument("--port", type=int, help="监听端口，默认 8000")
    parser.add_argument("--cache-dir", help="译文缓存目录，默认 ./cache")
    parser.add_argument(
        "--backend", choices=("openai", "fake"), help="翻译后端；fake 不调接口，用于跑通链路"
    )
    parser.add_argument("--base-url", help="翻译接口地址（OpenAI 兼容），如 https://api.deepseek.com/v1")
    parser.add_argument("--api-key", help="翻译接口密钥；也可用环境变量 LCTA_NOTICE_API_KEY / OPENAI_API_KEY")
    parser.add_argument("--model", help="模型名，如 deepseek-chat")
    parser.add_argument("--official-base-url", help="官方公告地址")
    parser.add_argument("--max-concurrency", type=int, help="同时翻译的公告数，默认 2")
    parser.add_argument(
        "--refresh-interval",
        type=int,
        help="定时预热间隔（秒），默认 1800（30 分钟），0 关闭",
    )
    parser.add_argument(
        "--refresh-languages",
        help="预热哪些语言的公告文件，逗号分隔（如 EN,KR），默认 EN",
    )
    return parser.parse_args(argv)


def apply_cli_overrides(config: dict, args) -> dict:
    if args.host:
        config["host"] = args.host
    if args.port:
        config["port"] = int(args.port)
    if args.cache_dir:
        config["cache_dir"] = args.cache_dir
    if args.official_base_url:
        config["official_base_url"] = args.official_base_url
    if args.max_concurrency:
        config["max_concurrency"] = int(args.max_concurrency)
    if args.refresh_interval is not None:
        config["refresh_interval"] = int(args.refresh_interval)
    if args.refresh_languages:
        languages = [
            part.strip().upper() for part in args.refresh_languages.split(",") if part.strip()
        ]
        if languages:
            config["refresh_languages"] = languages
    translate = config["translate"]
    if args.backend:
        translate["backend"] = args.backend
    if args.base_url:
        translate["base_url"] = args.base_url
    if args.api_key:
        translate["api_key"] = args.api_key
    if args.model:
        translate["model"] = args.model
    return config


def build_translator(config: dict):
    translate = config["translate"]
    if (translate.get("backend") or "openai") == "fake":
        return FakeTranslator()
    return OpenAIChatTranslator(
        base_url=translate.get("base_url", ""),
        model=translate.get("model", ""),
        api_key=translate.get("api_key", ""),
        timeout=translate.get("timeout", 120),
        temperature=translate.get("temperature", 0.2),
        max_retries=translate.get("max_retries", 2),
        target_language=translate.get("target_language", "简体中文"),
    )


def refresh_log(message: str) -> None:
    """预热日志：直接打时间戳到 stdout（与 uvicorn 的日志互不干扰）。"""
    print(
        "[refresh] {} {}".format(time.strftime("%Y-%m-%d %H:%M:%S"), message),
        flush=True,
    )


def build_refresher(config: dict, store: NoticeStore, service: NoticeService):
    """按配置构建定时预热器；`refresh_interval` 为 0 时返回 None（不预热）。"""
    interval = config.get("refresh_interval", 0)
    try:
        if int(interval) <= 0:
            return None
    except (TypeError, ValueError):
        return None
    return NoticeRefresher(
        store,
        service,
        interval=interval,
        languages=config.get("refresh_languages") or DEFAULT_LANGUAGES,
        only_valid=bool(config.get("refresh_only_valid", True)),
        logger=refresh_log,
    )


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        config = load_config(args.config)
    except (OSError, ValueError) as exc:
        sys.stderr.write("读取配置失败: {}\n".format(exc))
        return 2
    apply_cli_overrides(config, args)

    cache_dir = Path(config["cache_dir"]).expanduser()
    store = NoticeStore(
        cache_dir,
        config["official_base_url"],
        timeout=config.get("official_timeout", 30),
    )
    service = NoticeService(
        store, NoticePipeline(store, build_translator(config)), config["max_concurrency"]
    )
    refresher = build_refresher(config, store, service)
    app = create_app(service, refresher)

    backend = config["translate"].get("backend") or "openai"
    model = config["translate"].get("model") or "-"
    if backend == "openai" and not config["translate"].get("api_key"):
        sys.stderr.write(
            "提示: 未配置翻译接口密钥（--api-key / LCTA_NOTICE_API_KEY），"
            "接口若需要鉴权会返回 401\n"
        )

    host, port = config["host"], config["port"]
    print("=" * 66)
    print("LCTA 公告汉化服务端（FastAPI + Uvicorn）")
    print("=" * 66)
    print("监听地址   : http://{}:{}".format(host, port))
    print("译文缓存   : {}".format(cache_dir.resolve()))
    print("翻译后端   : {}（model={}）".format(backend, model))
    print("官方公告源 : {}".format(config["official_base_url"]))
    print("并发上限   : {}".format(config["max_concurrency"]))
    if refresher is not None:
        print(
            "定时预热   : 每 {} 秒一轮（{}，{}）".format(
                refresher.interval,
                "、".join(refresher.languages),
                "仅有效期内公告" if refresher.only_valid else "含已过期公告",
            )
        )
    else:
        print("定时预热   : 已关闭")
    print("-" * 66)
    print("客户端（LCTA「公告汉化」页）已内置本服务地址，无需手工填写；")
    print("状态页: http://{}:{}/   接口文档: http://{}:{}/docs".format(host, port, host, port))
    print("按 Ctrl+C 退出。")
    print("=" * 66)

    if refresher is not None:
        refresher.start()
    try:
        uvicorn.run(app, host=host, port=port, log_level="info")
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        if refresher is not None:
            refresher.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
