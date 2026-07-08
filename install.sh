#!/data/data/com.termux/files/usr/bin/bash
set -e

echo "📦 Updating Termux packages..."
pkg update -y
pkg upgrade -y

echo "📦 Installing required packages..."
pkg install -y python git tmux

if [ ! -d "$HOME/storage" ]; then
  echo "📁 Requesting Android storage permission..."
  termux-setup-storage || true
fi

echo "🐍 Creating Python virtual environment..."
python -m venv venv
source venv/bin/activate
pip install --upgrade pip wheel
pip install -r requirements.txt

mkdir -p "$HOME/telegram-file-store-bot"
mkdir -p "$HOME/storage/downloads/TGStore" 2>/dev/null || mkdir -p "$HOME/telegram-file-store-bot/TGStore"

if [ ! -f "$HOME/telegram-file-store-bot/.env" ]; then
cat > "$HOME/telegram-file-store-bot/.env" <<'ENV'
API_ID=
API_HASH=
BOT_TOKEN=
ENV
fi

echo "✅ Install complete."
echo "Edit credentials: nano ~/telegram-file-store-bot/.env"
echo "Then run: ./start.sh"
