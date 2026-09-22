@echo off
setlocal
echo Experimental startup: --disable-gpu. This is NOT a verified fix.
echo No registry changes, process patches, or forced termination.
if not exist "%ProgramFiles%\Tencent\Weixin\Weixin.exe" (
  echo Weixin was not found in the expected installation directory.
  pause
  exit /b 1
)
tasklist /FI "IMAGENAME eq Weixin.exe" /NH | find /I "Weixin.exe" >nul
if not errorlevel 1 (
  echo Please save drafts and EXIT Weixin from its tray menu first, then run this file again.
  echo This script will not stop Weixin for you.
  pause
  exit /b 1
)
start "" /D "%ProgramFiles%\Tencent\Weixin" "%ProgramFiles%\Tencent\Weixin\Weixin.exe" --disable-gpu
echo Open a chat after login, then run Diagnose-WeChat.cmd for comparison.
echo To revert: exit Weixin and start it with your usual shortcut.
pause
