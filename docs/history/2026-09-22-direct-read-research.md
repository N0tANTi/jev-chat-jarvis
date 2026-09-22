# 微信 4.1.15.10 直接读取研究

日期：2026-09-22；目的：保留当前版本，研究可验证的直接消息读取路径。

## 已知证据

- 受支持的桌面工具定位到唯一 Weixin 进程窗口，置前前后结构输出均为 3 行，
  无消息列表、文档文字、焦点元素。未打印或持久化窗口标题/聊天正文。
- 这一观察不能排除工具过滤、独立窗口差异或其他无障碍接口，因此不认定新版必然无法读取。
- [pywechat #264](https://github.com/Hello-Mr-Crab/pywechat/issues/264) 报告 4.1.9.57+
  内部元素不可见；[作者说明](https://github.com/Hello-Mr-Crab/pywechat/blob/main/Weixin4.0.md)
  提及账号差异及讲述人方式失效。这是第三方报告，不能直接当作本机原因已确认。
- [hermes-wxauto 的 listener.py](https://github.com/doingSthing/hermes-wxauto/blob/main/src/my_wxauto/listener.py)
  仍使用 `Desktop(backend="uia")` 与 `descendants(control_type="ListItem")`。
  能参考会话批次、去重设计，无法据此断言绕过了空控件树。
- [wechat-sdk](https://github.com/chengamu/wechat-sdk/tree/1b678a2031429ba591163440a6f9519c4a2a208d)
  提供 MSAA 探测思路。其 `examples/probe_accessibility.py` 定义 `IID_IAccessible`
  却调用 `IID_IAccessIBLE`，原样会出错；示例输出不是本机验证结果。
- [wechatauto-replica](https://github.com/fanyuantaier/wechatauto-replica/tree/424ffdeeaa9e695191007614703ce78b96e7e6a9)
  README 区分了进程写入激活 Qt 控件树、数据库解密读取消息。即便树可见也不能据此证明
  普通 UIA 可直接读取完整正文。本项目既有约定不修改微信进程、不读数据库，因此未执行。

## 首轮交付

依据 Microsoft 的 [AccessibleObjectFromWindow](https://learn.microsoft.com/en-us/windows/win32/api/oleacc/nf-oleacc-accessibleobjectfromwindow)
和 [AccessibleChildren](https://learn.microsoft.com/en-us/windows/win32/api/oleacc/nf-oleacc-accessiblechildren)
接口独立实现 MSAA 结构探针，不复制上述项目代码。只遍历可见 Weixin 的窗口/客户区对象，
读取角色及子节点数，不读取 `accName` / `accValue`，不执行默认动作。

51 项测试通过，新增混合子对象/子 ID、环、数量/深度上限、错误与自定义角色脱敏、
进程失败和超时测试。本机 comtypes 1.4.17 可加载接口；未执行真实窗口 MSAA 查询。
代码 `048dab9` 已推送；[Windows CI](https://github.com/N0tANTi/jev-chat-jarvis/actions/runs/35705089024)
通过同一测试集和 COM 绑定加载检查。

当前 Computer Use 只暴露统一窗口状态查询，不暴露单独 MSAA；技能要求桌面操作仅用其 JS API。
故没有通过 shell 运行自写探针替代工具。将探针作为用户可运行的产品诊断入口交付，
首轮实机结果由用户启动后读取无正文摘要。不得把接口加载/单元测试描述成新版微信适配成功。

若 MSAA 有有效结构，下一阶段才做好友身份与消息读取验证；若无，保留 OCR。
消息读取可行性仍未验证，不凭假设开发自动发送。

## 用户实测与 v2 改进

用户先测主窗口，再打开独立聊天窗口重测。摘要分别发现 1 / 2 个可见窗口；
每个窗口 MSAA 客户区都是 24 节点、窗口对象 46 节点，角色分布相同，无错误和截断。
仅出现通用窗口/按钮/滚动条等角色，没有列表项、静态文本或文本角色。
这符合通用窗口外框的表现，但尚不能据此证明所有内部入口不可用。报告不含聊天正文且未入 Git。

v2 独立实现 [EnumChildWindows](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-enumchildwindows)
子窗口枚举，以及 [UIA 三视图](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-treeoverview)
的 TreeWalker 遍历。只读取数值控件类型和运行时 ID（ID 仅内存去重，不入报告），不请求名称/值。
子窗口限定同进程，节点、层数、窗口目标均有上限；45 秒超时保留已完成样本和挂起目标。

57 项测试通过，新增 UIA 树遍历、环/兄弟循环、预算、失败脱敏、部分超时保留和五路目标调度。
本机 MSAA/UIA COM 绑定均可加载，未由代理对真实微信运行 v2。用户需用原启动文件再运行一次。
当前结论仍为“原生消息未接通”，不是新版适配成功。
v2 代码 `dda76f4` 已同步至 fork；[Windows CI](https://github.com/N0tANTi/jev-chat-jarvis/actions/runs/35705963373)
通过 57 项测试和双接口初始化检查，实机结果仍待用户运行。

操作、限制和回退见 [诊断手册](../runbooks/wxauto-diagnostics.md)，任务见 [路线图](../../ROADMAP.md)。

## v2 实测与启动模式线索

用户完成 v2，摘要更新时间 2026-09-22 16:42:33：2 个顶层窗口，各 1 个原生子窗口，
共 20 组测量。UIA 三视图均只有顶层 Window+Pane（2 节点）及子窗口 Pane（1 节点）；
MSAA 顶层 24/46 节点，子窗口 1/23 节点。全部 0 错误，无截断/超时，未暴露消息类型。
这不是“因工具超时没读完”，也不是已经证明所有启动模式或账号都无法使用。

继续核查发现：

- [Qt 5.15 Windows UIA 源码](https://github.com/qt/qtbase/blob/5.15/src/plugins/platforms/windows/uiautomation/qwindowsuiaaccessibility.cpp)
  在处理 WM_GETOBJECT 时调用无障碍 setActive，再尝试返回 accessibleRoot。
  这解释了标准请求本应尝试激活，但不能证明微信使用未修改的这份 Qt 实现。
- [Qt 文档](https://doc.qt.io/qt-6/qaccessible.html) 的 `QT_LINUX_ACCESSIBILITY_ALWAYS_ON`
  针对 Unix/X11，不能拿来当 Windows 微信的修复开关。
- pywechat #264 的 [成功报告](https://github.com/Hello-Mr-Crab/pywechat/issues/264#issuecomment-4740890103)
  提出以 `--disable-gpu` 启动；另有 [失败报告](https://github.com/Hello-Mr-Crab/pywechat/issues/264#issuecomment-4742517984)。
  只是可测试假设，没有确认本机 4.1.15.10 接受该参数，也不能声称禁用 GPU 就会取消 Qt 或暴露消息。
- [#283](https://github.com/Hello-Mr-Crab/pywechat/issues/283) 继续报告讲述人无效，作者归因于账号/缓存；
  没有腾讯侧证据验证本机原因。未改注册表、未切换账号、未安排第三方代登录。

新增 `desktop/Start-WeChat-Compatibility.cmd` 供用户在方便时退出微信后启动实验。
只给本次启动附加参数，不终止已运行微信，不写持久设置。已有进程时直接停止，避免参数未生效的假对照。
本机安装路径存在已核实；脚本静态检查通过，尚未执行启动实验。运行后复用 v2，再按原快捷方式重启回退。

## 兼容启动后观察与首版免 OCR 入口

用户执行兼容启动并重测。主进程参数含 `--disable-gpu`；标准 Computer Use 工具看到
主窗口会话列表，独立聊天的 `chat_message_list` 以及 6 个 `chat_bubble_item_view` 正文。
本次检查的独立窗口属于群聊，仅用于结构观察，不用它推断单聊发送方向；不把正文写入仓库。
这证明本次运行可访问正文，未验证参数的唯一因果或 GPU 实际运行状态。

独立实现 `desktop/direct_reader.py`，只使用 UIA 读取属性，无动作/点击/进程内存接口。
显式选择独立单聊；群聊拒绝，窗口句柄、RuntimeId、AutomationId 校验；最多 1024 节点、30 条正文，
12 秒子进程硬超时。结构异常停止；未识别的发言人标为「待确认」，不能自动提交模型。
UI 本地轮询，变化清除旧建议；编辑即停止，人工核对后沿用生成和可选学习。

68 项本地测试通过，包括顺序/重复、群聊拒绝、未知结构、循环预算、多行隔离、
读取超时、身份变化、迟到结果及无云端调用。安装主程序 comtypes 依赖。
产品适配器未由代理通过 shell 对真实微信执行；真实单聊端到端待用户点击新入口。
原生实时自动回复仍未完成：下一步研究可信的发送者判定，不以正文可读替代方向验收。

用户随后打开独立单聊，标准工具再次取得相同消息列表及 6 个正文行，无群聊 ID。
消息行仍无工具可见的发送者标记，截图重试仍为 `SetIsBorderRequired 0x80004002`。
未猜测发言方向，未提交真实聊天给模型。代码 `ddfa590` 已推送，
[Windows CI](https://github.com/N0tANTi/jev-chat-jarvis/actions/runs/35708090446) 的 68 项测试及 COM 初始化检查通过。

## 一次校对的自动 OCR 衔接

用户已运行产品入口并展示含待确认正文的界面，要求避免每轮手工核对。
新增逐行「我 / 对方 / 忽略」点选，保留仅保存校对按钮；显式开启连续运行时说明云端截图/文字处理。
UIA 返回消息列表及标题矩形供自动绑定，DPI-aware 子进程提供物理坐标；不手动画框。
首帧 OCR 必须与双方至少各一条的已核对文本/方向/顺序一致，重复或缺失不放行。
通过后沿用自动画面稳定检测及生成链路，未知方向停止；识别期间新消息变化会重试，不要求再次校对。
自动读取前后检查原生窗口绑定与消息快照，生成交付沿用前台/标题/画面复核。

这是 OCR 连续模式的交互简化，不是从一次正文标注学到了所有未来消息的原生方向。
校准不持久化、不自动发送、不自动写记忆；窗口改变后需重启流程。78 项本地测试通过，
真实 UIA 坐标与 OCR 校准的端到端仍未验证，不宣称首帧校准保证未来准确率。

## 时间分隔行导致直读中止

用户反馈已截到画面但提示“直接读取未完成”。标准 Computer Use 只读检查发现：
当前消息列表有一个无 AutomationId 的 ListItem，名称严格匹配 HH:MM；其余为已支持的气泡项目。
旧 collect 对所有非气泡 ListItem 抛出 unknown row，随后子进程吞掉异常，统一提示兼容启动。
这解释了时间分隔符出现后现有读取器必然中止的故障，不能据该通用提示认定兼容模式失效。

修复仅忽略上述明确格式，保留真实气泡中的时间文本；未知系统项目不静默丢弃。
子进程只传白名单错误码，UI 分别说明超时、身份变化、未知行及接口失败，不暴露异常或正文。
91 项本地测试通过，新增时间分隔、时间正文、其他未知行及错误分类脱敏回归。
实机结构已确认，修复后的完整生成仍需用户重启助手试用，无需重新填密钥或降级微信。

### OCR 路径遗漏补修

用户再次反馈要求核对，截图文本包含“待确认：HH:MM”。上次只修 UIA 读取，
没有修自动 OCR 的 to_transcript，时间仍进入 parse_transcript 并导致自动流程暂停。
新增严格时间格式、居中短框、非绿色背景的联合过滤；不从所有文本中一概删除时间。
94 项本地测试通过，新增左右气泡时间保留、中央时间过滤，以及自动 OCR 完成后仍调度生成。
这不是用户漏勾选，也不是需要每轮重新校对；未知发言人仍会明确暂停。
