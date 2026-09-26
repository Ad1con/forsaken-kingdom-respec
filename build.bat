@echo off
rem Builds both downloads and prints their SHA-256 for the release notes.
rem
rem   dist\FKRespec.exe          one file, the usual download
rem   dist\FKRespec-folder.zip   the same program as a folder
rem
rem The folder build is the fallback for anyone whose antivirus objects to the
rem single file: a one-file build unpacks itself into temp at startup, which is
rem what heuristics react to. Zipped, the two are about the same size.
rem
rem Needs: pip install pyinstaller

setlocal
if exist dist-folder rmdir /s /q dist-folder
if exist build rmdir /s /q build

echo(
echo === one file ===
python -m PyInstaller --noconfirm --onefile --windowed ^
    --add-data "fkrespec\tooltips_data.json;fkrespec" ^
    --name FKRespec fkrespec.py || goto :fail

echo(
echo === one folder ===
rem into its own dist so the exe inside keeps the plain name
python -m PyInstaller --noconfirm --onedir --windowed ^
    --add-data "fkrespec\tooltips_data.json;fkrespec" ^
    --distpath dist-folder --name FKRespec fkrespec.py || goto :fail

echo(
echo === zipping the folder ===
powershell -NoProfile -Command ^
    "Compress-Archive -Path dist-folder\FKRespec -DestinationPath dist\FKRespec-folder.zip -Force" || goto :fail
rmdir /s /q dist-folder

del fkrespec.spec 2>nul

echo(
echo === SHA-256, for the release notes ===
certutil -hashfile dist\FKRespec.exe SHA256 | findstr /v ":"
certutil -hashfile dist\FKRespec-folder.zip SHA256 | findstr /v ":"

echo(
echo Done. Both downloads are in dist\.
exit /b 0

:fail
echo(
echo BUILD FAILED
exit /b 1
