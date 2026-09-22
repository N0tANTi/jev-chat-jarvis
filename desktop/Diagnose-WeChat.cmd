@echo off
cd /d "%~dp0.."
echo This checks Weixin accessibility structure only. No chat text or network access.
echo Keep a Weixin chat window open. The check takes up to 25 seconds.
if not exist "desktop\.venv\Scripts\python.exe" (
  echo Missing diagnostic environment. See docs/runbooks/wxauto-diagnostics.md.
  pause
  exit /b 1
)
"desktop\.venv\Scripts\python.exe" -m desktop.accessibility_probe
echo Summary: _reports\wechat-msaa-summary.json
pause
