@echo off
rem Opens Nova Desk, the main terminal. Extra arguments pass through, e.g. nova --port 8502
"%~dp0venv\Scripts\python.exe" "%~dp0web_main.py" %*
