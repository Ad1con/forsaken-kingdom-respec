@echo off
rem Builds dist\FKRespec.exe. Needs: pip install pyinstaller
python -m PyInstaller --noconfirm --onefile --windowed --add-data "fkrespec\tooltips_data.json;fkrespec" --name FKRespec fkrespec.py
del fkrespec.spec
