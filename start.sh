#!/data/data/com.termux/files/usr/bin/bash
set -e
cd "$(dirname "$0")"
source venv/bin/activate
python bot.py
