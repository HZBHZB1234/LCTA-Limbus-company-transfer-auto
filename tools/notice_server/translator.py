# -*- coding: utf-8 -*-
"""公告翻译后端（OpenAI 兼容接口）。

`POST {base_url}/chat/completions`，请求体与 OpenAI 一致，
因此 DeepSeek / OpenAI / 本地 Ollama、vLLM 等都能直接接。
模型输出的 JSON 解析依赖 `json_repair`（见 requirements.txt）做容错修复。

翻译对象是**整篇公告的文本字段**：`title` 与 `content.list[*].formatValue`。
其中 `HyperLink` 的 formatValue 是裸 URL（如
`https://twitter.com/LimbusCompany_B`），绝不送进模型。

`SubTitle` 实测**不一定带包裹**：`<Official Twitter>` / `[Season 6: Zàng Huā Yín]`
有，但 `Notice: Lobotomy E.G.O::Red Sheet Sinclair Adjustment` 是裸的。带包裹时
包裹符号由 `restore_wrapper()` 确定性地还原，**不依赖模型听话**。

模型返回必须是**等长**的 JSON 字符串数组；输出先经 `json_repair` 容错解析
（截断 / 未转义换行 / 代码围栏 / 前后废话 / `<think>` 标签都能救回），
修不回来或长度不符才重试，重试耗尽抛 `TranslationError` ——
宁可报错，也不缓存一篇结构错乱的公告
（客户端也会拒收，但那时就看不出真正的原因了）。
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Callable, List, Optional

from json_repair import repair_json

USER_AGENT = "LCTA-NoticeServer/1.0"
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
DEFAULT_TARGET_LANGUAGE = "简体中文"
DEFAULT_MAX_RETRIES = 2

# 裸 URL 一律不翻译
URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)
# 推理模型的思考标签（Qwen 系经 vLLM 部署时常混在 content 里）
THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
# 包裹符号：<...> 与 [...]
WRAPPER_PAIRS = {"<": ">", "[": "]"}
# 这些 formatKey 的 formatValue 不是给人读的文本
SKIP_FORMAT_KEYS = ("HyperLink",)

SYSTEM_PROMPT = (
    "你是 Limbus Company（边狱公司）官方公告的汉化译者。"
    "用户会给你一个 JSON 数组，每一项是一段英文公告文本（标题、副标题或正文）。"
    "请逐项翻译成{lang}。\n"
    "硬性要求：\n"
    "1. 只输出一个 JSON 数组，元素为字符串，**长度与顺序必须与输入完全一致**；"
    "不要输出数组以外的任何内容（不要解释、不要代码块围栏、不要编号）。\n"
    "2. 保留原文的换行与空行结构。\n"
    "3. 保留行首的符号与编号（●、※、-、1.、2) 等），不要增删列表项。\n"
    "4. 保留 <...> 与 [...] 等包裹符号本身，只翻译里面的内容。\n"
    "5. 不要添加原文没有的内容，不要把多条合并成一条，也不要拆开。"
)


class TranslationError(RuntimeError):
    """翻译后端调用或结果解析失败。"""


# --------------------------------------------------------------------------
# 文本槽位 / 包裹处理
# --------------------------------------------------------------------------
def split_wrapper(value: str):
    """拆出 `<...>` / `[...]` 包裹，返回 `(前缀, 正文, 后缀)`；非包裹返回 `('', 原文, '')`。"""
    if len(value) >= 2 and value[0] in WRAPPER_PAIRS and value[-1] == WRAPPER_PAIRS[value[0]]:
        return value[0], value[1:-1], value[-1]
    return "", value, ""


def restore_wrapper(original: str, translated: str) -> str:
    """把包裹符号还原成原文的形式。

    模型有没有保留包裹都不影响结果：

    1. 模型自己加了一层包裹（或把原文包裹原样搬了过来）→ 先剥掉；
    2. 译文里仍原样嵌着 `<原文>`（模型没翻包裹内容，`FakeTranslator` 就是这种）
       → 把它换成不带包裹的正文，避免出现 `<<...>>` 这种双层包裹。
    """
    prefix, inner, suffix = split_wrapper(original)
    if not prefix:
        return translated
    text = (translated or "").strip()
    if len(text) >= 2 and text[0] in WRAPPER_PAIRS and text[-1] == WRAPPER_PAIRS[text[0]]:
        text = text[1:-1].strip()
    if original in text:
        text = text.replace(original, inner).strip()
    return prefix + text + suffix


def is_translatable(format_key: str, value) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    if (format_key or "") in SKIP_FORMAT_KEYS:
        return False
    return not URL_RE.match(value.strip())


def _content_items(payload: dict) -> List[dict]:
    content = payload.get("content")
    items = content.get("list") if isinstance(content, dict) else None
    return items if isinstance(items, list) else []


def build_slots(payload: dict) -> List[dict]:
    """列出需要翻译的字段槽位。

    每个槽位是 `{"where": "title"|"list", "index": int|None, "key": str|None, "text": str}`。
    """
    slots: List[dict] = []
    title = payload.get("title")
    if isinstance(title, str) and title.strip():
        slots.append({"where": "title", "index": None, "key": None, "text": title})
    for index, item in enumerate(_content_items(payload)):
        if not isinstance(item, dict):
            continue
        key = item.get("formatKey")
        value = item.get("formatValue")
        if is_translatable(key, value):
            slots.append({"where": "list", "index": index, "key": key, "text": value})
    return slots


def apply_translations(payload: dict, slots: List[dict], translations: List[str]) -> dict:
    """把译文写回 payload（就地修改）。`formatKey` 与其余字段一律不动。"""
    items = _content_items(payload)
    for slot, translated in zip(slots, translations):
        text = restore_wrapper(slot["text"], translated)
        if slot["where"] == "title":
            payload["title"] = text
        else:
            items[slot["index"]]["formatValue"] = text
    return payload


def validate_payload(payload: dict) -> None:
    """落盘前的自检：与客户端硬门同源的检查，避免缓存一篇会被拒收的公告。"""
    if not isinstance(payload.get("id"), int):
        raise TranslationError("译文缺少 id")
    if not isinstance(payload.get("noticeType"), int):
        raise TranslationError("译文缺少 noticeType")
    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        raise TranslationError("译文 title 为空")
    items = _content_items(payload)
    if not items:
        raise TranslationError("译文缺少 content.list")
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise TranslationError("content.list[{}] 不是对象".format(index))
        if not isinstance(item.get("formatKey"), str) or not item.get("formatKey"):
            raise TranslationError("content.list[{}] 缺少 formatKey".format(index))
        if not isinstance(item.get("formatValue"), str):
            raise TranslationError("content.list[{}] 的 formatValue 不是字符串".format(index))


# --------------------------------------------------------------------------
# 后端
# --------------------------------------------------------------------------
class OpenAIChatTranslator:
    """OpenAI 兼容的 chat/completions 后端。"""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout: int = 120,
        temperature: float = 0.2,
        max_retries: int = DEFAULT_MAX_RETRIES,
        target_language: str = DEFAULT_TARGET_LANGUAGE,
        opener: Optional[Callable] = None,
    ):
        self.base_url = (base_url or "").strip().rstrip("/")
        self.model = (model or "").strip()
        self.api_key = (api_key or "").strip()
        self.timeout = max(1, int(timeout))
        self.temperature = float(temperature)
        self.max_retries = max(0, int(max_retries))
        self.target_language = (target_language or DEFAULT_TARGET_LANGUAGE).strip()
        self._opener = opener or urllib.request.urlopen

    # -- 对外 -------------------------------------------------------------
    def translate(self, texts: List[str]) -> List[str]:
        """把一组英文文本译成中文，返回**等长**列表。"""
        if not texts:
            return []
        if not self.base_url or not self.model:
            raise TranslationError("未配置翻译后端（需要 translate.base_url 与 translate.model）")

        last_error: Optional[Exception] = None
        for _attempt in range(self.max_retries + 1):
            try:
                return self._parse(self._chat(texts), len(texts))
            except TranslationError as exc:
                last_error = exc
        raise TranslationError(
            "{}（已重试 {} 次）".format(last_error, self.max_retries)
        )

    # -- 内部 -------------------------------------------------------------
    def _chat(self, texts: List[str]) -> str:
        body = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT.format(lang=self.target_language)},
                {"role": "user", "content": json.dumps(texts, ensure_ascii=False)},
            ],
        }
        headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers=headers,
        )
        try:
            with self._opener(req, timeout=self.timeout) as resp:
                raw = resp.read(MAX_RESPONSE_BYTES)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read(400).decode("utf-8", "replace").strip()
            except Exception:
                pass
            raise TranslationError(
                "翻译接口返回 HTTP {}{}".format(exc.code, (" — " + detail) if detail else "")
            )
        except urllib.error.URLError as exc:
            raise TranslationError("无法连接翻译接口: {}".format(getattr(exc, "reason", exc)))
        except TimeoutError:
            raise TranslationError("翻译接口超时（{} 秒）".format(self.timeout))

        try:
            payload = json.loads(raw.decode("utf-8-sig"))
            content = payload["choices"][0]["message"]["content"]
        except Exception as exc:
            raise TranslationError("翻译接口响应结构异常: {}".format(exc))
        if not isinstance(content, str):
            raise TranslationError("翻译接口未返回文本内容")
        return content

    @staticmethod
    def _parse(content: str, expected: int) -> List[str]:
        items = extract_json_array(content)
        if len(items) != expected:
            raise TranslationError(
                "模型返回 {} 条，期望 {} 条".format(len(items), expected)
            )
        for index, item in enumerate(items):
            if not isinstance(item, str):
                raise TranslationError("模型返回的第 {} 条不是字符串".format(index + 1))
        return list(items)


def extract_json_array(content: str) -> list:
    """从模型输出里抠出 JSON 数组（尽力容错）。

    解析顺序：

    1. 剥离 `<think>…</think>` 推理标签与代码块围栏；
    2. 先走严格 `json.loads` —— 绝大多数正常输出零开销直达；
    3. 失败再用 `json_repair` 容错修复：截断（缺右括号）、字符串里未转义的
       换行、单引号、尾逗号、前后废话等都能救回来；
    4. 修不回来（纯文本 / 空串）才抛 `TranslationError`。

    注意：这里只修**语法**。「是数组、元素是字符串、与输入等长」的语义门在
    `_parse` 里，语法修复不会放过语义错误。
    """
    text = THINK_TAG_RE.sub("", (content or "").strip()).strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        payload = json.loads(text)
    except ValueError:
        try:
            payload = repair_json(text, return_objects=True)
        except Exception as exc:  # json_repair 自身异常也按解析失败处理
            raise TranslationError("模型返回的 JSON 无法解析: {}".format(exc))
    if not isinstance(payload, list):
        raise TranslationError("模型返回的不是 JSON 数组: {}".format(text[:120]))
    return payload


class FakeTranslator:
    """不调任何接口的假后端：给每段文本加 `【中】` 前缀。

    用来在没有 API Key 的情况下先跑通「客户端 ↔ 服务端」整条链路。
    产物是 `【中】English text`，客户端会正常收下，但游戏里看到的就是这个。
    """

    def translate(self, texts: List[str]) -> List[str]:
        return ["【中】" + text for text in texts]
