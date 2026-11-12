"""
Core Live Recorder Engine
Mendukung: TikTok, YouTube, Twitch, Kick, dan platform lainnya.
"""

import os
import sys
import time
import json
import logging
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from collections import deque

# In-memory log buffer for Web UI
LOG_BUFFER = deque(maxlen=120)
ACTIVE_STATUS = {}  # key: f"{platform}_{target}", value: bool (True if recording)

class BufferLogHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            LOG_BUFFER.append(msg)
        except Exception:
            pass

# Setup logging
logger = logging.getLogger("LiveRecorder")
logger.setLevel(logging.INFO)

formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

# Stream handler for console
sh = logging.StreamHandler(sys.stdout)
sh.setFormatter(formatter)
logger.addHandler(sh)

# Buffer handler for Web UI
bh = BufferLogHandler()
bh.setFormatter(formatter)
logger.addHandler(bh)


def sanitize_filename(name: str) -> str:
    """Bersihkan karakter ilegal dari nama file Windows & Linux."""
    keepcharacters = (' ', '.', '_', '-')
    return "".join(c for c in name if c.isalnum() or c in keepcharacters).rstrip()


def get_stream_url(platform: str, identifier: str) -> str:
    """Format input menjadi full live URL jika belum berupa URL."""
    ident = identifier.strip()
    if ident.startswith("http://") or ident.startswith("https://"):
        return ident

    # Bersihkan awalan @ jika ada
    clean_id = ident.lstrip("@")

    plat = platform.lower()
    if plat == "tiktok":
        return f"https://www.tiktok.com/@{clean_id}/live"
    elif plat == "youtube":
        return f"https://www.youtube.com/@{clean_id}/live"
    elif plat == "twitch":
        return f"https://www.twitch.tv/{clean_id}"
    elif plat == "kick":
        return f"https://kick.com/{clean_id}"
    else:
        return f"https://www.tiktok.com/@{clean_id}/live"


def upload_to_gdrive(local_file_path: str, gdrive_cfg: dict):
    """Mengunggah video ke Google Drive menggunakan Rclone dan menghapus lokal jika diminta."""
    remote = gdrive_cfg.get("rclone_remote", "gdrive")
    rclone_folder = gdrive_cfg.get("rclone_folder", "Rekaman").strip("/")
    delete_local = gdrive_cfg.get("delete_local_after_upload", True)

    action = "move" if delete_local else "copy"
    destination = f"{remote}:{rclone_folder}/"
    cmd = ["rclone", action, local_file_path, destination, "--progress"]
    logger.info(f"☁️ Mengunggah ke Google Drive: {destination}...")

    try:
        cmd = ["rclone", action, local_file_path, destination, "--progress"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            logger.info("🎉 Sukses ter-upload ke Google Drive!")
            try:
                from telegram_bot import send_telegram_msg
                filename = os.path.basename(local_file_path)
                send_telegram_msg(f"🎉 *VIDEO SUKSES KE GOOGLE DRIVE!*\n📁 File: `{filename}`\n[Klik untuk Buka Folder Rekaman](https://drive.google.com/drive/folders/1jv4Di6t7ceemzIljL641y5zSKD9oNq03)")
            except Exception:
                pass
            if delete_local:
                logger.info("🗑️ File lokal di VPS telah dihapus agar disk tetap lega.")
        else:
            logger.error(f"❌ Gagal upload ke Rclone: {res.stderr}")
    except FileNotFoundError:
        logger.warning("⚠️ Rclone belum terinstall di sistem. File tetap disimpan di folder lokal.")
    except Exception as e:
        logger.error(f"⚠️ Error saat upload Rclone: {e}")


def is_live_active(url: str) -> bool:
    """
    Cek apakah target sedang live.
    Coba streamlink dulu, jika gagal coba yt-dlp.
    """
    try:
        import streamlink
        session = streamlink.Streamlink()
        # Nonaktifkan prompt interaktif
        streams = session.streams(url)
        if streams:
            return True
    except Exception:
        pass

    # Fallback cek via yt-dlp
    try:
        import yt_dlp
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "impersonate": "chrome"
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if info and info.get("is_live"):
                return True
    except Exception:
        pass

    return False


def record_stream(url: str, output_path: str, platform: str, target: str, stop_event: threading.Event = None) -> bool:
    """
    Merekam stream menggunakan streamlink (rekomendasi terbaik untuk live stream).
    Fallback ke yt-dlp jika streamlink gagal.
    """
    status_key = f"{platform.lower()}_{target.lower().lstrip('@')}"
    ACTIVE_STATUS[status_key] = True
    logger.info(f"🔴 [{platform.upper()} - {target}] LIVE TERDETEKSI! Memulai rekaman...")
    logger.info(f"📁 Menyimpan ke: {output_path}")

    try:
        from telegram_bot import send_telegram_msg
        send_telegram_msg(f"🔴 *LIVE TERDETEKSI!*\nTarget: *{target}* ({platform.upper()})\nBot sedang merekam otomatis...")
    except Exception:
        pass

    # Metode 1: Streamlink
    cmd = [
        sys.executable, "-m", "streamlink",
        "--default-stream", "best",
        "--retry-streams", "5",
        "--retry-max", "5",
        "--stream-segment-threads", "2",
        "--output", output_path,
        url,
        "best"
    ]

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )

        while True:
            if stop_event and stop_event.is_set():
                logger.info(f"Menghentikan rekaman [{target}] karena diminta stop...")
                try:
                    process.terminate()
                    process.wait(timeout=4)
                except Exception:
                    try:
                        process.kill()
                    except Exception:
                        pass
                break

            retcode = process.poll()
            if retcode is not None:
                break

            line = process.stdout.readline()
            if line:
                line_str = line.strip()
                if "Written" in line_str or "error" in line_str.lower():
                    logger.debug(f"[{target}] {line_str}")
            else:
                time.sleep(0.5)

        try:
            process.wait(timeout=3)
        except Exception:
            pass

        logger.info(f"⏹️ [{platform.upper()} - {target}] Rekaman selesai (Live berakhir).")
        ACTIVE_STATUS[status_key] = False
        if os.path.exists(output_path):
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            logger.info(f"✅ File tersimpan: {output_path} ({size_mb:.2f} MB)")
            
            # Cek apakah fitur Google Drive via Rclone aktif
            cfg = load_config()
            gdrive_cfg = cfg.get("google_drive_rclone", {})
            if gdrive_cfg.get("enabled", False):
                upload_to_gdrive(output_path, gdrive_cfg)
        return True

    except Exception as e:
        logger.error(f"Error saat merekam dengan streamlink: {e}")

    # Metode 2: yt-dlp fallback
    try:
        logger.info(f"Mencoba rekaman fallback dengan yt-dlp...")
        yt_cmd = [
            sys.executable, "-m", "yt_dlp",
            "--live-from-start",
            "--no-part",
            "-o", output_path,
            url
        ]
        subprocess.run(yt_cmd, check=True)
        return True
    except Exception as e:
        logger.error(f"Fallback yt-dlp juga error: {e}")
        return False


class TargetWatcher(threading.Thread):
    """Worker thread yang memantau satu akun/channel secara terus-menerus."""

    def __init__(self, platform: str, target: str, output_dir: str, check_interval: int = 30):
        super().__init__(daemon=True)
        self.platform = platform
        self.target = target
        self.output_dir = Path(output_dir)
        self.check_interval = check_interval
        self.url = get_stream_url(platform, target)
        self.stop_event = threading.Event()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def stop(self):
        self.stop_event.set()

    def run(self):
        logger.info(f"👀 Memulai pemantauan: [{self.platform.upper()}] {self.target} (Cek tiap {self.check_interval}s)")
        
        while not self.stop_event.is_set():
            try:
                active = is_live_active(self.url)
                if active:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    safe_target = sanitize_filename(self.target.lstrip("@"))
                    filename = f"{self.platform}_{safe_target}_{timestamp}.mp4"
                    output_file = str(self.output_dir / filename)

                    # Mulai rekam sampai live selesai
                    record_stream(
                        url=self.url,
                        output_path=output_file,
                        platform=self.platform,
                        target=self.target,
                        stop_event=self.stop_event
                    )

                    # Jeda sebentar sebelum mulai cek lagi
                    time.sleep(10)
                else:
                    logger.info(f"💤 [{self.platform.upper()} - {self.target}] Sedang offline. Cek lagi dalam {self.check_interval} detik...")
            except Exception as e:
                logger.warning(f"⚠️ Error saat cek [{self.target}]: {e}")

            # Sleep terbagi agar responsif saat diminta stop
            for _ in range(self.check_interval):
                if self.stop_event.is_set():
                    break
                time.sleep(1)


def load_config(config_file: str = "config.json") -> dict:
    default_cfg = {
        "check_interval_seconds": 30,
        "output_directory": "recordings",
        "targets": []
    }
    if not os.path.exists(config_file):
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(default_cfg, f, indent=2)
        return default_cfg

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Gagal membaca {config_file}: {e}")
        return default_cfg


def save_config(cfg: dict, config_file: str = "config.json"):
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

