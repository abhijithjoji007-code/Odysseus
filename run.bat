@echo off
setlocal
cd /d "%~dp0"

echo ==========================================
echo   ODYSSEUS AI ASSISTANT v6
echo ==========================================

where py >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON_CMD=py"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set "PYTHON_CMD=python"
    ) else (
        goto error
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PYTHON_CMD% -m venv .venv || goto error
)

call ".venv\Scripts\activate.bat" || goto error

echo Updating pip...
python -m pip install --upgrade pip

echo Installing project requirements...
python -m pip install -r requirements.txt || goto error

echo.
echo Starting Odysseus at http://127.0.0.1:8000
start "" http://127.0.0.1:8000
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
goto end

:error
echo.
echo Setup failed. Confirm Python is installed and available in PATH.
pause
exit /b 1

:end
endlocal
