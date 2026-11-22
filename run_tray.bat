@echo off
rem SnapGo: stay in system tray, PrintScreen to capture
cd /d %~dp0
start "" pythonw snapgo.py --tray
