@echo off
title Auto Live Recorder Web Dashboard
cd /d "%~dp0"
echo Memulai Web Dashboard di http://localhost:5000 ...
start http://localhost:5000
python app.py
pause

