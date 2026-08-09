@echo off
REM Lanzador de verificar.ps1 que no depende de la directiva de ejecucion.
REM Ver respaldar.cmd para la explicacion completa.
REM
REM Uso:
REM   verificar.cmd

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0verificar.ps1" %*
exit /b %ERRORLEVEL%
