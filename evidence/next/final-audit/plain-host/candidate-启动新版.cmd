@echo off
chcp 65001 >nul
cd /d "%~dp0"
"D:\EXE\python\python.exe" "%~dp0launch.py"
if errorlevel 1 pause
