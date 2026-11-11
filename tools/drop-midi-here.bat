@echo off
rem Drag one or more .mid files onto this file to convert them into ocarinaMIDI songs and add them
rem to the emulator's playlist. The first time, it asks for the emulator's SD card folder
rem (usually the "user\sdmc" folder next to the emulator's exe) and remembers it in sd-path.txt.
setlocal
set "HERE=%~dp0"
set "CONVERTER=%HERE%midi2oca.py"

if "%~1"=="" (
    echo Drag .mid files onto this file to convert them.
    pause
    exit /b 1
)

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY (
    echo Python 3 was not found. Install it from https://www.python.org and try again.
    pause
    exit /b 1
)

set "SD="
if exist "%HERE%sd-path.txt" set /p SD=<"%HERE%sd-path.txt"
if not defined SD (
    echo Where is the emulator's SD card folder?
    echo It is usually the "user\sdmc" folder next to the emulator's exe.
    set /p "SD=Paste the folder path and press Enter: "
)
if not defined SD (
    echo No folder given.
    pause
    exit /b 1
)
set "SD=%SD:"=%"
if not exist "%SD%\" (
    echo The folder "%SD%" doesn't exist.
    if exist "%HERE%sd-path.txt" del "%HERE%sd-path.txt"
    pause
    exit /b 1
)
> "%HERE%sd-path.txt" echo %SD%

set FAILED=0
:next
if "%~1"=="" goto done
echo.
echo === %~nx1
%PY% "%CONVERTER%" "%~1" --sd "%SD%"
if errorlevel 1 set FAILED=1
shift
goto next

:done
echo.
if %FAILED%==1 (echo Some files were not converted, see above.) else (echo Done. The songs are in the playlist.)
pause
