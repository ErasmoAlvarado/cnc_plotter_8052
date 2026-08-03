@echo off
REM Levanta el backend (FastAPI, puerto 8000) y el frontend (Vite, puerto 5173)
REM cada uno en su propia ventana. Cerra cada ventana para detener ese proceso.

start "CNC API (8000)" cmd /k "cd /d %~dp0 && python python\cnc_api.py"
start "CNC Frontend (5173)" cmd /k "cd /d %~dp0frontend && npm run dev"
