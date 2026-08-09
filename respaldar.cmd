@echo off
REM Lanzador de respaldar.ps1 que no depende de la directiva de ejecucion.
REM
REM Windows bloquea por defecto los .ps1 sin firmar. Los .cmd no pasan por esa
REM comprobacion, asi que este fichero invoca PowerShell con la directiva
REM saltada solo para ese proceso: no cambia ningun ajuste del sistema.
REM
REM Aviso: -ExecutionPolicy Bypass tiene prioridad sobre la politica de la
REM maquina y la del usuario, pero NO sobre una impuesta por directiva de
REM grupo. Si en un equipo gestionado esto tampoco funciona, comprobar con
REM   Get-ExecutionPolicy -List
REM si MachinePolicy o UserPolicy tienen algo distinto de Undefined.
REM
REM Uso:
REM   respaldar.cmd
REM   respaldar.cmd -Destino D:\copias -Conservar 30
REM   respaldar.cmd -SinVerificar

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0respaldar.ps1" %*
exit /b %ERRORLEVEL%
