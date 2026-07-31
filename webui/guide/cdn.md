# CDN优选

测试并选择当前网络环境下最快的游戏CDN节点。该功能会对 Cloudflare 下载CDN 和 CloudFront API 服务器进行测速，并将选出的最优 IP 写入系统 hosts 文件，从而提升游戏的下载与连接速度。

---

### WebUI 使用

1. **查看当前生效 IP**：页面顶部显示已写入 hosts 的当前生效 IP（未设置时显示「未设置」）。CloudFront 支持多域名，会逐条显示域名与对应 IP。
2. **Cloudflare优选**：点击「Cloudflare优选」按钮，对游戏下载 CDN（`download.limbuscompanycdn.org` 等域名）进行测速。结果包含 IP地址、平均延迟、下载速度、丢包率。
3. **CloudFront优选**：点击「CloudFront优选」按钮，对游戏 API 服务器（`www.limbuscompanyapi.com`、`notice.limbuscompanyapi.com`）进行测速。结果按域名显示 IP地址与中位延迟。
4. **一键全优选**：依次执行 Cloudflare 与 CloudFront 的完整测速流程，一次获取全部优选结果。
5. **写入Hosts**：测速完成后点击「写入Hosts」，将优选 IP 写入系统 hosts 文件。该按钮在尚无测速结果时不可用；若测速结果与当前生效 IP 不同，页面会显示「测速结果尚未写入 hosts」提醒。

### 写入与移除 Hosts

- 写入 hosts 需要**管理员权限**。普通权限下程序会弹出 UAC 提权窗口，请在弹窗中选择「是」。
- 程序**仅修改受管标记块**（`# START-OF-LLC-BABEL-CF` / `# END-OF-LLC-BABEL-CF` 与 `# START-OF-LLC-BABEL-AMAZON` / `# END-OF-LLC-BABEL-AMAZON` 之间）的条目，不影响其他 hosts 记录。
- 写入成功后建议**刷新 DNS 缓存**（管理员命令行执行 `ipconfig /flushdns`）或重启游戏，新 IP 才会生效。
- 需要恢复时点击「移除当前CDN优选」按钮（仅在已有优选条目时显示），即可移除对应受管块，不影响其他 hosts 记录。

### Launcher 模式

在 Launcher 模式中开启「CDN优选」相关选项后，启动游戏前会自动完成测速；可通过「缓存有效期」设置控制测速结果的有效时间（小时），有效期内跳过测速直接使用已有 hosts，设为 0 表示每次启动都重新测速。

### 注意事项

- 修改 hosts 属于系统级操作，请勿手动篡改受管标记块之外的条目；如需还原，使用「移除当前CDN优选」即可。
- 测速优选的 CDN 节点可能随网络环境变化，若游戏出现下载或登录异常，可移除优选后重试。
- 若杀毒软件保护了 hosts 文件导致写入失败，请将本程序加入白名单或暂时关闭 hosts 保护后重试。

### 常见问题

**Q: 「写入Hosts」按钮是灰色的？**
A: 请先点击「Cloudflare优选」「CloudFront优选」或「一键全优选」获取测速结果。

**Q: 提示需要管理员权限？**
A: 请在 UAC 弹窗中选择「是」；若取消了弹窗，可右键程序图标 →「以管理员身份运行」后重试。

**Q: 写入后没有生效？**
A: 运行 `ipconfig /flushdns` 刷新 DNS 缓存，或重启游戏 / 系统。
