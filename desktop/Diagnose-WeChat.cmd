@echo off
cd /d "%~dp0.."
echo This checks Weixin accessibility structure only. No chat text or network access.
echo V2: checks native child windows, UIA Raw/Control/Content views and MSAA.
echo Keep a Weixin chat window open. The check takes up to 45 seconds.
if not exist "desktop\.venv\Scripts\python.exe" (
  echo Missing diagnostic environment. See docs/runbooks/wxauto-diagnostics.md.
  pause
  exit /b 1
)
"desktop\.venv\Scripts\python.exe" -m desktop.accessibility_probe
echo Summary: _reports\wechat-msaa-summary.json
pause
