# 当前状态

日期：2026-09-22。上游基线 `d872052`，fork 为 `N0tANTi/jev-chat-jarvis`，
Android 修复分支 `codex/session-safety-fixes`；当前桌面开发分支 `codex/desktop-mineru-trial`。

## 独立自动采集试用（2026-09-22 最新）

- 用户没有 Plus 授权，要求参考开源实现适配本机微信。只读 UIA 再检仅得到窗口根节点，
  无消息列表；开源 wxauto4 依赖的 `MessageView` / `ListControl` 无法定位。
- 新增独立 `desktop/watcher.py`：默认关闭，用户框选消息及标题后，在微信前台检测画面变化，
  稳定后调用 MinerU → DeepSeek → Jev；无需 wxauto/Plus，不复制其源码，不修改微信进程。
- 标题变化或窗口移动停止；后台/遮挡暂停；输出和下一阶段提交前复核原画面，丢弃迟到结果。
  自动 OCR 不写长期记忆；角色与已选好友档案仍参与生成。没有自动填入或发送。
- 本地 45 项测试通过（9 项新增合成画面/状态测试），没有采集或上传真实微信正文。
  新流程尚待用户在微信 4.1.15.10 实测，不能宣称已完成原生消息接口适配。
- 依赖可见前台窗口、云端 OCR 延迟；像素标题不等于稳定联系人身份，同名/短暂切换/局部遮挡
  仍可能漏检。仅单聊试用。操作与回退见 [桌面说明](desktop/README.md#自动更新试用无需-plus)。
- 决策与验证见 [本次记录](docs/history/2026-09-22-visible-watcher.md)。

## 角色与好友记忆 / wxauto 验证（2026-09-22 先前阶段）

- 新增全局说话角色、按 UUID 隔离的好友档案、手工确认背景、UTF-8 历史导入。
- DeepSeek 从选定好友历史提取有消息依据的观察，标记为模型推测；保留三版旧观察，
  不覆盖用户事实。用户可开启生成后的增量学习，也可清除观察或历史、关闭学习。
- 生成与 Jev 排序都收到有上限的角色/背景/历史/观察；切换好友清空旧聊天与临时关系。
- 本地 36 项测试通过，包括持久化、同名好友隔离、写入失败保留原文件、多窗口冲突、
  迟到标签拒绝及隐藏 Tk 窗口构造/切换回归。未进行新增界面的视觉验收。
- 代码 `e6b1ae7` 已推送，Windows CI 同样通过：
  [Desktop trial #35702176771](https://github.com/N0tANTi/jev-chat-jarvis/actions/runs/35702176771)。
- 合成历史线上验证通过：初次 2 条标签，补充历史后 3 条，确认事实保留、旧版保留，
  带记忆生成三条候选和 Jev 排序成功。尚无真实历史的质量对照评估。
- wxauto 已在隔离环境安装；修复 MCP SDK 2.x 不兼容，固定 1.30.0 后 CLI 加载成功。
  授权检查 `active: false`，用户没有激活码；没有读取微信正文或接通实时监听。
  免费版当前只支持到 4.1.8.107，不能据此确认本机 4.1.15.10 可用。
- 运行与存储见 [桌面说明](desktop/README.md)；兼容检查见
  [wxauto 诊断手册](docs/runbooks/wxauto-diagnostics.md)。

## Windows 桌面试用版（2026-09-22）

- 已新增 `desktop/`：手动框选或导入截图、预览、MinerU VLM OCR、编辑核对发言人、
  DeepSeek `deepseek-flash` 非思考模式起草三条、TypeSafe Jev 判断排序、复制候选。
- 启动不采集、不上传；用户点击识别才上传裁剪图，点击生成才发送核对后的文字。
  本机现有 `.env` 通过本地忽略的启动脚本引用，无需重新填写密钥。
- 编辑、新截图、清空取消旧任务并废弃迟到结果；本版不跟踪当前联系人、不自动填入或发送。
- 本地 21 项单元/状态测试通过。完整链路仅用合成图片实测：三条文字和方向均正确，
  三条候选生成并排序；一次样例 OCR 2.71 秒，总耗时 4.62 秒。不能推断日常稳定延迟。
- 桌面代码提交 `c69199c` 已推送，Windows GitHub CI 的 21 项测试也通过：
  [Desktop trial #35700001335](https://github.com/N0tANTi/jev-chat-jarvis/actions/runs/35700001335)。
- 本机 Python 3.13.14、Pillow 12.2.0；窗口已启动并通过窗口枚举确认。
  Windows 控制工具截图失败：`SetIsBorderRequired failed: 0x80004002`，未完成视觉验收，
  不等同于产品自身截屏失败。真实微信框选、混合 DPI / 多屏和复制操作待用户试用。
- 本机微信 4.1.15.10 的 UIA 预检未读到消息正文，当前使用截图方案，尚未集成微信 MCP。
- 桌面运行手册见 [desktop/README.md](desktop/README.md)，
  里程碑见 [桌面历史记录](docs/history/2026-09-22-desktop-trial.md)。

## 已实现

- 会话、窗口、消息版本绑定；异步判断/候选/OCR 的过期结果丢弃。
- 单轮分析等待两个分支完成；新消息合并排队，候选先返回时不再丢失。
- 回填前和每次延迟重试前复核会话；保留已有草稿；OCR 无法核验时只复制。
- 加载中标题不再沿用上个联系人；不再把 OCR 消息当联系人标题；日志移除会话标题。
- 历史记录不再把无重叠的新消息整屏丢弃；缺少时间戳/消息 ID 的局限仍在。
- API 密钥仅同 HTTPS 来源继承；禁止自动 HTTP 重定向，错误响应脱敏。
- 独立试用包、回归单元测试及 GitHub 构建工作流。

## 已验证

- 使用用户授权的本地 TypeSafe 配置运行上游 30 条样例：30/30 HTTP 200；
  true_intent 86.7%，she_needs 80.0%，danger_level MAE 0.495；门槛通过。
  平均请求延迟 0.577 秒；这不是完整回复耗时，也不是独立准确率评测。
- 两次合成数据请求验证 Android 的 me/other、background/history 字段、7 项判断和
  3 个候选的排序响应。未调用用户真实聊天数据。
- 用户选择 DeepSeek V4.1 Flash，官方 API ID `deepseek-flash`；账号模型列表已核实。
  本地密钥实测“Flash 非思考模式生成 3 条 → Jev 排序 3 条”通过。
- 最终 Android 代码提交 `6f13c06` 已通过 15 项单元测试（0 失败）、APK 构建、lint
  （0 阻断错误、27 项警告，含依赖版本、目标 SDK、国际化、无障碍触摸等建议）。
  [CI 验证与下载](https://github.com/N0tANTi/jev-chat-jarvis/actions/runs/35697258673)。
- APK 已下载并检查清单：包名 `com.jev.probe.trial`，版本 `1.3-session-fix`，
  28,112,449 字节。解包扫描未发现用户两把 API 密钥。
  本地文件 `app/build/outputs/apk/trial/jev-session-fix-flash.apk` 被 Git 忽略。
  SHA-256：`105bab8463359d1b6f4460a27a19876ff07a016a732f53a69dfbe7e049ca5cff`。

## 尚未验证

- 无本地 Android 设备；真机安装、微信采集、悬浮窗、回填和后台续航尚未验证。
- 手机端仍需填写两把密钥，均未放入源码、CI 或 APK。
- 同名会话、群聊、OCR 方向与不同微信版本适配仍有限制。

修复代码已推送到 fork；本次记录随交付同步。最新记录提交可能晚于 APK 的代码提交，
安装包以以上 CI 和哈希为准。

试用步骤见 [运行手册](docs/runbooks/android-trial.md)，后续工作见 [路线图](ROADMAP.md)。
