# 2026-09-22 Windows 桌面试用链路

用户希望减少手机配置，接受使用 MinerU 云端 OCR，并授权复用本地 API 配置。
本机微信 4.1.15.10 的 UIA 预检只暴露窗口，未能读取正文；未接入需要特定微信版本、
激活码或数据库读取的 MCP。当前方案是独立桌面窗口、人工框选和复制回复。

## 交付

- `desktop/app.py`：Tk 界面、框选截图、预览、核对、复制、取消和快照状态提示。
- `desktop/service.py`：允许列表配置读取、MinerU 异步上传/轮询/坐标解析、DeepSeek/TypeSafe。
- `desktop/tests/`：21 项验证；`.github/workflows/desktop-trial.yml` 提供 Windows CI。
- `desktop/smoke.py`：三条模拟消息的完整线上验证，不采集屏幕、不使用真实聊天。
- `desktop/Start.cmd` 通用入口；本机 `start-local.cmd` 引用现有 env，被 Git 忽略。
- [桌面运行手册](../../desktop/README.md) 说明数据去向、配置、限制和测试命令。

所有请求使用直接 HTTPS；不跟随重定向，文件存储请求不携带 API 密钥；云端结果只读取
有大小上限的坐标 JSON，不解压到磁盘。聊天与截图不在本地落盘，剪贴板由用户管理。

## 验证与局限

- 本地 `python -m unittest discover -s desktop/tests -v`：21 tests，OK。
- 合成图 MinerU 识别 3/3 文字与发言方向正确；DeepSeek 三条候选、Jev 排序通过。
  一次总耗时 4.62 秒（其中 OCR 2.71 秒），可能受缓存/排队影响，不是性能承诺。
- 实测发现 DeepSeek 有时返回带 `text` 字段的对象数组；明确字符串数组提示词，并兼容该
  已见格式，继续严格校验三条非空回复。错误信息不包含原始聊天或密钥。
- 窗口启动已确认；控制工具视觉截图因 `SetIsBorderRequired failed: 0x80004002` 失败。
  产品框选、多屏缩放、真实微信截图与复制的人工验收尚未完成。
- OCR 对标题、时间、群昵称、长气泡可能误判。用户必须核对每行 `我/对方`，不自动发送。

回退：关闭桌面程序即可停止本地处理；已提交的云端请求不能撤回。Android 试用包未改动。
