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

## 新版直接读取研究：v2 结构探针

UIA 标准工具在本机置前前后均只返回窗口根节点，尚未证明所有无障碍入口均不可用。
用户自行运行 `desktop/Diagnose-WeChat.cmd`。v2 同时探测顶层窗口、同进程原生子窗口，
分别遍历 UIA Raw/Control/Content 三种视图及 MSAA 客户区/窗口对象。
程序不读取名称、值或正文，不发送、不截屏、不联网、不修改微信；只输出节点计数及数字角色。
这不是回复生成入口，也不依赖 Plus。v1 实测两种窗口均返回 MSAA 客户区 24 / 窗口 46 节点，
无列表或文本角色，不能当作消息读取成功；v2 的子窗口与三视图结果待实测。

1. 保持微信已登录并打开单聊，双击 `desktop/Diagnose-WeChat.cmd`。
2. 确认开头显示 V2，最多等待 45 秒，结果保存在 Git 忽略的 `_reports/wechat-msaa-summary.json`。
3. 可同时打开主窗口及独立聊天窗口，一次采集；`schema_version=2` 表示新探针。
   报告每次覆盖，不记录窗口标题，`window_index` 只表示本次枚举顺序。
4. `status=measured` 只表示完成结构测量；节点很多也不代表拿到了聊天消息。
   `unavailable`、`errors`、`truncated`、`timeout` 分别区分接口不可用、查询错误、
   截断与超时，不能解释成“微信没有消息”。`partial_timeout` 保留已完成样本，
   `pending_target` 标明超时时未完成的目标/API/视图。没有返回的目标不等于空树。
5. 若出现有效列表/文本子节点，再开发只读消息验证：联系人身份、顺序、方向、新增及切换。
   本探针始终返回 `message_reading_verified=false`，不自动开启任何监听。

依赖 `comtypes==1.4.17`，本机已有；在其他机器可执行：

```powershell
python -m venv desktop/.venv
desktop/.venv/Scripts/python.exe -m pip install -r desktop/accessibility-requirements.txt
```

最多枚举 8 个可见顶层 Weixin 窗口，每窗口最多 16 个同进程子窗口（包含隐藏子窗口），
总共检测至多 24 个原生窗口目标。每个 MSAA 对象限 256 节点/8 层，UIA 视图限 256 节点/12 层。
先测顶层窗口再测子窗口，超时或预算截断明确标记；子进程硬超时只终止探针，不终止微信。
每次覆盖同一份无正文报告；无需额外备份，诊断完成后可删除。回退为不运行脚本，主程序无新依赖。
当前代理只使用受支持的 Computer Use 接口读取 UIA，不能通过自写 MSAA 脚本替代该工具操作微信。
因此已完成代码/模拟树测试及 COM 接口加载验证，v2 实机查询仍须由用户启动。

研究依据、未经验证的假设见 [新版读取研究](../history/2026-09-22-direct-read-research.md)。

回退：主程序使用全局 Python，未依赖隔离环境中的 wxauto。保留隔离环境停用即可。

## 可选启动参数实验（未验证修复）

更新：本机用户执行后已恢复 UIA 会话/正文控件，可保持此次微信运行试用
[免 OCR 入口](../../desktop/README.md#直接读取试用免-ocr发言人仍需核对)。
这是一次实测结果，不保证其他账号/启动/版本可复现；发言人仍未验证。
以下保留实验及回退步骤。

v2 已完成：两个顶层窗口及各自子窗口共 20 组测量，无错误/截断，仍仅通用窗口结构。
下一假设来自 pywechat #264 的用户反馈：`--disable-gpu`，同时存在失败反馈。

1. 保存正在编辑的内容，从微信托盘菜单正常退出（仅关闭窗口可能仍在后台运行）。
2. 双击 `desktop/Start-WeChat-Compatibility.cmd`。已有 Weixin 进程时脚本会退出，不会强行结束它。
3. 正常登录并打开同样的聊天，运行 `desktop/Diagnose-WeChat.cmd`，比较是否出现新的消息控件。
4. 无变化就不重复相同实验。出现新控件也仍需后续验证正文、身份、方向、顺序和切换。
5. 回退：正常退出微信，使用原来的微信快捷方式启动。脚本不改注册表、启动项或微信文件。

当前启动器针对 `%ProgramFiles%/Tencent/Weixin/Weixin.exe`，本机路径已核实；不同安装路径会停止。
这是临时启动参数试验，不保证微信识别参数、不保证 GPU 实际关闭、不保证恢复无障碍树。
若渲染异常或卡顿，按回退步骤恢复；现有聊天数据无需搬动。程序未替用户执行退出或登录。
