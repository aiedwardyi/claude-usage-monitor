@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "BASH_EXE="
set "LOCAL_GIT=%LocalAppData%\Programs\Git"

if exist "%ProgramFiles%\Git\bin\bash.exe" set "BASH_EXE=%ProgramFiles%\Git\bin\bash.exe"
if not defined BASH_EXE if exist "%ProgramFiles%\Git\usr\bin\bash.exe" set "BASH_EXE=%ProgramFiles%\Git\usr\bin\bash.exe"
if not defined BASH_EXE if exist "%ProgramFiles(x86)%\Git\bin\bash.exe" set "BASH_EXE=%ProgramFiles(x86)%\Git\bin\bash.exe"
if not defined BASH_EXE if exist "%LOCAL_GIT%\bin\bash.exe" set "BASH_EXE=%LOCAL_GIT%\bin\bash.exe"
if not defined BASH_EXE if exist "%LOCAL_GIT%\usr\bin\bash.exe" set "BASH_EXE=%LOCAL_GIT%\usr\bin\bash.exe"
if not defined BASH_EXE call :find_bash_on_path

if not defined BASH_EXE (
  echo Claude
  exit /b 0
)

"%BASH_EXE%" "%SCRIPT_DIR%statusline.sh"
exit /b 0

:find_bash_on_path
for /f "delims=" %%I in ('where bash.exe 2^>nul') do (
  set "BASH_EXE=%%~fI"
  goto :eof
)
for /f "delims=" %%I in ('where bash 2^>nul') do (
  set "BASH_EXE=%%~fI"
  goto :eof
)
goto :eof
