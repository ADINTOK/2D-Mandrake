@echo off
cd /d "%~dp0"

echo [1/3] Checking Python Environment...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo CRITICAL ERROR: Python is not found!
    echo.
    echo Please install Python 3.9+ from python.org.
    echo IMPORTANT: Check the box "Add Python to PATH" during installation.
    pause
    exit /b
)

echo [2/3] Installing Dependencies...
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo WARNING: Dependency installation had issues. Attempting to continue...
)

echo [3/3] Starting 2D Mandrake - Service Management & Compliance...
REM Use 'python -m streamlit' to avoid PATH issues with the streamlit executable
python -m streamlit run Business_Catalog.py

if %errorlevel% neq 0 (
    echo.
    echo Application exited with an error.
    pause
)
