@echo off
if "%1"=="min" goto :run
start "" /min cmd /c "%~dpnx0" min
goto :eof

:run
start /min python floating_ui.py
python main.py