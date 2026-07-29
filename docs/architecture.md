# LCTA 架构文档

> 面向开发者的详细架构说明，包含技术决策理由和权衡分析。
> AI 快速参考请见 `.claude/docs/architecture.md`
> Last updated: 2026-07-29

## 项目概述

LCTA（Limbus Company Transfer Auto / 边狱公司工具箱）是一个面向游戏《边狱公司》(Limbus Company) 的综合性桌面工具箱。项目始于对游戏汉化管理的需求，逐步扩展为集翻译管理、CDN 优化、游戏启动器、模组支持于一体的多功能工具。

**当前版本**: 5.0.0
**许可证**: MIT（主项目），launcher/ 子目录为 GPL-3.0

### 核心功能

- **翻译管理**：支持零协会(LLC)、OurPlay PC、OurPlay Android、机翻等多种汉化源的一键下载安装
- **LLM 自动翻译**：基于大语言模型的游戏文本自动翻译流水线，支持专有名词匹配
- **API 配置与测试**：支持项目专用的 OpenAI-compatible LLM 与 Null provider 配置和原生连通性测试
- **集成启动器**：带模组支持的游戏启动器，含 CDN 优化（支持缓存有效期避免重复测速）、变速、热键全生命周期日志等功能
- **其他工具**：缓存清理、专有名词抓取、字体定制、Bubble 语言包下载、文本美化等

## 技术选型理由

### 为什么选择 pywebview 而不是 Electron？

- **体积**：pywebview 使用系统原生 WebView（Windows 上为 Edge WebView2），不需要捆绑完整的 Chromium，发布包体积显著小于 Electron
- **混合生态**：pywebview 可直接复用 Python 的桌面与 Unity 资源生态；翻译、规则和文件热路径通过 PyO3 调用 Rust，无需额外 IPC 服务
- **启动速度**：pywebview 窗口启动明显快于 Electron

代价：仅支持 Windows（系统 WebView 依赖），跨平台能力受限。但目标用户群体几乎全部使用 Windows，此代价可接受。

### 为什么选择 Python 而不是 .NET/C#？

- 团队更熟悉 Python 生态
- WebUI、配置、打包和 UnityPy 资源处理继续复用成熟的 Python 生态
- 翻译热路径使用 Rust/Tokio/Reqwest，避免 Python 线程和同步网络 I/O 成为瓶颈
- 快速迭代：Python 的开发效率适合工具类项目频繁的需求变更

代价：分发时需要捆绑嵌入式 Python（~30MB），且 Python 作为解释型语言在某些场景性能不如编译型语言。

### 为什么使用嵌入式 Python 分发？

传统做法是使用 PyInstaller 打包为单个 exe，但 LCTA 选择直接分发 Python 源码 + 嵌入式解释器，原因：
- PyInstaller 打包的 exe 会被杀毒软件频繁误报
- 源码分发便于用户审查和修改（开源透明）
- 更新时可以只替换源码文件，无需重新下载整个解释器
- C 编写的 `launcher.exe` 作为 PE 入口点，避免双击时弹出控制台窗口

### 为什么 launcher/ 单独使用 GPL-3.0？

launcher/ 的模组功能基于 LimbusModLoader（GPL-3.0），因此该子目录必须保持 GPL-3.0。为了不污染主项目的 MIT 许可证，launcher/ 与主项目在代码层面**完全隔离**——没有任何 import 关系，仅通过 `config.json` 和命令行参数通信。

## 分层架构详解

```
┌──────────────────────────────────────────────────────────────┐
│                        PRESENTATION                          │
│                                                              │
│  ┌─────────────────────┐  ┌──────────────────────────────┐  │
│  │   start_webui.py    │  │     webui/ (Frontend SPA)     │  │
│  │   入口分发器          │  │                              │  │
│  │   -launcher →       │  │  app.py    LCTA_API (Bridge)  │  │
│  │   launcher/main.py  │  │  index.html SPA Shell         │  │
│  │   默认 →            │  │  js/       9 modules          │  │
│  │   webui/app.py      │  │  css/      3 stylesheets      │  │
│  └─────────────────────┘  │  guide/    16 md pages         │  │
│                           └──────────────────────────────┘  │
├──────────────────────────────────────────────────────────────┤
│                      BUSINESS LOGIC                          │
│                                                              │
│  webutils/__init__.py  ← 公共 API 聚合层                     │
│  webutils/function_*.py ← 每个文件一个功能领域                │
│  webutils/update.py    ← 自更新逻辑                           │
│  webutils/load.py      ← 配置加载 / Steam 注册表检测          │
├──────────────────────────────────────────────────────────────┤
│                     DOMAIN ENGINES                            │
│                                                              │
│  native/lcta_translation_engine/ Rust 翻译引擎               │
│  ┌──────────────────────────────────────────────────────┐    │
│  │ engine.rs      → 阶段屏障与并发编排                    │    │
│  │ provider.rs    → Tokio/Reqwest 高并发网络              │    │
│  │ response.rs    → JSON 提取、修复与 ID 校验             │    │
│  │ matcher.rs     → 不可变 AC 自动机                      │    │
│  │ rules.rs       → 术语快照与确定性校验                  │    │
│  │ diagnostics.rs → schema-v2 异步诊断日志                │    │
│  └──────────────────────────────────────────────────────┘    │
├──────────────────────────────────────────────────────────────┤
│                     INFRASTRUCTURE                            │
│                                                              │
│  webFunc/          GitHub API / 文件上传 / 蓝奏云 / Webnote  │
│  globalManagers/   ConfigManager & LogManager (单例)         │
│  CFST/             CloudflareSpeedTest (第三方二进制)        │
├──────────────────────────────────────────────────────────────┤
│                    EXTERNAL TOOLS                             │
│  openspeedy  UnityPy  pywebview  etcpak                       │
└──────────────────────────────────────────────────────────────┘
```

### 表示层 (Presentation)

**start_webui.py** 是整个应用的入口分发器。它根据命令行参数决定启动哪个模式：
- 无参数 → WebUI 模式（完整桌面应用）
- `-launcher` → 启动器模式（轻量级游戏启动器）

**webui/app.py** 中的 `LCTA_API` 类是表示层的核心。它是一个~1450 行的类，将底层所有功能通过 pywebview 的 JS API 桥接暴露给前端。每个公开方法对应前端的一个功能调用。主要职责：
- 注册所有功能方法到 pywebview API（包括 `perform_update_from_file()` 手动更新功能）
- 管理模态窗口的生命周期（创建、更新进度、关闭）
- 处理前端与后端的双向通信（回调、事件）
- 拖放文件处理：接收 JS 传递的文件路径列表，交由 `function_drop.py` 分析执行

**webui/ 前端** 是一个单页应用（SPA），使用原生 HTML/CSS/JS 构建，不依赖 React/Vue 等框架。选择原生方案的原因是减少依赖、降低打包体积。9 个 JS 模块按功能领域拆分。

### 业务逻辑层 (Business Logic)

**webutils/** 是业务逻辑的集中地。每个 `function_*.py` 文件封装一个完整的功能领域，例如：
- `function_llc.py` — 零协会汉化包的下载、解压、安装全流程
- `function_cdn.py` — CDN 测速和优化（含缓存 TTL 机制，避免启动器模式重复测速）
- `function_translate.py` — 翻译功能的编排入口

所有功能模块通过 `webutils/__init__.py` 统一导出，形成稳定的公共 API。`webui/app.py` 只依赖 `__init__.py` 的导出，不直接导入具体功能模块。这种间接层允许功能模块内部重构而不影响表示层。

### 领域引擎层 (Domain Engines)

**native/lcta_translation_engine/** 是翻译领域引擎。`translateFunc/` 仅保留配置与 PyO3 桥接，不再包含 Python 翻译实现。

原生翻译流水线的主要阶段：
1. **异步加载规则**：并发读取本地术语或抓取 ParaTranz 术语
2. **优先级屏障**：先处理 BattleKeywords 与 ScenarioModelCodes，冻结效果和角色快照
3. **并发文件处理**：Tokio 文件任务、请求信号量和文件 I/O 信号量相互独立
4. **请求级提示词**：system/user prompt 随每次请求传递，provider 配置保持不可变
5. **响应修复与补译**：提取/修复 JSON，检测缺失与重复 ID，对无效条目发起补充请求
6. **确定性校验与输出**：检查标签、占位符、数字和效果引用，原子写入 UTF-8 BOM JSON
7. **结构化诊断**：单 Tokio writer 输出 schema-v2 JSONL 和每阶段耗时/重试信息

### 基础设施层 (Infrastructure)

- **webFunc/**：通用的网络/文件操作基础设施，与业务逻辑无关。可独立复用于其他项目。
- **globalManagers/**：跨切面的单例管理器。ConfigManager 提供线程安全的配置访问（点号路径、自动校验、自动保存），LogManager 提供统一的日志输出（文件轮转、控制台、WebView 模态框回调）。

## 设计模式详解

### Singleton — ConfigManager & LogManager

```
ConfigManager 生命周期：
  app 启动 → ConfigManager(validate=True) → 加载 config.json
  → 与 config_default.json 合并 → 按 config_check.json 校验类型
  → 后续所有模块通过 ConfigManager.get("path.to.key") 访问

线程安全：使用 threading.Lock 保护写操作
自动保存：修改配置后自动写入 config.json
```

使用单例的原因：配置和日志是真正的全局关注点，所有模块都需要访问。单例避免了在函数间传递配置对象的样板代码。但代价是增加了模块间的隐式耦合——测试时需要 mock 单例。

### Bridge — LCTA_API ↔ JavaScript

```
Python → JS:
  webview.windows[0].evaluate_js("updateProgress(50)")

JS → Python:
  const result = await pywebview.api.install_llc()
```

`LCTA_API` 类的方法通过 pywebview 自动暴露给前端 JavaScript。JS 中可以直接调用 `pywebview.api.<method_name>()` 来执行 Python 方法。这种桥接模式使得前端可以像调用本地函数一样调用后端能力。

### Pipeline — Native Translation Engine

Rust 引擎采用阶段屏障与不可变快照组合：规则源文件串行建立依赖，普通文件并发消费冻结后的快照。文件并发、HTTP 请求并发和文件 I/O 并发分别限流，避免网络等待阻塞文件转换。

### Factory — Update Objects

`launcher/updates.py` 使用工厂模式创建不同类型的更新对象（LLC 更新、OurPlay 更新、机翻更新）。每种更新类型实现相同的接口，调用方无需关心具体类型。

## 多语言集成

### Python ↔ C

C 代码（`launcher.c`）仅在发布包中使用，作为 PE 入口点：
1. 查找捆绑的嵌入式 Python 解释器
2. 校验 Python 解释器的哈希值（防止篡改）
3. 调用 Python 执行启动脚本

编译使用 MinGW-w64 的 `gcc -mwindows`，`-mwindows` 标志抑制控制台窗口，使得双击 exe 时不会弹出命令行黑窗。资源文件（图标等）通过 `windres` 编译。

### Python → 外部二进制

- **CFST/cfst.exe**：通过 `subprocess.run()` 调用，解析 CSV 输出
- **7z.exe**：运行时从 GitHub 下载，通过 `subprocess` 调用进行压缩/解压
- **openspeedy**：通过 Python 包的 DLL 注入机制实现游戏变速

## 外部依赖

### 核心运行时依赖

| 包 | 版本 | 用途 | 备注 |
|----|------|------|------|
| pywebview | latest | 桌面窗口 | 依赖系统 WebView2 |
| UnityPy | 1.10.18 | Unity 资源提取/修改 | launcher 模组功能核心 |
| openspeedy | latest | 游戏变速 | DLL 注入 |
| etcpak | 0.9.8 | ETC 纹理压缩 | **必须固定版本**，0.9.9 崩溃 |
| keyboard | latest | 全局热键 | 启动器变速快捷键 |

### 外部二进制

| 二进制 | 来源 | 用途 |
|--------|------|------|
| cfst.exe v2.3.5 | 打包在 `CFST/` | Cloudflare CDN 测速 |
| 7z.exe | 运行时下载 | 压缩/解压 |
| Python 3.9.6 embeddable | 构建时下载 | 发布包内嵌解释器 |
| ChineseFont.ttf | LLC GitHub 仓库 | 中文字体渲染 |

## 架构决策记录

### ADR-1: 源码分发而非 PyInstaller 打包
**决策**：发布包直接包含 Python 源码 + 嵌入式解释器。
**理由**：避免杀毒软件误报；保持开源透明；支持增量更新。
**代价**：用户可直接看到/修改源码，增加了"破解"风险（但项目本身就是开源的）。

### ADR-2: launcher/ 代码隔离
**决策**：launcher/ 子目录与主项目在代码层面零 import。
**理由**：launcher/ 继承自 LimbusModLoader（GPL-3.0），必须保持许可证隔离。
**代价**：launcher/ 无法复用 webutils/ 中的工具函数（如配置访问），需要自己实现或通过 CLI 通信。

### ADR-3: 前端使用原生 JS 而非框架
**决策**：不引入 React/Vue 等前端框架。
**理由**：减少依赖数量；减小打包体积；项目前端复杂度适中，原生 JS 可维护。
**代价**：缺乏框架提供的状态管理和组件化能力，大型 UI 变更时需要更多手动管理 DOM。
