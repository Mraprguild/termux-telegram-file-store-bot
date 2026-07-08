#!/usr/bin/env python3
"""
Mraprguild Termux Telegram File Store Bot - Large File MTProto Version

This version uses Telethon/MTProto instead of the normal HTTP Bot API getFile
endpoint, so large Telegram media downloads do not hit the normal 20 MB getFile
limit.

Required environment variables:
  API_ID      = Telegram API ID from https://my.telegram.org/apps
  API_HASH    = Telegram API hash from https://my.telegram.org/apps
  BOT_TOKEN   = Bot token from @BotFather
"""

import asyncio
import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Optional, Tuple

from telethon import TelegramClient, events
from telethon.tl.types import DocumentAttributeFilename

APP_NAME = "Mraprguild File Store Bot"
SESSION_NAME = "mraprguild_file_store_bot"

API_ID_RAW = os.getenv("API_ID", "").strip()
API_HASH = os.getenv("API_HASH", "").strip()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

ROOT_DIR = Path.home() / "telegram-file-store-bot"
DB_PATH = ROOT_DIR / "files.db"

TERMUX_DOWNLOADS = Path.home() / "storage" / "downloads"
if TERMUX_DOWNLOADS.exists():
    BASE_DIR = TERMUX_DOWNLOADS / "TGStore"
else:
    BASE_DIR = ROOT_DIR / "TGStore"

ROOT_DIR.mkdir(parents=True, exist_ok=True)
BASE_DIR.mkdir(parents=True, exist_ok=True)


def load_dotenv() -> None:
    """Small .env loader to avoid extra dependencies."""
    env_file = ROOT_DIR / ".env"
    local_env_file = Path.cwd() / ".env"
    for file in (env_file, local_env_file):
        if not file.exists():
            continue
        for line in file.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def refresh_env() -> Tuple[int, str, str]:
    load_dotenv()
    api_id_raw = os.getenv("API_ID", "").strip()
    api_hash = os.getenv("API_HASH", "").strip()
    bot_token = os.getenv("BOT_TOKEN", "").strip()

    missing = []
    if not api_id_raw:
        missing.append("API_ID")
    if not api_hash:
        missing.append("API_HASH")
    if not bot_token:
        missing.append("BOT_TOKEN")
    if missing:
        raise RuntimeError(
            "Missing required values: " + ", ".join(missing) + "\n\n"
            "Set them like this:\n"
            "export API_ID=123456\n"
            "export API_HASH=your_api_hash\n"
            "export BOT_TOKEN=your_bot_token\n"
        )

    try:
        api_id = int(api_id_raw)
    except ValueError as exc:
        raise RuntimeError("API_ID must be a number, example: export API_ID=123456") from exc

    return api_id, api_hash, bot_token


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            chat_id INTEGER,
            message_id INTEGER,
            file_name TEXT,
            file_type TEXT,
            file_size INTEGER,
            mime_type TEXT,
            saved_path TEXT,
            created_at INTEGER
        )
        """
    )
    conn.commit()
    return conn


def safe_name(name: Optional[str]) -> str:
    if not name:
        name = f"telegram_file_{int(time.time())}"
    name = name.replace("\x00", "")
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:180] or f"telegram_file_{int(time.time())}"


def human_size(size: Optional[int]) -> str:
    if not size:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{size} B"


def media_info(message) -> Tuple[str, str, int, Optional[str]]:
    """Return name, type, size, mime."""
    file_obj = getattr(message, "file", None)
    name = None
    ext = None
    size = 0
    mime = None

    if file_obj:
        name = getattr(file_obj, "name", None)
        ext = getattr(file_obj, "ext", None)
        size = int(getattr(file_obj, "size", 0) or 0)
        mime = getattr(file_obj, "mime_type", None)

    if not name and getattr(message, "document", None):
        for attr in getattr(message.document, "attributes", []) or []:
            if isinstance(attr, DocumentAttributeFilename):
                name = attr.file_name
                break

    if getattr(message, "photo", None):
        ftype = "photo"
        name = name or f"photo_{int(time.time())}.jpg"
    elif getattr(message, "video", None):
        ftype = "video"
        name = name or f"video_{int(time.time())}{ext or '.mp4'}"
    elif getattr(message, "audio", None):
        ftype = "audio"
        name = name or f"audio_{int(time.time())}{ext or '.mp3'}"
    elif getattr(message, "voice", None):
        ftype = "voice"
        name = name or f"voice_{int(time.time())}{ext or '.ogg'}"
    elif getattr(message, "gif", None):
        ftype = "animation"
        name = name or f"animation_{int(time.time())}{ext or '.mp4'}"
    elif getattr(message, "sticker", None):
        ftype = "sticker"
        name = name or f"sticker_{int(time.time())}{ext or '.webp'}"
    elif getattr(message, "document", None):
        ftype = "document"
        name = name or f"document_{int(time.time())}{ext or ''}"
    else:
        ftype = "media"
        name = name or f"telegram_media_{int(time.time())}{ext or ''}"

    return safe_name(name), ftype, size, mime


async def progress_message(event, action: str):
    last_update = 0
    status_msg = await event.respond(f"⏳ {action}: 0%")

    async def callback(current: int, total: int):
        nonlocal last_update
        now = time.time()
        if now - last_update < 3 and current != total:
            return
        last_update = now
        percent = (current / total * 100) if total else 0
        try:
            await status_msg.edit(
                f"⏳ {action}: {percent:.1f}%\n"
                f"📦 {human_size(current)} / {human_size(total)}"
            )
        except Exception:
            pass

    return status_msg, callback


async def cmd_start(event):
    await event.respond(
        "✅ **Mraprguild File Store Bot Running**\n\n"
        "Send any document, video, photo, audio, sticker, or animation.\n"
        "This build uses **MTProto large-file mode** for Termux.\n\n"
        "**Commands**\n"
        "/list - Show stored files\n"
        "/get ID - Send saved file back\n"
        "/delete ID - Delete saved file\n"
        "/stats - Storage details\n"
        "/help - Help"
    )


async def cmd_help(event):
    await event.respond(
        "📁 **File Store Help**\n\n"
        "1. Send a file to this bot.\n"
        "2. Bot saves it in Termux storage.\n"
        "3. Use `/list` to see saved files.\n"
        "4. Use `/get 1` to send a stored file back.\n"
        "5. Use `/delete 1` to remove a file.\n\n"
        "📍 Storage folder:\n"
        f"`{BASE_DIR}`\n\n"
        "🔐 Required values:\n"
        "`API_ID`, `API_HASH`, `BOT_TOKEN`"
    )


async def cmd_list(event):
    conn = get_db()
    rows = conn.execute(
        """
        SELECT id, file_name, file_type, file_size, created_at
        FROM files
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 30
        """,
        (event.sender_id,),
    ).fetchall()
    conn.close()

    if not rows:
        await event.respond("📭 No files stored yet.")
        return

    text = "📁 **Your Stored Files**\n\n"
    for fid, name, ftype, size, created in rows:
        text += f"🆔 `{fid}` | {ftype} | {human_size(size)}\n📄 `{name}`\n\n"
    text += "Use `/get ID` to download."
    await event.respond(text)


async def cmd_get(event):
    parts = event.raw_text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await event.respond("Usage: `/get ID`")
        return

    fid = int(parts[1].strip())
    conn = get_db()
    row = conn.execute(
        "SELECT file_name, saved_path, file_size FROM files WHERE id = ? AND user_id = ?",
        (fid, event.sender_id),
    ).fetchone()
    conn.close()

    if not row:
        await event.respond("❌ File not found.")
        return

    file_name, saved_path, file_size = row
    path = Path(saved_path)
    if not path.exists():
        await event.respond("❌ File missing from Termux storage.")
        return

    status_msg, cb = await progress_message(event, "Uploading")
    try:
        await event.client.send_file(
            event.chat_id,
            file=str(path),
            caption=f"✅ File ID: `{fid}`\n📄 `{file_name}`\n📦 {human_size(file_size)}",
            force_document=True,
            progress_callback=cb,
        )
        await status_msg.edit("✅ Upload complete.")
    except Exception as exc:
        await status_msg.edit(f"❌ Upload failed: `{exc}`")


async def cmd_delete(event):
    parts = event.raw_text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip().isdigit():
        await event.respond("Usage: `/delete ID`")
        return

    fid = int(parts[1].strip())
    conn = get_db()
    row = conn.execute(
        "SELECT saved_path FROM files WHERE id = ? AND user_id = ?",
        (fid, event.sender_id),
    ).fetchone()

    if not row:
        conn.close()
        await event.respond("❌ File not found.")
        return

    path = Path(row[0])
    if path.exists():
        try:
            path.unlink()
        except Exception:
            pass

    conn.execute("DELETE FROM files WHERE id = ? AND user_id = ?", (fid, event.sender_id))
    conn.commit()
    conn.close()
    await event.respond(f"🗑 Deleted file ID: `{fid}`")


async def cmd_stats(event):
    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(file_size), 0) FROM files WHERE user_id = ?",
        (event.sender_id,),
    ).fetchone()
    conn.close()

    count, total = row if row else (0, 0)
    await event.respond(
        "📊 **Storage Stats**\n\n"
        f"📁 Files: `{count}`\n"
        f"📦 Total indexed size: `{human_size(total)}`\n"
        f"📍 Folder: `{BASE_DIR}`\n"
        f"🗃 Database: `{DB_PATH}`"
    )


async def save_media(event):
    message = event.message
    if not message or not message.media:
        return

    file_name, ftype, size, mime = media_info(message)
    timestamp = int(time.time())
    final_name = f"{timestamp}_{file_name}"
    save_path = BASE_DIR / final_name

    status_msg, cb = await progress_message(event, "Downloading")
    try:
        downloaded = await message.download_media(file=str(save_path), progress_callback=cb)
        if not downloaded:
            await status_msg.edit("❌ Download failed: Telegram returned no file path.")
            return

        real_path = Path(downloaded)
        real_size = real_path.stat().st_size if real_path.exists() else size

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO files
            (user_id, chat_id, message_id, file_name, file_type, file_size, mime_type, saved_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.sender_id,
                event.chat_id,
                message.id,
                file_name,
                ftype,
                real_size,
                mime,
                str(real_path),
                timestamp,
            ),
        )
        conn.commit()
        file_db_id = cur.lastrowid
        conn.close()

        await status_msg.edit(
            "✅ **File stored successfully**\n\n"
            f"🆔 ID: `{file_db_id}`\n"
            f"📄 Name: `{file_name}`\n"
            f"🧩 Type: `{ftype}`\n"
            f"📦 Size: `{human_size(real_size)}`\n"
            f"📍 Path: `{real_path}`\n\n"
            f"Use `/get {file_db_id}`"
        )
    except Exception as exc:
        await status_msg.edit(
            "❌ **File store failed**\n\n"
            f"Error: `{exc}`\n\n"
            "Fix checks:\n"
            "1. Confirm API_ID and API_HASH are correct.\n"
            "2. Keep Termux screen active during big downloads.\n"
            "3. Make sure phone storage has enough free space."
        )


async def main():
    api_id, api_hash, bot_token = refresh_env()
    client = TelegramClient(str(ROOT_DIR / SESSION_NAME), api_id, api_hash)

    @client.on(events.NewMessage(pattern=r"^/start$"))
    async def start_handler(event):
        await cmd_start(event)

    @client.on(events.NewMessage(pattern=r"^/help$"))
    async def help_handler(event):
        await cmd_help(event)

    @client.on(events.NewMessage(pattern=r"^/list$"))
    async def list_handler(event):
        await cmd_list(event)

    @client.on(events.NewMessage(pattern=r"^/get(\s+\d+)?$"))
    async def get_handler(event):
        await cmd_get(event)

    @client.on(events.NewMessage(pattern=r"^/delete(\s+\d+)?$"))
    async def delete_handler(event):
        await cmd_delete(event)

    @client.on(events.NewMessage(pattern=r"^/stats$"))
    async def stats_handler(event):
        await cmd_stats(event)

    @client.on(events.NewMessage(incoming=True))
    async def media_handler(event):
        if event.raw_text and event.raw_text.startswith("/"):
            return
        if event.message and event.message.media:
            await save_media(event)

    print(f"{APP_NAME} starting...")
    print(f"Storage: {BASE_DIR}")
    print("Large-file mode: Telethon / MTProto")
    await client.start(bot_token=bot_token)
    print("Bot started successfully.")
    await client.run_until_disconnected()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped by user.")
    except Exception as exc:
        print(f"Startup failed: {exc}")
