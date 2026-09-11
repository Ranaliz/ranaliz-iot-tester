@echo off
REM Build Ranaliz iOT Tester for Windows (.exe)
REM Run on a Windows PC (PyInstaller cannot cross-compile from macOS).

setlocal enabledelayedexpansion

cd /d "%~dp0"

REM Prefer project venv; create it if missing
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo .venv not found — creating...
  where py >nul 2>&1
  if not errorlevel 1 (
    py -3 -m venv .venv
  ) else (
    where python >nul 2>&1
    if errorlevel 1 (
      echo Python 3 not found. Install Python 3, then re-run this script.
      pause
      exit /b 1
    )
    python -m venv .venv
  )
  if not exist "%~dp0.venv\Scripts\python.exe" (
    echo Failed to create .venv
    pause
    exit /b 1
  )
)

set "PYTHON=%~dp0.venv\Scripts\python.exe"
echo Building Windows executable with: %PYTHON%

REM Ensure build + runtime dependencies (PyInstaller, Pillow, app deps)
"%PYTHON%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 goto :install_deps
"%PYTHON%" -c "import PIL" >nul 2>&1
if errorlevel 1 goto :install_deps
goto :deps_ok

:install_deps
echo Installing requirements + PyInstaller + Pillow into .venv...
"%PYTHON%" -m pip install -U pip
if errorlevel 1 (
  echo pip upgrade failed.
  pause
  exit /b 1
)
"%PYTHON%" -m pip install -r requirements.txt pyinstaller pyinstaller-hooks-contrib pillow
if errorlevel 1 (
  echo Dependency install failed.
  pause
  exit /b 1
)

:deps_ok
"%PYTHON%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
  echo PyInstaller still missing after install.
  pause
  exit /b 1
)

REM Clean previous builds
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "Ranaliz iOT Tester.spec" del /f /q "Ranaliz iOT Tester.spec"

REM Generate AppIcon.ico (falls back to logo512.png if Pillow missing)
"%PYTHON%" tools\make_icon.py
if errorlevel 1 (
  echo Icon generation failed.
  pause
  exit /b 1
)

REM Emit PyInstaller spec (SPECPATH + hiddenimports + upx=False)
"%PYTHON%" tools\emit_windows_spec.py
if errorlevel 1 (
  echo Spec generation failed.
  pause
  exit /b 1
)

REM Build one-file windowed EXE
"%PYTHON%" -m PyInstaller "Ranaliz iOT Tester.spec" --clean
if errorlevel 1 (
  echo.
  echo Build failed!
  echo Try manually:
  echo   .venv\Scripts\pip install -r requirements.txt pyinstaller pyinstaller-hooks-contrib pillow
  pause
  exit /b 1
)

echo.
echo Build complete!
echo    Executable: dist\Ranaliz iOT Tester.exe
echo.
echo Run:
echo    dist\Ranaliz iOT Tester.exe
echo.
pause
endlocal
