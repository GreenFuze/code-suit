@echo off
setlocal

set "REPO_ROOT=%~dp0"
cd /d "%REPO_ROOT%"

if exist "%REPO_ROOT%\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%REPO_ROOT%\.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
    where "%PYTHON_EXE%" >nul 2>nul
    if errorlevel 1 (
        echo Python executable not found: %PYTHON_EXE%
        exit /b 1
    )
)

if defined PYTHONPATH (
    set "PYTHONPATH=%REPO_ROOT%src;%PYTHONPATH%"
) else (
    set "PYTHONPATH=%REPO_ROOT%src"
)

"%PYTHON_EXE%" -m suitcode.mcp.server --transport http --host 127.0.0.1 --port 8000 %*
