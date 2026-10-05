@echo off
if not exist .venv\Scripts\python.exe (
  echo Creating virtual environment...
  py -m venv .venv
)
call .venv\Scripts\activate
python -m pip install -r requirements.txt
if not exist .env copy .env.example .env
python bot.py
pause
