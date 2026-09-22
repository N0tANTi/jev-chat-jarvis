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

## 本次交付与未完成项

依据 Microsoft 的 [AccessibleObjectFromWindow](https://learn.microsoft.com/en-us/windows/win32/api/oleacc/nf-oleacc-accessibleobjectfromwindow)
和 [AccessibleChildren](https://learn.microsoft.com/en-us/windows/win32/api/oleacc/nf-oleacc-accessiblechildren)
接口独立实现 MSAA 结构探针，不复制上述项目代码。只遍历可见 Weixin 的窗口/客户区对象，
读取角色及子节点数，不读取 `accName` / `accValue`，不执行默认动作。

51 项测试通过，新增混合子对象/子 ID、环、数量/深度上限、错误与自定义角色脱敏、
进程失败和超时测试。本机 comtypes 1.4.17 可加载接口；未执行真实窗口 MSAA 查询。

当前 Computer Use 只暴露统一窗口状态查询，不暴露单独 MSAA；技能要求桌面操作仅用其 JS API。
故没有通过 shell 运行自写探针替代工具。将探针作为用户可运行的产品诊断入口交付，
实机结果待用户启动后读取无正文摘要。不得把接口加载/单元测试描述成新版微信适配成功。

若 MSAA 有有效结构，下一阶段才做好友身份与消息读取验证；若无，保留 OCR。
独立聊天窗口差异、MSAA、UIA RawView 的可行性均未验证，不凭假设开发自动发送。

操作、限制和回退见 [诊断手册](../runbooks/wxauto-diagnostics.md)，任务见 [路线图](../../ROADMAP.md)。
