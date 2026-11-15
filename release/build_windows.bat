@echo off
rem Build the portable MiSalud folder on Windows.
rem
rem Double-click this file, or run it from a terminal:
rem     release\build_windows.bat                      build and check dist\MiSalud
rem     release\build_windows.bat --install C:\MiSalud  also put the program there
rem
rem The first run creates a private Python environment in .venv-build and
rem downloads the libraries, so it needs internet. The app itself never does.

setlocal
cd /d "%~dp0.."

set "PYTHON=py -3"
%PYTHON% --version >nul 2>nul
if errorlevel 1 set "PYTHON=python"
%PYTHON% -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>nul
if errorlevel 1 (
    echo.
    echo No se encontro Python 3.12 o mas nuevo.
    echo Instalalo desde https://www.python.org/downloads/ y volve a ejecutar este archivo.
    goto :failed
)

if not exist ".venv-build\Scripts\python.exe" (
    echo Creando el entorno de Python en .venv-build ...
    %PYTHON% -m venv .venv-build
    if errorlevel 1 goto :failed
)

echo Instalando las librerias ...
".venv-build\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv-build\Scripts\python.exe" -m pip install --quiet ".[ui,build]"
if errorlevel 1 goto :failed

echo Armando la carpeta de MiSalud. Tarda unos minutos ...
".venv-build\Scripts\python.exe" release\build.py %*
if errorlevel 1 goto :failed

echo.
echo Listo. La carpeta de la app esta en dist\MiSalud
pause
exit /b 0

:failed
echo.
echo No se pudo completar. El motivo esta en las lineas de arriba.
pause
exit /b 1
