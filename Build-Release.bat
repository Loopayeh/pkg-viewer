@echo off
rem PKG Viewer release builder - run from this folder.
rem Build env needs: pip install pyinstaller pillow cryptography mkpfs tkinterdnd2
rem Bundles assets (window icon) + sets the exe icon. Without these
rem the window falls back to the Tk feather and a white titlebar.
rem
rem Optional Authenticode signing - needed to avoid Smart App Control blocks
rem and the SmartScreen "Unknown publisher" prompt. Either:
rem   set SIGN_PFX=C:\path\cert.pfx
rem   set SIGN_PFX_PASS=yourpassword
rem or (Azure Trusted Signing):
rem   set SIGN_DLIB=C:\path\Azure.CodeSigning.Dlib.dll
rem   set SIGN_METADATA=C:\path\metadata.json
rem Without either variable the build stays unsigned, as before.
rem The Setup exe needs its own signature too - see installer.iss.
cd /d "%~dp0"
python -m PyInstaller --noconfirm --clean --onefile --windowed --name PKGViewer --icon assets\logo.ico --add-data "assets;assets" --add-data "assets_about.png;." --add-data "orbis_full.py;." --collect-submodules PIL --collect-all tkinterdnd2 pkgviewer.py
echo.
echo Built: dist\PKGViewer.exe
call :sign_exe dist\PKGViewer.exe
echo.
pause
goto :eof

:sign_exe
if not exist "%~1" goto :eof
if defined SIGN_PFX (
    echo Signing %~1 with %SIGN_PFX% ...
    signtool sign /fd sha256 /td sha256 /tr http://timestamp.digicert.com /f "%SIGN_PFX%" /p "%SIGN_PFX_PASS%" "%~1"
    if errorlevel 1 echo WARNING: signing failed - this exe is unsigned and Smart App Control will block it.
    goto :eof
)
if defined SIGN_DLIB (
    echo Signing %~1 with Azure Trusted Signing ...
    signtool sign /fd sha256 /td sha256 /tr http://timestamp.acs.microsoft.com /dlib "%SIGN_DLIB%" /dmdf "%SIGN_METADATA%" "%~1"
    if errorlevel 1 echo WARNING: signing failed - this exe is unsigned and Smart App Control will block it.
    goto :eof
)
echo Unsigned build - set SIGN_PFX (or SIGN_DLIB) to sign.
goto :eof
