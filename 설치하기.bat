@echo off
chcp 65001 >nul
cd /d "%~dp0"
python -I -X utf8 "%~dp0설치.py" %*
pause
