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
无授权时已有用户启动的自动 OCR 试用，见 [桌面说明](../../desktop/README.md)。

## 新版直接读取研究：MSAA 结构探针

UIA 标准工具在本机置前前后均只返回窗口根节点，尚未证明所有无障碍入口均不可用。
因此新增用户自行运行的 `desktop/Diagnose-WeChat.cmd`，独立探测 MSAA 客户区/窗口对象。
程序不读取名称、值或正文，不发送、不截屏、不联网、不修改微信；只输出节点计数及数字角色。
这不是回复生成入口，也不依赖 Plus。实机 MSAA 结果目前待验证。

1. 保持微信已登录并打开单聊，双击 `desktop/Diagnose-WeChat.cmd`。
2. 最多等待 25 秒，结果保存在 Git 忽略的 `_reports/wechat-msaa-summary.json`。
3. 可先测主窗口，再由用户手动打开同一聊天的独立窗口后重测。
   报告每次覆盖，不记录窗口标题，`window_index` 只表示本次枚举顺序。
4. `status=measured` 只表示完成结构测量；节点很多也不代表拿到了聊天消息。
   `unavailable`、`errors`、`truncated`、`timeout` 分别区分接口不可用、查询错误、
   截断与超时，不能解释成“微信没有消息”。
5. 若出现有效列表/文本子节点，再开发只读消息验证：联系人身份、顺序、方向、新增及切换。
   本探针始终返回 `message_reading_verified=false`，不自动开启任何监听。

依赖 `comtypes==1.4.17`，本机已有；在其他机器可执行：

```powershell
python -m venv desktop/.venv
desktop/.venv/Scripts/python.exe -m pip install -r desktop/accessibility-requirements.txt
```

最多测 8 个可见 Weixin 窗口，每个对象 256 节点、8 层；子进程硬超时只终止探针，不终止微信。
每次覆盖同一份无正文报告；无需额外备份，诊断完成后可删除。回退为不运行脚本，主程序无新依赖。
当前代理只使用受支持的 Computer Use 接口读取 UIA，不能通过自写 MSAA 脚本替代该工具操作微信。
因此已完成代码/模拟树测试及 COM 接口加载验证，实际 MSAA 查询须由用户启动。

研究依据、未经验证的假设见 [新版读取研究](../history/2026-09-22-direct-read-research.md)。

回退：主程序使用全局 Python，未依赖隔离环境中的 wxauto。保留隔离环境停用即可。
