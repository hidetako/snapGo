@echo off
rem SnipNote: stay in system tray, PrintScreen to capture
cd /d %~dp0
start "" pythonw snipnote.py --tray
