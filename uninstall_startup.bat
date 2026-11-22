@echo off
rem Remove SnapGo from Windows Startup and stop the running instance
powershell -NoProfile -Command "$lnk=[Environment]::GetFolderPath('Startup')+'\SnapGo.lnk'; if(Test-Path $lnk){Remove-Item $lnk; Write-Host 'Removed startup shortcut'}else{Write-Host 'No startup shortcut found'}"
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | Where-Object {$_.CommandLine -like '*snapgo.py*'} | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host 'Stopped SnapGo' }"
pause
