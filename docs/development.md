# LCTA 开发指南

> 面向开发者的完整开发环境搭建、构建、调试和发布指南。
> AI 快速参考请见 `.claude/docs/dev-guide.md`

## 前置条件

| 工具 | 版本要求 | 用途 |
|------|---------|------|
| Python | 3.9.6+ | 运行和开发 |
| Git | 任意版本 | 版本控制 |
| MinGW-w64 | 任意版本 | C launcher 编译（可选，构建时如不可用则跳过） |
| PowerShell | 5.0+ | 运行构建脚本 |
| 操作系统 | Windows 10+ | 唯一支持平台 |

## 开发环境搭建

### 1. 克隆仓库

```bash
git clone <repo-url>
cd LCTA-Limbus-company-transfer-auto
```

### 2. 创建虚拟环境

```bash
python -m venv .venv
# 或使用项目已有的 .venv/
```

### 3. 激活虚拟环境

```bash
# Git Bash / PowerShell
source .venv/Scripts/activate
# 或
.venv\Scripts\Activate.ps1
```

### 4. 安装依赖

```bash
pip install -r requirements.txt
```

### 5. 配置环境变量

复制 `.env` 文件并根据需要修改：

```env
TesterTocken=<your-api-key>
TesterModel=deepseek-v4-flash
TesterEndPoint=https://api.deepseek.com/v1
```

### 6. 验证安装

```bash
python start_webui.py
```

如果 GUI 窗口正常启动并显示主界面，说明环境配置成功。

## 项目结构详解

```
LCTA-Limbus-company-transfer-auto/
├── start_webui.py              # 主入口分发器（WebUI / Launcher 模式）
├── build.ps1                   # 构建脚本（617 行，6 步流水线）
├── launcher.c                  # C 原生启动器源码
│
├── webui/                      # 前端应用
│   ├── app.py                  # LCTA_API 核心桥接类 (~1450 行)
│   ├── index.html              # SPA 外壳 (103KB)
│   ├── css/                    # 样式表 (3 文件)
│   ├── js/                     # JS 模块 (9 文件)
│   ├── guide/                  # 应用内用户指南 (16 md 页面)
│   └── elder/                  # 设置向导 (14 md 页面)
│
├── webutils/                   # 业务逻辑层
│   ├── __init__.py             # 公共 API 聚合
│   └── function_*.py           # 功能模块 (24 文件)
│
├── webFunc/                    # 基础设施层
│   ├── GithubDownload.py
│   ├── FileTransfer.py
│   ├── LanzouFolder.py
│   └── Webnote.py
│
├── translateFunc/              # 翻译引擎
│   ├── pipeline.py             # 流水线编排
│   ├── processor.py            # 单文件处理
│   ├── workers.py              # 并发控制
│   ├── config.py               # 配置数据类
│   ├── enums.py                # 枚举定义
│   ├── translate_request.py    # API 请求
│   ├── builder/                # 提示词与请求构建
│   └── matcher/                # 专有名词匹配引擎
│
├── globalManagers/             # 全局单例
│   ├── ConfigManager.py
│   └── LogManager.py
│
├── launcher/                   # 独立启动器 (GPL-3.0)
│   ├── main.py
│   ├── game_launch.py
│   ├── updates.py
│   └── ...
│
├── CFST/                       # CloudflareSpeedTest
├── tests/                      # 测试套件
├── docs/                       # 面向人类的文档（你在这里）
├── .claude/docs/              # AI 快速参考文档
├── .github/workflows/         # CI/CD
├── prompts/                    # AI 提示词规则
├── config.json                 # 用户运行时配置
├── config_default.json         # 默认配置模板
├── config_check.json           # 配置类型校验
└── requirements.txt            # Python 依赖
```

## 运行模式

### WebUI 模式（完整桌面应用）

```bash
python start_webui.py
```

启动完整的桌面应用，包含所有功能标签页：仪表盘、安装、下载、翻译、API 配置、管理、清理、美化、专有名词、老版、设置、CDN、变速、日志等。

### Launcher 模式（轻量级游戏启动器）

```bash
python start_webui.py -launcher
```

启动轻量级启动器，仅包含游戏启动、汉化更新、CDN 优化功能。入口点在 `launcher/main.py`。

### 调试模式

```bash
python start_webui.py --debug
```

启用详细日志输出，便于开发调试。

## 配置系统

LCTA 使用三层配置系统：

### config.json（用户配置）
运行时配置，包含用户的 API 密钥、游戏路径、UI 偏好等。由 `ConfigManager` 管理，程序运行时自动读写。

### config_default.json（默认配置模板）
内置的默认值。当 `config.json` 中缺少某个键时，`ConfigManager` 会回退到此文件中的值。新增配置项时，必须在此文件中添加默认值。

### config_check.json（配置校验模式）
定义每个配置键的类型（`"str"`, `"bool"`, `"int"` 等）。`ConfigManager` 在加载和保存配置时使用此文件进行类型校验。

### 配置访问方式

```python
from globalManagers.ConfigManager import ConfigManager

# 读取（使用点号路径）
api_key = ConfigManager.get("ui_default.translator.api_key")

# 写入
ConfigManager.set("ui_default.translator.api_key", "new_key")
# 自动校验类型 → 自动保存到 config.json
```

**关键规则**：永远不要直接读写 `config.json`，必须通过 `ConfigManager`。直接文件操作会绕过校验、破坏线程安全、导致多实例不一致。

## 测试

### 运行测试

```bash
# 全部测试
pytest tests/

# 指定测试文件
pytest tests/test_config.py

# 带详细输出
pytest tests/ -v

# 指定单个测试
pytest tests/test_config.py::test_load_config
```

### 测试组织

| 文件 | 覆盖范围 |
|------|---------|
| `tests/test_config.py` | ConfigManager 加载、校验、保存 |
| `tests/test_translate.py` | 翻译流水线 |
| `tests/test_webui.py` | WebUI 功能 |

### 编写新测试

1. 在 `tests/` 目录下创建 `test_<module>.py`
2. 使用 pytest 风格（函数名以 `test_` 开头）
3. 如需测试数据，放在 `tests/` 下的子目录中
4. Mock `ConfigManager` 和 `LogManager` 单例以避免副作用

## 构建发布包

### 完整构建

```powershell
.\build.ps1
```

构建脚本执行 6 个步骤：

1. **InitCode** — 运行 `.github/InitCode.py`，下载前端资源（Font Awesome、marked.js、字体等），生成嵌入资源的 C 源码
2. **C 编译** — 使用 MinGW-w64 编译 C launcher（`gcc -mwindows -O2`），编译资源文件（`windres`）
3. **嵌入式 Python** — 下载 Python 3.9.6 embeddable，安装 pip 依赖，修补 `requests` 禁用 SSL 验证
4. **dist/ 组装** — 复制源码文件，替换 webui 为 InitCode 修改版，捆绑嵌入式 Python venv
5. **更新包清理** — 从更新包中移除 `.git` 和 `.github`
6. **ZIP 打包** — 创建三个输出包

### 构建产物

| 文件 | 说明 |
|------|------|
| `LCTA-Portable-Full.zip` | 标准发布包 |
| `LCTA-Portable-Full-Compatible.zip` | 兼容版发布包（含 PyQt 回退） |
| `LCTA-update.zip` | 源文件更新包（不含嵌入式 Python） |

### 构建要求

- **PowerShell 5.0+**
- **MinGW-w64**（gcc + windres）：可选，不可用时跳过 C 编译步骤
- **系统 Python 3.9.6**：用于创建 venv
- **网络连接**：用于下载嵌入式 Python 和前端资源

### 构建故障排查

| 问题 | 解决方案 |
|------|---------|
| `build.ps1` 中文乱码 | 文件必须是 UTF-8 with BOM 编码，参考 `prompts/build.ps1.md` |
| gcc 未找到 | 安装 MinGW-w64 并确保 `gcc` 在 PATH 中，或接受跳过 C 编译 |
| 下载嵌入式 Python 失败 | 检查网络连接，可能需要代理 |
| etcpak 安装失败 | 确认版本为 0.9.8（0.9.9 有已知崩溃问题） |

## CI/CD

### release.yml（构建与发布）

触发条件：推送到 `main` 分支，或推送 `v*` 标签（如 `v4.1.5`）。

流程：
1. `windows-latest` 运行器
2. `msys2/setup-msys2@v2` 安装 MinGW-w64 工具链
3. 执行与 `build.ps1` 相同的 gcc 编译命令
4. 构建完成后上传产物

**重要**：修改 gcc 编译参数或 C 源码结构时，必须同步更新 `build.ps1` 和 `release.yml`。

### check.yml（定时检查）

触发条件：定时 cron。

用于定期检查项目的健康状态（依赖可用性、构建是否成功等）。

## 调试指南

### 常见问题与解决

| 问题 | 原因 | 解决 |
|------|------|------|
| 启动后窗口闪退 | Python 环境问题或缺少依赖 | 运行 `debug_environ_test.py` 诊断 |
| WebView 白屏 | WebView2 未安装或版本过低 | 安装/更新 Edge WebView2 Runtime |
| API 调用失败 | API 密钥无效或网络问题 | 检查 `.env` 配置，使用 API 测试页面 |
| 翻译卡住不动 | LLM API 速率限制或超时 | 减少并发 worker 数，检查 API 配额 |
| 游戏启动失败 | 游戏路径配置错误 | 检查 config.json 中的游戏路径，确认 Steam 安装 |

### PyWebView 开发者工具

在 pywebview 窗口中可以打开开发者工具：
- 右键点击 → 检查（Inspect）
- 查看 Console、Network、Elements 面板

### 日志分析

- **终端输出**：运行时的 LogManager 输出
- **logs/ 目录**：按时间戳的日志文件，包含完整的调试信息
- **模态框日志**：WebUI 中操作的实时日志通过模态框显示

## 代码风格与约定

### Python

- 遵循 PEP 8 风格
- 功能模块使用 `function_<feature>.py` 命名
- 配置访问统一通过 `ConfigManager`
- 日志输出统一通过 `LogManager`
- 不在模块顶层执行有副作用的代码

### JavaScript

- 使用 ES6+ 语法
- JS 模块按功能页面拆分（`js/cdn.js`, `js/speed.js` 等）
- 与 Python 通信统一通过 `pywebview.api`
- 模态框使用统一的生命周期管理

### 文件命名

- Python 模块：`snake_case.py`
- 功能模块：`function_<feature>.py`
- JS 模块：`kebab-case.js`
- 文档：`kebab-case.md`

## 发布流程

1. **开发与测试**：在 `main` 分支开发，确保所有测试通过
2. **版本号更新**：修改 `start_webui.py` 顶部的版本号
3. **更新 changelog**：更新 `webui/assets/update.md`
4. **运行构建**：`.\build.ps1`
5. **测试构建产物**：解压 ZIP，验证可正常运行
6. **打标签**：`git tag v4.x.x`
7. **推送**：`git push && git push --tags`
8. **GitHub Actions**：自动构建并创建 Release
9. **更新通知**：用户启动 LCTA 时会收到自动更新提示

## 常见开发任务

### 添加新功能模块

1. 创建 `webutils/function_<newfeature>.py`
2. 在 `webutils/__init__.py` 中导出公共函数
3. 在 `webui/app.py` 的 `LCTA_API` 类中添加桥接方法
4. 创建 `webui/guide/<newfeature>.md` 用户指南页
5. 在 `webui/js/features.js` 或新建 JS 文件中添加前端逻辑
6. 如有新配置项，更新 `config_default.json` 和 `config_check.json`
7. 如有 tooltip 需求，参考 `prompts/tooltip.md`

### 修复 Bug

1. 在 `logs/` 中查看相关日志
2. 通过 `.claude/docs/key-paths.md` 找到相关代码路径
3. 修改代码
4. 运行相关测试：`pytest tests/ -k <related_keyword>`
5. 手动验证修复效果

### 更新依赖

1. 修改 `requirements.txt`
2. 在虚拟环境中测试安装：`pip install -r requirements.txt`
3. 完整运行测试套件
4. 完整构建测试：`.\build.ps1`
5. 注意 `etcpak==0.9.8` 不能升级（0.9.9 有崩溃 bug）

## 约束条件

- **仅支持 Windows**：使用 Win32 API、pywebview（WebView2）、MSYS2 构建
- **Python 3.9.6**：嵌入式 Python 打包固定使用此版本
- **UTF-8 with BOM**：`build.ps1` 必须使用此编码（含中文文本）
- **etcpak==0.9.8 固定**：不可升级
- **GPL-3.0 隔离**：`launcher/` 与主项目代码零 import，仅通过 config.json 和命令行通信
- **构建/CI 同步**：修改编译参数必须同步更新 `build.ps1` 和 `.github/workflows/release.yml`
