@echo off
setlocal DisableDelayedExpansion

rem Change only this line when Blender is installed elsewhere.
set "BLENDER_EXE=C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"

set "ROOT_DIR=%~dp0"
set "SOURCE_DIR=%ROOT_DIR%panda_lip_blender"
set "MANIFEST=%SOURCE_DIR%\blender_manifest.toml"
set "DIST_DIR=%ROOT_DIR%dist"
set "PACKAGE_ID="
set "PACKAGE_VERSION="
set "EXIT_CODE=0"

if not exist "%BLENDER_EXE%" (
    set "FAILURE_REASON=Blender executable was not found. Edit BLENDER_EXE in build.bat."
    goto :failed
)

if not exist "%MANIFEST%" (
    set "FAILURE_REASON=Extension manifest was not found: %MANIFEST%"
    goto :failed
)

for /f "tokens=3" %%I in ('findstr.exe /B /C:"id = " "%MANIFEST%"') do set "PACKAGE_ID=%%~I"
for /f "tokens=3" %%I in ('findstr.exe /B /C:"version = " "%MANIFEST%"') do set "PACKAGE_VERSION=%%~I"

if not defined PACKAGE_ID (
    set "FAILURE_REASON=Could not read the extension id from blender_manifest.toml."
    goto :failed
)

if not defined PACKAGE_VERSION (
    set "FAILURE_REASON=Could not read the extension version from blender_manifest.toml."
    goto :failed
)

set "OUTPUT_ZIP=%DIST_DIR%\%PACKAGE_ID%-%PACKAGE_VERSION%.zip"
set "TEMP_ZIP=%DIST_DIR%\%PACKAGE_ID%-%PACKAGE_VERSION%.building.zip"

if not exist "%DIST_DIR%" (
    mkdir "%DIST_DIR%"
    if errorlevel 1 (
        set "FAILURE_REASON=Could not create the dist directory: %DIST_DIR%"
        goto :failed
    )
)

rem Build to a temporary ZIP so an existing successful build remains intact
rem if Blender fails. No other files in dist are removed.
if exist "%TEMP_ZIP%" del /Q "%TEMP_ZIP%"
if exist "%TEMP_ZIP%" (
    set "FAILURE_REASON=Could not remove the previous temporary build: %TEMP_ZIP%"
    goto :failed
)

pushd "%ROOT_DIR%"
if errorlevel 1 (
    set "FAILURE_REASON=Could not enter the repository directory: %ROOT_DIR%"
    goto :failed
)

"%BLENDER_EXE%" --background --factory-startup --command extension build --source-dir "%SOURCE_DIR%" --output-filepath "%TEMP_ZIP%"
set "BUILD_EXIT_CODE=%ERRORLEVEL%"
popd

if not "%BUILD_EXIT_CODE%"=="0" (
    set "FAILURE_REASON=Blender Extension build returned error code %BUILD_EXIT_CODE%."
    goto :failed
)

if not exist "%TEMP_ZIP%" (
    set "FAILURE_REASON=Blender reported success but did not create the expected ZIP."
    goto :failed
)

move /Y "%TEMP_ZIP%" "%OUTPUT_ZIP%" >nul
if errorlevel 1 (
    set "FAILURE_REASON=Could not update the output ZIP: %OUTPUT_ZIP%"
    goto :failed
)

echo.
echo ========================================
echo Panda Lip Blender build completed.
echo ========================================
echo.
echo Output:
echo   "%OUTPUT_ZIP%"
goto :finish

:failed
set "EXIT_CODE=1"
if defined TEMP_ZIP if exist "%TEMP_ZIP%" del /Q "%TEMP_ZIP%"
echo.
echo ========================================
echo BUILD FAILED
echo ========================================
echo.
echo Reason:
echo   "%FAILURE_REASON%"

:finish
echo.
if /I "%~1"=="--no-pause" goto :exit
pause

:exit
exit /B %EXIT_CODE%
