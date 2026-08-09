# 🧰 LCTA - 边狱公司工具箱 (Limbus Company Transfer Auto)

一个功能全面的《边狱公司》游戏辅助工具集，提供汉化、管理、优化等一系列自动化功能。  
~~你不要问我为什么是transfer不是translate，我也想要改~~  
<img src='https://moe.8845.top/get/?name=LCTA&theme=moebooru'></img>

---

## ✨ 功能特点

- **翻译工具**：将游戏文本（韩/日/英文）自动翻译成中文，内置百度、Google、DeepL 等机翻与大量 LLM 适配；多阶段管线（消歧→翻译→自检）、专有名词匹配、并发处理、翻译日志查看
- **汉化包下载**：零协会、OurPlay、LCTA-AU 自动汉化等多平台汉化包一键下载与安装，支持 OurPlay 神人汉化、调爪文本修改包导入、字体精简、哈希校验与代理加速
- **安装已有汉化**：安装本地已有的汉化包文件，支持更换字体、导出系统字体
- **文本美化**：基于结构化规则（v2 / bus）修改语言包 JSON，支持文本替换、包裹、颜色渐变、技能属性着色；内置规则集编辑器、模板与智能生成，另有 LLM 文本美化窗口
- **CDN优选**：自动测速并选择最快的游戏 CDN 节点（Cloudflare 下载 + CloudFront API），写入系统 hosts 优化下载与连接体验
- **游戏资源更新**：提前预下载官方 Localize 与 AssetBundle 资源，减少版本更新后的等待，支持 Launcher 启动前自动预下载
- **游戏加速**：通过 DLL 注入 + 时间 API Hook 实现游戏变速（0.1x–10x），支持 Launcher 模式全局热键
- **输入反检测**：Hook CommonLib 的 RawInput 计数上报，控制游戏读取的合成/真实输入数据（auto/manual 模式）
- **作弊工具箱**：基于 MinHook 的原生游戏工具集，功能以加密形式分发，输入密钥解锁后使用
- **Metadata 恢复**：自动恢复 IL2CPP `global-metadata.dat` 的解密入口、参数与 31 段映射，输出可直接被修复版 Il2CppDumper 消费的正式 profile（含一键安装的 IDA 定位器插件）
- **已安装数据管理**：管理已安装汉化包、模组目录与 C 盘数据软链接，支持一键切换汉化版本
- **Launcher配置**：集成启动器，通过替换 Steam 启动命令实现汉化包自动更新、调爪文本自动导入、MOD 加载、文本美化、资源预下载、游戏加速、CDN 优选与图形化进度窗口
- **配置汉化API**：配置各端点 LLM 与各种机翻服务的 API 密钥与参数，内置预设 LLM 服务与在线测试功能
- **抓取专有词汇**：通过 ParaTranz API 抓取专有名词表并生成词汇文件（JSON/单文件/双文件），提高翻译一致性

作为LCTA_auto_update作者，添加 [LCTA_auto_update](https://github.com/HZBHZB1234/LCTA_auto_update) 自动翻译仓库，基于原文与零协会汉化，自动进行高质量LLM翻译，延时仅1-2小时。无需用户进行额外配置与操作，通过启动器自动获取更新。


---

## 🚀 快速开始

### 安装
1. 从 [Release 页面](https://github.com/HZBHZB1234/LCTA-Limbus-company-transfer-auto/releases) 下载最新版本
   > 文件下载指导  
   - LCTA-Portable-Full.zip 正常版本。推荐下载此版本  
   - LCTA-update.zip 完整版自动更新功能需求文件，包含项目源码 
2. 解压到任意目录
3. 运行 **可执行文件(.exe)** 即可启动工具箱

## 从源码安装 (不推荐)
1. 确保已安装 [Python 3.9.6](https://www.python.org/downloads) 及以上版本
2. 下载项目源码
3. 安装依赖：`pip install -r requirements.txt`
4. 运行 `python start_webui.py` 启动 WebUI；或 `python start_webui.py -launcher` 启动集成启动器

### 构建发布包
运行 `.\build.ps1` 完成完整构建打包，产物输出到 `dist/` 目录：
- `LCTA-Portable-Full.zip` — 正常版本
- `LCTA-update.zip` — 源码更新包

构建要求：
- PowerShell 5.0+
- MinGW-w64（gcc + windres，用于编译 C 启动器；不可用时自动跳过）
- 网络连接（首次需下载嵌入式 Python 3.9.6）

---

## 🔗 相关链接

### 开发与发布
- **GitHub 项目**：[HZBHZB1234/LCTA-Limbus-company-transfer-auto](https://github.com/HZBHZB1234/LCTA-Limbus-company-transfer-auto)
- **自动汉化仓库**：[LCTA_auto_update](https://github.com/HZBHZB1234/LCTA_auto_update)
- **翻译工具库**：[Py-Translate-Kit](https://github.com/HZBHZB1234/Py-Translate-Kit)
- **游戏变速库**：[PyOpenSpeedy](https://github.com/HZBHZB1234/pyOpenSpeedy)
- **global-metadata解密**：[LimbusMetadataRecovery](https://github.com/HZBHZB1234/LimbusMetadataRecovery)
- **适配版Il2cppDumper**：[Il2CppDumper](https://github.com/HZBHZB1234/Il2CppDumper)

### 作者与社区
- **B站主页**：[ygdtpnn](https://space.bilibili.com/3493119444126599)  
- **介绍视频**：[LCTA 工具箱演示](https://www.bilibili.com/video/BV1iuAUzHEmA)  
- **最新版本介绍**: [介绍视频](https://www.bilibili.com/video/BV1F3wxzfEt6)
  > ⚠️ 注：视频可能非最新，请以项目实际版本为准
- **GitHub 作者**：[HZBHZB1234](https://github.com/HZBHZB1234)
- **意见反馈**：[Issues 页面](https://github.com/HZBHZB1234/LCTA-Limbus-company-transfer-auto/issues)
- **QQ 交流群**：1081988645
- **贴吧昵称**：HZBHZB31415926

---

## 📄 许可证声明

### 主程序
本项目基于 **[MIT 许可证](https://github.com/HZBHZB1234/LCTA-Limbus-company-transfer-auto/blob/main/LICENSE)** 发布。

### 资源与引用
- `favicon.ico` 来自 [边狱公司中文维基](https://limbuscompany.huijiwiki.com/wiki/%E9%A6%96%E9%A1%B5)，遵循其原有使用条款。
- `launcher` 文件夹内的部分代码基于 [LimbusModLoader](https://github.com/LEAGUE-OF-NINE/LimbusModLoader) 实现，遵循 **[GPL-3.0 许可证](https://github.com/LEAGUE-OF-NINE/LimbusModLoader/blob/master/LICENSE)**。  
  > 💡 注意：`launcher` 目录下的所有代码均遵循 GPL-3.0。LCTA 主程序与启动器之间仅为配置与调用关系，无代码依赖，因此主程序不受 GPL-3.0 约束。
- `webFunc/LanzouFolder.py` 来自互联网 *吾爱破解* 论坛。经过修改。[原文链接](https://www.52pojie.cn/thread-2005690-1-1.html)
- 部分前端依赖代码引用自互联网，遵循其原有使用条款。前端依赖详细信息请查看 [InitCode.py](https://github.com/HZBHZB1234/LCTA-Limbus-company-transfer-auto/blob/main/.github/InitCode.py)
- `tools/cfst/cfst.exe`（CloudflareSpeedTest v2.3.5）来自 [CloudflareSpeedTest](https://github.com/XIU2/CloudflareSpeedTest)，遵循 **[GPL-3.0 许可证](https://github.com/XIU2/CloudflareSpeedTest/blob/master/LICENSE)**。该工具以独立进程方式被调用，CDN 优选模块的主程序代码不受 GPL-3.0 约束。同目录下的 `ip.txt` 候选地址文件也来源于 CloudflareSpeedTest 项目。
- CDN 优选功能的设计参考了 [LLC_BABEL](https://github.com/LocalizeLimbusCompany/LLC_BABEL)（MIT License, Copyright (c) 2026 ZengXiaoPi）。本项目采用 Python 独立实现，不包含 LLC_BABEL 的 .NET 代码。
- `tools/aria2/aria2c.exe`（aria2 v1.37.0）来自 [aria2](https://github.com/aria2/aria2)，遵循 **[GPL-2.0-or-later 许可证](https://github.com/aria2/aria2/blob/master/COPYING)**。该工具以独立进程方式被调用，官方资源预下载模块的主程序代码不受 GPL-2.0-or-later 约束。随包附带的 `COPYING` 文件即其许可证文本。
- MinHook（私有仓库 `LCTA_CheatingCore` 的 `vendor/minhook`，随作弊工具箱编译进 hook DLL）来自 [MinHook](https://github.com/TsudaKageyu/minhook)，遵循 **[BSD 3-Clause 许可证](https://github.com/TsudaKageyu/minhook/blob/master/LICENSE.txt)**。
- **作弊者工具箱（Cheater's Toolbox，`LCTA_CheatingCore` 私有仓库）**：**No License（无许可证）**。该仓库未附带任何开源许可证，默认保留所有权利，未经作者书面许可不得复制、修改、分发或商用其代码；随包加密分发的 `cheat_core.bin` 亦遵循此约定。

### 数据许可
- **零协会汉化包**：遵循 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) 许可。
- **自动汉化包**：遵循 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) 许可。
- **用户自制汉化数据**：可自行选择许可协议，但需兼容所基于汉化包的原有许可。

---

## ⚠️ 免责声明

本项目为开源工具，旨在为《边狱公司》玩家提供便利，使用者应自行承担因使用本工具而产生的任何风险，包括但不限于：

- 游戏账号异常
- 客户端文件损坏
- 系统兼容性问题

作者及贡献者不对任何直接或间接损失承担法律责任。
