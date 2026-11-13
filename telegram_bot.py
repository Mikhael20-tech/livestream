"""
Telegram Bot Controller & Notifier untuk Live Stream Recorder
"""

import os
import time
import json
import logging
import threading
import urllib.request
import urllib.parse
from recorder import load_config, save_config, ACTIVE_STATUS, get_vps_health

logger = logging.getLogger("TelegramBot")


def send_telegram_msg(text: str):
    """Kirim pesan notifikasi ke chat Telegram pemilik bot."""
    cfg = load_config()
    tg = cfg.get("telegram", {})
    if not tg.get("enabled", False):
        return

    token = tg.get("bot_token")
    chat_id = tg.get("chat_id")
    if not token or not chat_id:
        return

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": "true"
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req, timeout=8)
    except Exception as e:
        logger.error(f"Gagal mengirim pesan Telegram: {e}")


class TelegramListener(threading.Thread):
    """Worker background yang menerima perintah interaktif dari chat Telegram."""

    def __init__(self):
        super().__init__(daemon=True)
        self.stop_event = threading.Event()
        self.last_update_id = 0

    def stop(self):
        self.stop_event.set()

    def run(self):
        logger.info("📱 Telegram Controller Bot aktif dan mendengarkan perintah...")
        time.sleep(2)
        send_telegram_msg("🤖 *Bot Perekam Live v2.0 Siap!*\nKetik /help untuk melihat daftar perintah canggih.")

        while not self.stop_event.is_set():
            cfg = load_config()
            tg = cfg.get("telegram", {})
            token = tg.get("bot_token")
            allowed_chat = str(tg.get("chat_id", ""))

            if not tg.get("enabled", False) or not token:
                time.sleep(5)
                continue

            try:
                url = f"https://api.telegram.org/bot{token}/getUpdates?offset={self.last_update_id + 1}&timeout=15"
                with urllib.request.urlopen(url, timeout=20) as resp:
                    data = json.loads(resp.read().decode("utf-8"))

                for item in data.get("result", []):
                    self.last_update_id = item["update_id"]
                    msg = item.get("message", {})
                    chat_id = str(msg.get("chat", {}).get("id", ""))
                    text = msg.get("text", "").strip()

                    # Keamanan: hanya tanggapi pemilik bot
                    if chat_id != allowed_chat:
                        continue

                    self.handle_command(text, chat_id)

            except Exception:
                time.sleep(2)

    def handle_command(self, text: str, chat_id: str):
        if not text:
            return

        cmd_parts = text.split()
        cmd = cmd_parts[0].lower()

        if cmd in ["/start", "/help", "help", "halo"]:
            reply = (
                "🤖 *Live Stream Recorder Bot v2.0*\n\n"
                "📌 *Perintah Utama:*\n"
                "➕ `/add <username>` - Tambah target TikTok\n"
                "➕ `/add <platform> <target> [kualitas]` - Tambah target (tiktok/youtube/band/twitch)\n"
                "📋 `/list` - Cek daftar akun & status pantauan\n"
                "🗑️ `/del <username>` - Hapus target dari daftar\n"
                "📊 `/status` - Cek stream yang sedang direkam\n"
                "💾 `/storage` - Pantau kapasitas SSD & RAM VPS\n"
                "📁 `/recordings` - Cek hasil rekaman lokal terbaru\n"
                "🏓 `/ping` - Cek respon & kesehatan bot\n"
                "☁️ `/drive` - Buka folder rekaman Google Drive\n\n"
                "_Pilihan kualitas: hd, origin, sd, audio_only_"
            )
            send_telegram_msg(reply)

        elif cmd in ["/storage", "/vps", "/health"]:
            h = get_vps_health()
            free_pct = 100 - h["disk_pct"]
            status_disk = "🟢 Aman" if free_pct > 20 else ("🟡 Perhatian" if free_pct > 10 else "🔴 Kritis")
            
            lines = [
                "💾 *STATUS SISTEM & VPS (72.60.79.72):*",
                f"• Kapasitas SSD: *{h['disk_used_gb']} GB* / *{h['disk_total_gb']} GB* ({h['disk_pct']}%)",
                f"• Sisa Penyimpanan: *{h['disk_free_gb']} GB* ({free_pct:.1f}%) [{status_disk}]"
            ]
            if h.get("ram_total_mb", 0) > 0:
                lines.append(f"• Pemakaian RAM: *{h['ram_used_mb']:.0f} MB* / *{h['ram_total_mb']:.0f} MB* ({h['ram_pct']}%)")
            
            rec_count = sum(1 for v in ACTIVE_STATUS.values() if v)
            lines.append(f"• Stream Aktif Direkam: *{rec_count}*")
            send_telegram_msg("\n".join(lines))

        elif cmd == "/ping":
            send_telegram_msg("🏓 *Pong!*\nBot aktif normal di VPS Jakarta.\nLayanan berjalan 24/7 otonom.")

        elif cmd == "/list":
            cfg = load_config()
            targets = cfg.get("targets", [])
            if not targets:
                send_telegram_msg("📋 Belum ada akun target yang dipantau.")
                return

            lines = ["📋 *Daftar Target Pemantauan:*"]
            for idx, t in enumerate(targets, 1):
                plat = t.get("platform", "tiktok").lower()
                user = t.get("username", "")
                clean_user = user.lower().lstrip("@")
                qual = t.get("quality", "hd").upper()
                is_live = ACTIVE_STATUS.get(f"{plat}_{clean_user}", False)
                status_str = "🔴 *SEDANG LIVE*" if is_live else ("Standby" if t.get("enabled", True) else "Nonaktif")
                lines.append(f"{idx}. [{plat.upper()}] *{user}* ({qual}) - {status_str}")
            send_telegram_msg("\n".join(lines))

        elif cmd == "/add":
            if len(cmd_parts) < 2:
                send_telegram_msg("⚠️ Format salah!\nContoh: `/add @rrenerren29` atau `/add youtube @channel` atau `/add band https://band.us/band/xxx`")
                return

            platform = "tiktok"
            quality = "hd"

            if len(cmd_parts) == 2:
                username = cmd_parts[1].strip()
            elif len(cmd_parts) >= 3:
                # Cek jika argumen pertama adalah platform atau username
                first_arg = cmd_parts[1].strip().lower()
                if first_arg in ["tiktok", "youtube", "twitch", "kick", "band"]:
                    platform = first_arg
                    username = cmd_parts[2].strip()
                    if len(cmd_parts) >= 4:
                        quality = cmd_parts[3].strip().lower()
                else:
                    username = cmd_parts[1].strip()
                    quality = cmd_parts[2].strip().lower()

            cfg = load_config()
            cfg.setdefault("targets", [])
            clean_u = username.lower().lstrip("@")

            # Cek duplikat
            for t in cfg["targets"]:
                if t.get("username", "").lower().lstrip("@") == clean_u and t.get("platform", "").lower() == platform:
                    send_telegram_msg(f"⚠️ Target *{username}* sudah ada di daftar pemantauan.")
                    return

            cfg["targets"].append({
                "platform": platform,
                "username": username,
                "quality": quality,
                "enabled": True
            })
            save_config(cfg)
            send_telegram_msg(f"✅ Berhasil menambahkan [{platform.upper()}] *{username}* (Kualitas: {quality.upper()}) ke pantauan 24/7!")

        elif cmd == "/del":
            if len(cmd_parts) < 2:
                send_telegram_msg("⚠️ Format salah!\nContoh: `/del @nama_akun`")
                return
            username = cmd_parts[1].strip()
            clean_u = username.lower().lstrip("@")

            cfg = load_config()
            targets = cfg.get("targets", [])
            new_t = [t for t in targets if t.get("username", "").lower().lstrip("@") != clean_u]
            if len(new_t) < len(targets):
                cfg["targets"] = new_t
                save_config(cfg)
                send_telegram_msg(f"🗑️ Berhasil menghapus *{username}* dari pantauan.")
            else:
                send_telegram_msg(f"⚠️ Target *{username}* tidak ditemukan.")

        elif cmd == "/status":
            recording = [k for k, v in ACTIVE_STATUS.items() if v]
            if recording:
                send_telegram_msg(f"🔴 *Sedang Merekam ({len(recording)} live aktif):*\n" + "\n".join([f"- {r}" for r in recording]))
            else:
                send_telegram_msg("💤 Tidak ada live yang sedang berlangsung saat ini. Bot tetap standby memantau 24/7.")

        elif cmd == "/recordings":
            cfg = load_config()
            rec_dir = cfg.get("output_directory", "recordings")
            if not os.path.exists(rec_dir):
                send_telegram_msg("📁 Belum ada rekaman lokal.")
                return

            files = [f for f in os.listdir(rec_dir) if f.endswith(".mp4") or f.endswith(".ts")]
            if not files:
                send_telegram_msg("📁 Folder lokal kosong (file rekaman sudah otomatis diunggah ke Google Drive).")
                return

            lines = [f"📁 *File Rekaman Lokal ({len(files)} file):*"]
            for f in sorted(files)[-10:]:
                fp = os.path.join(rec_dir, f)
                sz_mb = os.path.getsize(fp) / (1024 * 1024)
                lines.append(f"• `{f}` ({sz_mb:.1f} MB)")
            send_telegram_msg("\n".join(lines))

        elif cmd == "/drive":
            cfg = load_config()
            folder_id = cfg.get("google_drive_rclone", {}).get("folder_id", "1jv4Di6t7ceemzIljL641y5zSKD9oNq03")
            send_telegram_msg(
                "☁️ *Google Drive Rekaman:*\n"
                f"[Klik di sini untuk membuka Folder Rekaman](https://drive.google.com/drive/folders/{folder_id})"
            )
