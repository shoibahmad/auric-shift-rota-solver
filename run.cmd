@echo off
REM Entrypoint:  run <items.json> --budget <1x^|3x^|10x> --out <answers.json>
cd /d "%~dp0"
python -m rota.main %*
