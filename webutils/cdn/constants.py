"""常量定义（对应 LLC_BABEL CdnTarget.cs）"""
from __future__ import annotations

_DEBUG = False

CF_START_MARKER = "# START-OF-LLC-BABEL-CF"
CF_END_MARKER   = "# END-OF-LLC-BABEL-CF"
CFA_START_MARKER = "# START-OF-LLC-BABEL-AMAZON"
CFA_END_MARKER   = "# END-OF-LLC-BABEL-AMAZON"

CLOUDFLARE_DOMAINS = [
    "download.limbuscompanycdn.org",
    "downloadcommon.limbuscompanycdn.org",
    "downloadfmod.limbuscompanycdn.org",
]

CLOUDFRONT_ENDPOINTS = {
    "www.limbuscompanyapi.com":    "https://www.limbuscompanyapi.com/",
    "notice.limbuscompanyapi.com": "https://notice.limbuscompanyapi.com/",
}

CFST_EXE = "cfst.exe"
IP_FILE = "ip.txt"
CFST_TEST_URL = "https://cf.xiu2.xyz/url"
CFST_VERSION = "v2.3.5"
CFST_DOWNLOAD_URL = (
    f"https://github.com/XIU2/CloudflareSpeedTest/releases/download/"
    f"{CFST_VERSION}/cfst_windows_amd64.zip"
)
IP_TXT_URL = "https://raw.githubusercontent.com/XIU2/CloudflareSpeedTest/master/ip.txt"

DOH_SOURCES = [
    ("阿里 DoH",   "https://dns.alidns.com/resolve"),
    ("DNSPod DoH", "https://doh.pub/dns-query"),
]

SOURCE_TIMEOUT = 3        # 每个 DNS 源的超时（秒）
PROBE_TIMEOUT = 4         # 每次 HTTPS 探测超时（秒）
MAX_CANDIDATES = 24
MAX_CONCURRENCY = 6
FINALIST_COUNT = 5
FINAL_ATTEMPTS = 3
REQUIRED_FINAL_SUCCESSES = 2
CLOUDFRONT_OVERALL_TIMEOUT = 45  # 匹配 LLC_BABEL DefaultOverallTimeout
CFST_OVERALL_TIMEOUT = 900       # cfst 测速总超时（秒，15 分钟），防止子进程被挂起时无限等待

# ---- CloudFront 探测失败分类（对应 LLC_BABEL CloudFrontProbeFailure 枚举） ----
# 每种失败类型都有对应的用户可读消息，方便日志诊断。
PROBE_FAILURE_NONE = None          # 探测成功
PROBE_FAILURE_CONNECTION = "Connection"
PROBE_FAILURE_TIMEOUT = "Timeout"
PROBE_FAILURE_TLS = "Tls"
PROBE_FAILURE_HTTP_STATUS = "HttpStatus"
PROBE_FAILURE_BUSINESS_CONTENT = "BusinessContent"
PROBE_FAILURE_CANCELED = "Canceled"
PROBE_FAILURE_NETWORK = "Network"

PROBE_FAILURE_MESSAGES = {
    PROBE_FAILURE_NONE: None,
    PROBE_FAILURE_CONNECTION: "无法连接到目标 IP（连接被拒绝或重置）。",
    PROBE_FAILURE_TIMEOUT: "探测超时（目标 IP 在规定时间内未响应）。",
    PROBE_FAILURE_TLS: "TLS 协商或证书验证失败。",
    PROBE_FAILURE_HTTP_STATUS: "目标端点返回了不可接受的 HTTP 状态码。",
    PROBE_FAILURE_BUSINESS_CONTENT: "目标端点响应未包含业务验证所需的关键内容。",
    PROBE_FAILURE_CANCELED: "探测已被取消。",
    PROBE_FAILURE_NETWORK: "探测因网络错误失败。",
}
