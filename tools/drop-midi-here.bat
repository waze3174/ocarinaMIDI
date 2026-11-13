@echo off
rem Drag one or more .mid files onto this file to convert them into ocarinaMIDI songs and add them to
rem the emulator's playlist. For each file it lists the song's parts and asks which one is the melody
rem (Enter takes the likely one). Next to an emulator's exe it uses that emulator's "user\sdmc" folder;
rem anywhere else it asks for the SD card folder the first time and remembers it in sd-path.txt.
setlocal
set "HERE=%~dp0"
set "CONVERTER=%HERE%midi2oca.py"

if "%~1"=="" (
    echo Drag .mid files onto this file to convert them.
    pause
    exit /b 1
)

rem Each candidate is run, so the Windows Store's "python" stub (installed with Windows) doesn't count.
set "PY="
for %%P in ("py -3" "python" "python3") do if not defined PY call :try_python %%~P
if not defined PY (
    echo Python 3 was not found. Install it from https://www.python.org and try again.
    pause
    exit /b 1
)

set "SD="
if exist "%HERE%user\sdmc\" (
    set "SD=%HERE%user\sdmc"
    goto have_sd
)
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
:have_sd
echo Songs go to "%SD%\ocarinaMIDI\songs".

set FAILED=0
:next
if "%~1"=="" goto done
echo.
echo === %~nx1
%PY% "%CONVERTER%" "%~1" --sd "%SD%" --pick
if errorlevel 1 set FAILED=1
shift
goto next

:done
echo.
if %FAILED%==1 (echo Some files were not converted, see above.) else (echo Done. The songs are in the playlist.)
pause
exit /b %FAILED%

:try_python
%* -c "import sys; sys.exit(sys.version_info[0] != 3)" >nul 2>nul && set "PY=%*"
exit /b 0
