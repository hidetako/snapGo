@echo off
rem Register SnipNote in Windows Startup (runs at sign-in, PrintScreen to capture) and start it now
cd /d %~dp0
powershell -NoProfile -ExecutionPolicy Bypass -Command "$pw=(Get-Command pythonw -ErrorAction SilentlyContinue).Source; if(-not $pw){Write-Host 'pythonw.exe not found in PATH'; exit 1}; $lnk=[Environment]::GetFolderPath('Startup')+'\SnipNote.lnk'; $s=(New-Object -ComObject WScript.Shell).CreateShortcut($lnk); $s.TargetPath=$pw; $s.Arguments='\"%~dp0snipnote.py\" --tray'; $s.WorkingDirectory='%~dp0'; $s.Description='SnipNote screen capture'; $s.Save(); Write-Host ('Registered: '+$lnk)"
if errorlevel 1 (pause & exit /b 1)
start "" pythonw snipnote.py --tray
echo SnipNote started. Press PrintScreen to capture.
pause
