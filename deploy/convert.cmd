@echo off
setlocal
cd /d "%~dp0"
if "%~1"=="" (
  echo Usage: convert.cmd input\document.pdf [additional marker options]
  exit /b 2
)
for %%F in ("%~1") do set "INPUT_NAME=%%~nxF"
set "EXTRA_ARGS="
shift
:loop
if "%~1"=="" goto run
set "EXTRA_ARGS=%EXTRA_ARGS% %1"
shift
goto loop
:run
docker compose -f docker-compose.yml --profile cli run --rm marker "/inputs/%INPUT_NAME%" --output_dir /outputs %EXTRA_ARGS%
endlocal



