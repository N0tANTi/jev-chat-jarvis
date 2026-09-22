# Jev 桌面试用版

Windows 10/11，Python 3.11+（含 Tk），Pillow。使用已有 Jev 题目集，独立于 Android 构建。

```powershell
python -m pip install -r desktop/requirements.txt
python -m desktop.app --env-file "本机已有的.env路径"
```

在仓库根目录执行。也可双击 `desktop/Start.cmd`，默认读取 `desktop/.env`。
只需要三个变量：`MINERU_API_TOKEN`、`DEEPSEEK_API_KEY`、`TYPESAFE_API_KEY`。
进程环境优先；密钥不显示在界面，不写入日志。用户授权的本地 `.env` 被 Git 忽略。

1. 打开微信单聊，点击「截取聊天」，拖动框选消息气泡；Esc 取消。也可导入截图。
2. 在预览中检查范围，再点击「识别聊天」。所选截图上传 MinerU 云端，等待异步 OCR。
3. 核对发言人和顺序，删除标题、时间及系统提示。每条一行，格式 `我：内容` / `对方：内容`。
4. 勾选核对完成，点击「生成回复」。DeepSeek `deepseek-flash` 非思考模式生成三条，TypeSafe Jev `jev-latest` 判断排序。
5. 点击「复制」，回微信确认当前联系人，自行粘贴发送。切换聊天后重新截图。

可以不使用 OCR：直接在文字框粘贴上述格式的聊天，勾选核对后生成。
本地快捷启动文件 `start-local.cmd` 可引用现有 env 路径，属于忽略项，不上传。

## 数据边界与限制

- 启动不截屏、不调用 API。不接管微信、不自动发送、不读聊天数据库、不做 MCP 伪接入。
- 截图、识别内容和候选只在本次进程内存中保留；复制内容会留在系统剪贴板。
- 截图发送 MinerU；核对后的聊天和关系描述发送 DeepSeek / TypeSafe。云端留存由各服务政策决定。
- 关闭或清空会取消本地后续处理并忽略迟到结果；已经提交的云端任务无法撤回。
- 首版只适用于可见的单聊消息。裁剪范围由人选择；标题/通知/时间也可能被当成消息，必须核对。
- 用绿底辅助识别「我」，左侧辅助识别「对方」；歧义标记为「待确认」。深色主题、群聊、图片、引用、多行气泡可能误判或漏识别。不自动合并聊天历史。
- 仅依据截图快照提供建议。不会跟踪当前微信联系人或新消息，建议不自动更新。
- MinerU 是异步文档 OCR，可能排队；轮询最多两分钟，单个网络请求另有超时。网络调用使用直接 HTTPS，不读取代理环境变量。
- 仅合成数据通过不代表真实微信适配已经完成；多屏缩放与真实聊天仍需试用反馈。

## 验证

```powershell
python -m unittest discover -s desktop/tests -v
python -m desktop.app --demo
# 以下明确调用真实 API，但只发送程序生成的模拟聊天：
python -m desktop.smoke --env-file "本机已有的.env路径"
```
