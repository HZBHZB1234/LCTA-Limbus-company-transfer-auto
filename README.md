# 🧰 LCTA - 边狱公司工具箱 (Limbus Company Transfer Auto)

一个功能全面的《边狱公司》游戏辅助工具集，提供汉化、管理、优化等一系列自动化功能。  
~~你不要问我为什么是transfer不是translate，我也想要改~~  
<img src='https://moe.8845.top/get/?name=LCTA&theme=moebooru'></img>

---

## ✨ 功能特点

- ✅ **汉化安装与管理**：支持零协会汉化包、OurPlay 汉化包的下载与安装
- 🔄 **自动汉化更新**：自动获取并应用最新的汉化资源
- ⚙️ **API 配置与测试**：方便用户配置并测试翻译 API
- 🚀 **集成启动器**：快速启动游戏并管理汉化包版本
- 💭 **气泡语言包一键下载**：自动爬取并更新气泡语言包
- 🧹 **缓存清理工具**：清理游戏缓存，消除错误数据 (暂不保证可用性)
- 📚 **零协会专有名词抓取**：自动提取翻译术语以支持翻译
- 🧩 **模块化设计**：各功能独立，便于维护与扩展
- 🌐 **CDN优选**：自动测速并选择最快的游戏CDN节点（Cloudflare + CloudFront），优化下载与API连接体验

## ✨ 特色功能
作为LCTA_auto_update作者，添加 [LCTA_auto_update](https://github.com/HZBHZB1234/LCTA_auto_update) 自动翻译仓库，基于原文与零协会汉化，自动进行高质量LLM翻译，延时仅3-5小时。无需用户进行额外配置与操作，通过启动器自动获取更新。


---

## 🚀 快速开始

### 安装
1. 从 [Release 页面](https://github.com/HZBHZB1234/LCTA-Limbus-company-transfer-auto/releases) 下载最新版本
   > 文件下载指导  
   - LCTA-Portable-Full.zip 正常版本。推荐下载此版本  
   - LCTA-Portable-Full-Compatible.zip 兼容版，空间占用较大且存在可能出现的UI界面错误，请在无法使用正常版本时使用该版本  
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
- `LCTA-Portable-Full-Compatible.zip` — 兼容版（含 PyQt 后备）
- `LCTA-update.zip` — 源码更新包

构建要求：
- PowerShell 5.0+
- MinGW-w64（gcc + windres，用于编译 C 启动器；不可用时自动跳过）
- 网络连接（首次需下载嵌入式 Python 3.9.6）

---

## 📅 开发计划 (TODO)

- 添加专有名词分析功能
- 统一配置与函数调用逻辑  
- 添加 MOD 制作工具  
- 集成letheLauncher功能
- 使用vue重构webui
<details>
  <summary>点击展开已完成功能</summary>
  <ul>
    <li>下载气泡自动Fallback</li>
    <li>修复已安装数据管理页面汉化包相关功能未预期工作问题</li>
    <li>添加 C 盘链接创建功能</li>
    <li>修改字体文件修改功能，使其可以自己选择字体</li>
    <li>添加更新后自动显示更新内容窗口</li>
    <li>优化新手指导</li>
    <li>添加美化功能</li>
    <li>添加运行环境自动诊断</li>
    <li>修复在win11系统环境下由于cmd默认启动终端导致无法正确隐藏控制台</li>
    <li>统一日志逻辑，使用单例化日志管理器 </li>
  </ul>
</details>
<details>
  <summary>点击展开已放弃功能</summary>
  <ul>
  </ul>
</details>
<details>
  <summary>点击展开现已证实早已完成或不存在的功能</summary>
  <ul>
    <li>修复汉化相关非预期日志问题</li>
    <li>修复汉化相关非预期漏翻问题</li>
    <li>修复安装汉化包不会自动切换的问题</li>
  </ul>
</details>

---

## 🔗 相关链接

### 开发与发布
- **GitHub 项目**：[HZBHZB1234/LCTA-Limbus-company-transfer-auto](https://github.com/HZBHZB1234/LCTA-Limbus-company-transfer-auto)
- **自动汉化仓库**：[LCTA_auto_update](https://github.com/HZBHZB1234/LCTA_auto_update)
- **翻译工具库**：[Py-Translate-Kit](https://github.com/HZBHZB1234/Py-Translate-Kit)

### 作者与社区
- **B站主页**：[ygdtpnn](https://space.bilibili.com/3493119444126599)  
- **介绍视频**：[LCTA 工具箱演示](https://www.bilibili.com/video/BV1iuAUzHEmA)  
- **最新版本介绍**: [介绍视频]([https://www.bilibili.com/video/BV1F3wxzfEt6)
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
- `CFST/cfst.exe`（CloudflareSpeedTest v2.3.5）来自 [CloudflareSpeedTest](https://github.com/XIU2/CloudflareSpeedTest)，遵循 **[GPL-3.0 许可证](https://github.com/XIU2/CloudflareSpeedTest/blob/master/LICENSE)**。该工具以独立进程方式被调用，CDN 优选模块的主程序代码不受 GPL-3.0 约束。同目录下的 `ip.txt` 候选地址文件也来源于 CloudflareSpeedTest 项目。
- CDN 优选功能的设计参考了 [LLC_BABEL](https://github.com/LocalizeLimbusCompany/LLC_BABEL)（MIT License, Copyright (c) 2026 ZengXiaoPi）。本项目采用 Python 独立实现，不包含 LLC_BABEL 的 .NET 代码。

### 数据许可
- **零协会汉化包**：遵循 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) 许可。
- **自动汉化包**：遵循 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) 许可。
- **用户自制汉化数据**：可自行选择许可协议，但需兼容所基于汉化包的原有许可。

---

## ⚠️ 免责声明

本项目为开源工具，旨在为《边狱公司》玩家提供便利。尽管本项目没有任何违反ProjectMoon服务条款的功能与行为，处于免责考虑，使用者应自行承担因使用本工具而产生的任何风险，包括但不限于：

- 游戏账号异常
- 客户端文件损坏
- 系统兼容性问题

作者及贡献者不对任何直接或间接损失承担法律责任。
