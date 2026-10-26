@echo off
setlocal
cd /d "%~dp0"
echo Structure Lab - local educational structural analysis
if exist ".venv\Scripts\python.exe" goto dependencies
python -c "import sys; assert sys.version_info >= (3,10)" >nul 2>&1
if not errorlevel 1 (
    python -m venv .venv
    goto check_environment
)
py -3 -c "import sys; assert sys.version_info >= (3,10)" >nul 2>&1
if not errorlevel 1 (
    py -3 -m venv .venv
    goto check_environment
)
for %%P in ("%USERPROFILE%\anaconda3\python.exe" "%LOCALAPPDATA%\anaconda3\python.exe" "%USERPROFILE%\miniconda3\python.exe" "%LOCALAPPDATA%\miniconda3\python.exe" "C:\ProgramData\anaconda3\python.exe") do (
    if exist "%%~P" (
        "%%~P" -m venv .venv
        goto check_environment
    )
)
echo Python was not found. Open Anaconda Prompt, go to this folder,
echo and type: python -m venv .venv
echo Then double-click START_WINDOWS.bat again.
pause
exit /b 1
:check_environment
if not exist ".venv\Scripts\python.exe" (
    echo Environment creation failed. See the messages above.
    pause
    exit /b 1
)
:dependencies
".venv\Scripts\python.exe" -c "import numpy, pandas, plotly, streamlit; from importlib.metadata import version; from packaging.version import Version; assert Version(version('streamlit')) >= Version('1.51')" >nul 2>&1
if errorlevel 1 (
    echo Installing packages. Keep this window open and stay connected to Wi-Fi.
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt --timeout 120 --retries 10
    if errorlevel 1 (
        echo Installation did not complete. Check Wi-Fi, then run this file again.
        pause
        exit /b 1
    )
)
echo Starting the app. Keep this window open; press Ctrl+C to stop.
".venv\Scripts\python.exe" -m streamlit run app.py
pause
