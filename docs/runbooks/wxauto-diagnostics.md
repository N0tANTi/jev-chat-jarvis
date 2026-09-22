# Windows wxauto 兼容检查

实测日期 2026-09-22。本机微信 4.1.15.10、Python 3.13.14。

隔离环境 `desktop/.venv/` 被忽略；用 `desktop/wxauto-requirements.txt` 安装。
`desktop/.venv/Scripts/python.exe -m desktop.wxauto_probe` 只检查包版本和激活状态，
不读取聊天、不注册 MCP、不执行微信 UI 操作。

已验证：

- wxautox4 41.1.1.post1 / wxauto-mcp 1.0.2 安装成功。
- 未限制 MCP SDK 时安装了 2.2.0，CLI 因 `AttributeError: Server has no attribute list_tools` 失败。
- 固定 mcp 1.30.0 后 `wxauto-mcp --help` 成功。
- `wxautox4 --json auth check` 返回 `active: false`。用户没有激活码。

尚未验证：微信正文读取、当前聊天身份、新消息监听。不能将安装成功表述成客户端兼容。
免费版作者文档目前只支持至 4.1.8.107：[安装与激活](https://docs.wxauto.org/docs/install.html)。

下一步若获得有效授权，先做用户指定会话的只读验证，核对会话身份和消息方向，再开放监听。
不自动调用 `--install` 注册整套发送/加好友工具，不购买、不降级、不修改微信进程。
无授权时可另行实现用户启动的自动 OCR 方案，但目前尚未实现。

回退：主程序使用全局 Python，未依赖隔离环境中的 wxauto。保留隔离环境停用即可。
