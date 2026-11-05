@echo off
title Servidor MCP PAT
rem PAT 135: usa el entorno que crea "07 Instaladores y entorno\Instalar_entorno_PAT.ps1" (%LOCALAPPDATA%\PAT_simulador\venv)
set "VENV=%LOCALAPPDATA%\PAT_simulador\venv"
if not exist "%VENV%\Scripts\python.exe" (
  echo Falta instalar el entorno. Ejecutando la instalacion...
  call "%~dp0..\07 Instaladores y entorno\Instalar entorno PAT.bat"
)
"%VENV%\Scripts\python.exe" -c "import mcp" 2>nul
if errorlevel 1 (
  echo Instalando el paquete mcp en el entorno...
  "%VENV%\Scripts\python.exe" -m pip install -r "%~dp0requirements.txt"
)
cd /d "%~dp0"
echo Servidor MCP PAT por stdio. Normalmente lo lanza Claude Desktop o Claude Code; aqui se puede probar con el inspector de MCP.
"%VENV%\Scripts\python.exe" servidor_mcp_pat.py
pause
