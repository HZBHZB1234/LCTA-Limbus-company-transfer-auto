# 🧰 LCTA - 边狱公司工具箱 (Limbus Company Transfer Auto)

一个功能全面的《边狱公司》游戏辅助工具集，提供汉化、管理、优化等一系列自动化功能。

---

## ✨ 功能特点

- ✅ **汉化安装与管理**：支持零协会汉化包、OurPlay 汉化包的下载与安装
- 🔄 **自动汉化更新**：自动获取并应用最新的汉化资源
- ⚙️ **API 配置与测试**：方便用户配置并测试翻译 API
- 🚀 **集成启动器**：快速启动游戏并管理汉化包版本
- 💭 **气泡mod一键下载**：自动爬取并更新气泡mod
- 🧹 **缓存清理工具**：清理游戏缓存，消除错误数据 (暂不保证可用性)
- 📚 **零协会专有名词抓取**：自动提取翻译术语以支持翻译
- 🧩 **模块化设计**：各功能独立，便于维护与扩展

## ✨ 特色功能
作为LCTA_auto_update作者，添加 [LCTA_auto_update](https://github.com/HZBHZB1234/LCTA_auto_update) 自动翻译仓库，基于原文与零协会汉化，自动进行高质量LLM翻译，延时仅3-5小时。无需用户进行额外配置与操作，通过启动器自动获取更新。


---

## 🚀 快速开始

### 安装
1. 从 [Release 页面](https://github.com/HZBHZB1234/LCTA-Limbus-company-transfer-auto/releases) 下载最新版本
  > 文件下载指导  
  LCTA-Portable-Full.zip 完整版全功能，空间占用较大。推荐下载此版本  
  LCTA-Folder.zip 兼容版文件夹版  
  LCTA-Folder-Debug.zip 兼容调试版，显示命令窗口  
  LCTA-OneFile.zip 兼容版单文件版  
  LCTA-OneFile-Debug.zip 兼容调试版，显示命令窗口  
  LCTA-update.zip 完整版自动更新功能需求文件，包含项目源码  
2. 解压到任意目录
3. 运行 **可执行文件(.exe)** 即可启动工具箱

## 从源码安装 (不推荐)
1. 确保已安装 [Python3.96](https://www.python.org/downloads) 及以上版本python
2. 下载项目源码
3. 运行 `pip install -r requirements.txt` 安装依赖
4. 运行 **start_webui.py**
  > 为加速启动速度，请运行[.github\InitCode.py](https://github.com/HZBHZB1234/LCTA/blob/main/.github/InitCode.py)以本地化网络资源  
  > **注：** 运行 **InitCode.py** 时请确保已安装 **requests** 模块  

---

## 📅 开发计划 (TODO)

- 统一配置与函数调用逻辑  
- 统一日志逻辑，使用单例化日志管理器  
- 添加 MOD 制作工具  
- 添加 MOD 管理界面  
- 添加 C 盘链接创建功能  
- 优化界面布局，合并重复页面  
- 添加气泡 MOD 下载功能  
- 集成letheLauncher功能
- 下载气泡自动Fallback

---

## ❗ 已知问题

> 目前所有已知问题已解决。  
> 如遇到新问题，欢迎提交至 [Issues](https://github.com/HZBHZB1234/LCTA-Limbus-company-transfer-auto/issues)。

---

## 🔗 相关链接

### 开发与发布
- **GitHub 项目**：[HZBHZB1234/LCTA-Limbus-company-transfer-auto](https://github.com/HZBHZB1234/LCTA-Limbus-company-transfer-auto)
- **自动汉化仓库**：[LCTA_auto_update](https://github.com/HZBHZB1234/LCTA_auto_update)
- **翻译工具库**：[Py-Translate-Kit](https://github.com/HZBHZB1234/Py-Translate-Kit)

### 作者与社区
- **B站主页**：[ygdtpnn](https://space.bilibili.com/3493119444126599)  
- **最新介绍视频**：[LCTA 工具箱演示](https://www.bilibili.com/video/BV1v54y1X7jY)  
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
