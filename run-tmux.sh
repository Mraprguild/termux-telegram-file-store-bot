#!/data/data/com.termux/files/usr/bin/bash
set -e
cd "$(dirname "$0")"
tmux new-session -d -s tgstore "cd '$PWD' && source venv/bin/activate && python bot.py"
echo "✅ Bot started in tmux session: tgstore"
echo "Open session: tmux attach -t tgstore"
echo "Detach: CTRL+B then D"
