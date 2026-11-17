@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================
echo  Agent Integration - Build Installer
echo ============================================
echo.

REM Prefer active venv python when available
set "PY=python"
if exist "venv\Scripts\python.exe" set "PY=%~dp0venv\Scripts\python.exe"

"%PY%" -c "import sys; print(sys.executable)"
if errorlevel 1 (
  echo ERROR: Python not found.
  exit /b 1
)

echo [1/4] Installing dependencies...
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 (
  echo ERROR: pip install failed.
  exit /b 1
)

echo.
echo [2/4] Building main app: Agent_Integration...
if exist "dist\Agent_Integration" rmdir /s /q "dist\Agent_Integration"
if exist "build\Agent_Integration" rmdir /s /q "build\Agent_Integration"
if exist "dist\Setup" rmdir /s /q "dist\Setup"
if exist "build\Setup" rmdir /s /q "build\Setup"

"%PY%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --name Agent_Integration ^
  --distpath dist ^
  --workpath build ^
  --add-data "static;static" ^
  --add-data "src;src" ^
  --hidden-import uvicorn.logging ^
  --hidden-import uvicorn.loops ^
  --hidden-import uvicorn.loops.auto ^
  --hidden-import uvicorn.protocols ^
  --hidden-import uvicorn.protocols.http ^
  --hidden-import uvicorn.protocols.http.auto ^
  --hidden-import uvicorn.protocols.websockets ^
  --hidden-import uvicorn.protocols.websockets.auto ^
  --hidden-import uvicorn.lifespan ^
  --hidden-import uvicorn.lifespan.on ^
  --hidden-import fastapi ^
  --hidden-import pydantic ^
  --hidden-import httpx ^
  --collect-all uvicorn ^
  --collect-all fastapi ^
  --collect-all httpx ^
  run.py

if errorlevel 1 (
  echo ERROR: Main app PyInstaller build failed.
  exit /b 1
)

if not exist "dist\Agent_Integration\Agent_Integration.exe" (
  echo ERROR: dist\Agent_Integration\Agent_Integration.exe was not created.
  exit /b 1
)

echo.
echo [3/4] Building installer wizard ^(onedir^): Setup.exe + _internal...
REM Bundle the built app into the installer payload as Agent_Integration/
"%PY%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --name Setup ^
  --distpath dist ^
  --workpath build ^
  --add-data "dist\Agent_Integration;Agent_Integration" ^
  installer\setup_ui.py

if errorlevel 1 (
  echo ERROR: Setup wizard PyInstaller build failed.
  exit /b 1
)

echo.
echo [4/4] Verifying build outputs...
if not exist "dist\Setup\Setup.exe" (
  echo ERROR: dist\Setup\Setup.exe was not created.
  exit /b 1
)
if not exist "dist\Setup\_internal" (
  echo ERROR: dist\Setup\_internal was not created.
  exit /b 1
)
if not exist "dist\Setup\_internal\Agent_Integration\Agent_Integration.exe" (
  echo ERROR: App bundle missing inside dist\Setup\_internal\Agent_Integration
  exit /b 1
)

echo.
echo Build complete.
echo   Setup root:  dist\Setup\Setup.exe
echo   Payload:     dist\Setup\_internal\Agent_Integration\
echo.
endlocal
exit /b 0
