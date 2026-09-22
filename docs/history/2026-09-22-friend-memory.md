# 2026-09-22 角色与好友记忆、wxauto 验证

用户希望省去手动流程，并提出角色、历史分析、好友标签随内容更新。

## 完成

- `desktop/memory.py`：显式本地保存、独立好友 ID、原子写入及多进程冲突拒绝；历史限量、
  模型观察来源校验、版本控制、清除、上下文预算。保存失败回滚内存状态，不覆盖已保存文件。
- `desktop/profile_ui.py`：角色与确认背景编辑、历史文件导入、模型观察及依据/旧版查看。
- `desktop/app.py` / `service.py`：选中好友的记忆参与起草和排序；可选生成后保存并更新观察；
  切换好友清空旧会话。模型不会自动获取其他好友聊天。
- `desktop/wxauto-requirements.txt` / `wxauto_probe.py`：可复现依赖与不读取消息的诊断。
- `desktop/smoke_memory.py`：只用合成历史验证两轮标签更新和带背景生成。

## 验证

- 本地 36 项测试通过；合成线上：initial_tags=2、updated_tags=3、确认事实保留、
  previous_versions=1、candidates=3、jev_ranked=true。
- wxautox4 41.1.1.post1、wxauto-mcp 1.0.2 在独立环境安装成功。MCP SDK 2.2.0 下
  `Server.list_tools` 缺失；固定 1.30.0 后 CLI help 成功。
- 授权检查 `active: false`。没有购买/激活/降级，也未读取聊天、注入进程或注册发送工具。

## 未完成

实际微信 4.1.15.10 的正文读取、实时监听和新界面视觉验收没有完成。
好友记忆尚未做真实数据质量对照，不宣称量化改善。历史缺少原始消息 ID，文本重叠去重仍有歧义。

使用、数据去向、保留上限和清除方法见 [桌面手册](../../desktop/README.md)。
