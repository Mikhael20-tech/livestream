"""
Core Live Recorder Engine v2.1
Mendukung: TikTok, Band.us, YouTube, Twitch, Kick, dan Custom URLs.
Fitur:
- Penamaan file rapi & terstruktur dengan Waktu Indonesia Barat (WIB)
- Bypass WAF & 18+ Live TikTok
- Ekstraksi Direct CDN FLV/HLS via FFmpeg (0% CPU, Lossless)
- Fragmented MP4 (+frag_keyframe) agar bisa langsung diputar saat masih merekam
- Pemisahan Segmen Otomatis (Part 01, Part 02) per 60 menit
- Auto Upload Google Drive via Rclone
- Pemantau Status Disk/RAM VPS & Storage Warning
"""

import os
import sys
import time
import json
import logging
import subprocess
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import deque

# Zona Waktu Indonesia Barat (WIB = UTC+7)
WIB = timezone(timedelta(hours=7))

# In-memory log buffer for Web UI
LOG_BUFFER = deque(maxlen=150)
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
    """Bersihkan karakter terlarang dari nama file Windows & Linux."""
    keepcharacters = (' ', '.', '_', '-', '[', ']', '(', ')')
    return "".join(c for c in name if c.isalnum() or c in keepcharacters).rstrip()


def get_vps_health() -> dict:
    """Mengambil status pemakaian Disk dan RAM VPS secara cross-platform."""
    import shutil
    try:
        path = "/" if os.name != "nt" else "."
        total, used, free = shutil.disk_usage(path)
        disk_total_gb = total / (1024**3)
        disk_used_gb = used / (1024**3)
        disk_free_gb = free / (1024**3)
        disk_pct = (used / total) * 100
    except Exception:
        disk_total_gb, disk_used_gb, disk_free_gb, disk_pct = 0, 0, 0, 0

    ram_used_mb, ram_total_mb, ram_pct = 0, 0, 0
    try:
        if os.path.exists("/proc/meminfo"):
            with open("/proc/meminfo", "r") as f:
                lines = f.readlines()
            mem = {}
            for line in lines:
                parts = line.split(":")
                if len(parts) == 2:
                    mem[parts[0].strip()] = int(parts[1].strip().split()[0])
            total_k = mem.get("MemTotal", 0)
            avail_k = mem.get("MemAvailable", 0)
            ram_total_mb = total_k / 1024
            ram_used_mb = (total_k - avail_k) / 1024
            ram_pct = (ram_used_mb / ram_total_mb * 100) if ram_total_mb > 0 else 0
    except Exception:
        pass

    return {
        "disk_total_gb": round(disk_total_gb, 1),
        "disk_used_gb": round(disk_used_gb, 1),
        "disk_free_gb": round(disk_free_gb, 1),
        "disk_pct": round(disk_pct, 1),
        "ram_total_mb": round(ram_total_mb, 1),
        "ram_used_mb": round(ram_used_mb, 1),
        "ram_pct": round(ram_pct, 1)
    }


LAST_STORAGE_ALERT_TIME = 0
def check_storage_alert():
    """Kirim notifikasi Telegram jika kapasitas disk tersisa di bawah threshold."""
    global LAST_STORAGE_ALERT_TIME
    now = time.time()
    if now - LAST_STORAGE_ALERT_TIME < 3600:
        return

    health = get_vps_health()
    free_pct = 100 - health["disk_pct"]
    cfg = load_config()
    threshold = cfg.get("storage_alert_threshold_percent", 15)

    if 0 < free_pct < threshold:
        LAST_STORAGE_ALERT_TIME = now
        msg = (
            f"⚠️ *PERINGATAN KAPASITAS VPS RENDAH!*\n"
            f"Sisa penyimpanan: *{health['disk_free_gb']} GB* ({free_pct:.1f}% tersisa).\n"
            f"Batas minimum: {threshold}%.\n"
            f"File di Google Drive aman, namun segera periksa disk VPS."
        )
        try:
            from telegram_bot import send_telegram_msg
            send_telegram_msg(msg)
        except Exception:
            pass


def get_stream_url(platform: str, identifier: str) -> str:
    """Format input menjadi full live URL jika belum berupa URL."""
    ident = identifier.strip()
    if ident.startswith("http://") or ident.startswith("https://"):
        return ident

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
    elif plat == "band":
        return f"https://band.us/band/{clean_id}"
    else:
        return f"https://www.tiktok.com/@{clean_id}/live"


def upload_to_gdrive(local_file_path: str, gdrive_cfg: dict):
    """Mengunggah video ke Google Drive menggunakan Rclone dan menghapus lokal jika diminta."""
    remote = gdrive_cfg.get("rclone_remote", "gdrive")
    rclone_folder = gdrive_cfg.get("rclone_folder", "Rekaman").strip("/")
    delete_local = gdrive_cfg.get("delete_local_after_upload", True)

    action = "move" if delete_local else "copy"
    destination = f"{remote}:{rclone_folder}/"
    filename = os.path.basename(local_file_path)
    logger.info(f"☁️ Mengunggah ke Google Drive: {filename}...")

    try:
        cmd = ["rclone", action, local_file_path, destination, "--progress"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            logger.info(f"🎉 Sukses ter-upload ke Google Drive: {filename}")
            try:
                from telegram_bot import send_telegram_msg
                folder_id = gdrive_cfg.get("folder_id", "1jv4Di6t7ceemzIljL641y5zSKD9oNq03")
                send_telegram_msg(
                    f"🎉 *VIDEO SUKSES KE GOOGLE DRIVE!*\n📁 File: `{filename}`\n"
                    f"[Klik untuk Buka Folder Rekaman](https://drive.google.com/drive/folders/{folder_id})"
                )
            except Exception:
                pass
            if delete_local:
                logger.info(f"🗑️ File lokal {filename} telah dihapus agar disk VPS tetap lega.")
        else:
            logger.error(f"❌ Gagal upload ke Rclone: {res.stderr}")
    except FileNotFoundError:
        logger.warning("⚠️ Rclone belum terinstall di sistem. File tetap disimpan di folder lokal.")
    except Exception as e:
        logger.error(f"⚠️ Error saat upload Rclone: {e}")


def check_tiktok_live(username: str, sessionid: str = "", quality: str = "hd") -> tuple[bool, str]:
    """
    Cek live TikTok langsung via API resmi dengan sessionid cookie.
    Tahan anti-bot WAF dan mampu menembus live 18+ / mature restriction.
    """
    import urllib.request
    clean_user = username.strip().lstrip("@")
    page_url = f"https://www.tiktok.com/@{clean_user}/live"
    api_url = f"https://www.tiktok.com/api-live/user/room/?aid=1988&sourceType=54&uniqueId={clean_user}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Referer": "https://www.tiktok.com/",
        "Accept": "application/json, text/plain, */*"
    }
    if sessionid:
        headers["Cookie"] = f"sessionid={sessionid}"

    try:
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            room_data = data.get("data", {})
            user_info = room_data.get("user", {})
            live_room = room_data.get("liveRoom", {})
            status = live_room.get("status")

            stream_url = ""
            raw_sd = live_room.get("streamData", {}).get("pull_data", {}).get("stream_data")
            if raw_sd:
                try:
                    sd_json = json.loads(raw_sd)
                    data_obj = sd_json.get("data", {})

                    q_choice = (quality or "hd").lower()
                    if q_choice == "audio_only":
                        order = ["ao"]
                    elif q_choice == "origin":
                        order = ["origin", "hd", "sd", "ld"]
                    elif q_choice == "sd":
                        order = ["sd", "ld", "hd", "origin"]
                    elif q_choice == "ld":
                        order = ["ld", "sd", "hd", "origin"]
                    else:
                        order = ["hd", "origin", "sd", "ld"]

                    for q in order:
                        if q in data_obj:
                            main = data_obj[q].get("main", {})
                            stream_url = main.get("flv") or main.get("hls")
                            if stream_url:
                                break

                    if not stream_url and data_obj:
                        for q_val in data_obj.values():
                            main = q_val.get("main", {})
                            stream_url = main.get("flv") or main.get("hls")
                            if stream_url:
                                break
                except Exception:
                    pass

            if status == 2:
                title = live_room.get("title", "")
                logger.info(f"✨ TikTok API: @{clean_user} terdeteksi AKTIF LIVE! Judul: '{title}' [{quality.upper()}]")
                return True, stream_url or page_url
            elif status == 4:
                return False, ""
    except Exception as e:
        logger.debug(f"urllib TikTok check error: {e}")

    try:
        from curl_cffi import requests
        cookies = {"sessionid": sessionid} if sessionid else {}
        r = requests.get(api_url, cookies=cookies, headers=headers, impersonate="chrome124", timeout=10)
        if r.status_code == 200:
            data = r.json()
            live_room = data.get("data", {}).get("liveRoom", {})
            if live_room.get("status") == 2:
                return True, page_url
    except Exception:
        pass

    return False, ""


def check_band_live(target_url: str) -> tuple[bool, str]:
    """Cek live stream Band.us via yt-dlp atau inspeksi halaman HLS."""
    clean_target = target_url.strip()
    if not clean_target.startswith("http"):
        clean_target = f"https://band.us/band/{clean_target.lstrip('@')}"

    try:
        import yt_dlp
        ydl_opts = {"quiet": True, "no_warnings": True, "extract_flat": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(clean_target, download=False)
            if info and (info.get("is_live") or info.get("url")):
                return True, info.get("url") or clean_target
    except Exception:
        pass

    try:
        import urllib.request
        req = urllib.request.Request(
            clean_target,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
            if "live_status\":\"ONAIR\"" in html or "isLive\":true" in html or ".m3u8" in html:
                import re
                m3u8_match = re.search(r'(https?://[^\s"\']+\.m3u8[^\s"\']*)', html)
                if m3u8_match:
                    return True, m3u8_match.group(1).replace("\\u0026", "&")
                return True, clean_target
    except Exception:
        pass

    return False, ""


def is_live_active(url: str, platform: str = "", target: str = "", quality: str = "hd") -> tuple[bool, str]:
    """Cek apakah target sedang live."""
    cfg = load_config()
    sessionid = cfg.get("tiktok_sessionid", "")
    plat = platform.lower()

    if plat == "tiktok" or "tiktok.com" in url:
        username = target if target else url.split("@")[-1].split("/")[0]
        active, stream_url = check_tiktok_live(username, sessionid, quality=quality)
        if active:
            return True, stream_url

    if plat == "band" or "band.us" in url:
        active, stream_url = check_band_live(url)
        if active:
            return True, stream_url

    try:
        import streamlink
        session = streamlink.Streamlink()
        if sessionid and ("tiktok.com" in url or plat == "tiktok"):
            session.set_option("http-cookies", f"sessionid={sessionid}")
            session.set_option("http-headers", "Referer=https://www.tiktok.com/")
        streams = session.streams(url)
        if streams:
            return True, url
    except Exception:
        pass

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
                return True, url
    except Exception:
        pass

    return False, ""


def record_stream(url: str, output_path: str, platform: str, target: str, stop_event: threading.Event = None) -> bool:
    """
    Merekam stream menggunakan direct FFmpeg CDN atau Streamlink.
    Mendukung Fragmented MP4 (+frag_keyframe) dan pemotongan segmen per jam (Part 01, Part 02).
    """
    status_key = f"{platform.lower()}_{target.lower().lstrip('@')}"
    ACTIVE_STATUS[status_key] = True
    logger.info(f"🔴 [{platform.upper()} - {target}] LIVE TERDETEKSI! Memulai rekaman...")

    try:
        from telegram_bot import send_telegram_msg
        send_telegram_msg(f"🔴 *LIVE TERDETEKSI!*\nTarget: *{target}* ({platform.upper()})\nBot sedang merekam otomatis...")
    except Exception:
        pass

    cfg = load_config()
    sessionid = cfg.get("tiktok_sessionid", "")
    segment_mins = int(cfg.get("segment_minutes", 0))
    gdrive_cfg = cfg.get("google_drive_rclone", {})
    output_dir = os.path.dirname(output_path) or "recordings"

    is_segmented = segment_mins > 0
    seg_prefix = os.path.basename(output_path).replace(".mp4", "")
    seg_pattern = os.path.join(output_dir, f"{seg_prefix} (Part %02d).mp4")

    # Mode 1: Jika URL berupa direct CDN Stream (.flv atau .m3u8)
    if "tiktokcdn.com" in url or ".flv" in url or (url.startswith("http") and ".m3u8" in url):
        headers_str = "Referer: https://www.tiktok.com/\r\nUser-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36\r\n"
        
        # Flags fragmented mp4 agar video bisa diputar di web browser saat proses rekaman masih berlangsung
        mov_flags = "+frag_keyframe+empty_moov+default_base_moof"

        if is_segmented:
            seg_secs = segment_mins * 60
            logger.info(f"✂️ Mode Segmen Aktif: Memotong tiap {segment_mins} menit ({seg_secs}s) -> (Part 01, Part 02...)")
            cmd = [
                "ffmpeg", "-y",
                "-headers", headers_str,
                "-i", url,
                "-c", "copy",
                "-movflags", mov_flags,
                "-f", "segment",
                "-segment_time", str(seg_secs),
                "-segment_start_number", "1",
                "-reset_timestamps", "1",
                "-reconnect", "1",
                "-reconnect_at_eof", "1",
                "-reconnect_streamed", "1",
                "-reconnect_delay_max", "5",
                seg_pattern
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-headers", headers_str,
                "-i", url,
                "-c", "copy",
                "-movflags", mov_flags,
                "-reconnect", "1",
                "-reconnect_at_eof", "1",
                "-reconnect_streamed", "1",
                "-reconnect_delay_max", "5",
                output_path
            ]
    else:
        # Mode 2: Streamlink untuk platform umum
        extra_args = []
        if sessionid and (platform.lower() == "tiktok" or "tiktok.com" in url):
            extra_args.extend([
                "--http-cookie", f"sessionid={sessionid}",
                "--http-header", "Referer=https://www.tiktok.com/",
                "--http-header", "User-Agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            ])

        cmd = [
            sys.executable, "-m", "streamlink",
            "--default-stream", "best",
            "--retry-streams", "5",
            "--retry-max", "5",
            "--stream-segment-threads", "2"
        ] + extra_args + [
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

        uploaded_parts = set()
        def check_and_upload_completed_segments():
            if not is_segmented or not gdrive_cfg.get("enabled", False):
                return
            try:
                candidates = sorted([
                    f for f in os.listdir(output_dir)
                    if f.startswith(seg_prefix) and f.endswith(".mp4") and f not in uploaded_parts
                ])
                if len(candidates) > 1:
                    for f in candidates[:-1]:
                        full_f = os.path.join(output_dir, f)
                        if os.path.exists(full_f) and os.path.getsize(full_f) > 5000:
                            logger.info(f"📦 Part selesai: {f}, mengunggah ke Google Drive...")
                            uploaded_parts.add(f)
                            upload_to_gdrive(full_f, gdrive_cfg)
            except Exception as e:
                logger.debug(f"Segment uploader notice: {e}")

        last_check_seg = time.time()

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

            if time.time() - last_check_seg > 30:
                last_check_seg = time.time()
                check_and_upload_completed_segments()

        try:
            process.wait(timeout=3)
        except Exception:
            pass

        logger.info(f"⏹️ [{platform.upper()} - {target}] Rekaman selesai (Live berakhir).")
        ACTIVE_STATUS[status_key] = False

        if is_segmented:
            try:
                remaining = sorted([
                    f for f in os.listdir(output_dir)
                    if f.startswith(seg_prefix) and f.endswith(".mp4") and f not in uploaded_parts
                ])
                for f in remaining:
                    full_f = os.path.join(output_dir, f)
                    if os.path.exists(full_f) and os.path.getsize(full_f) > 1024:
                        size_mb = os.path.getsize(full_f) / (1024 * 1024)
                        logger.info(f"✅ Part tersimpan: {f} ({size_mb:.2f} MB)")
                        if gdrive_cfg.get("enabled", False):
                            upload_to_gdrive(full_f, gdrive_cfg)
            except Exception as e:
                logger.error(f"Error upload final segments: {e}")
        else:
            if os.path.exists(output_path):
                size_mb = os.path.getsize(output_path) / (1024 * 1024)
                logger.info(f"✅ File tersimpan: {output_path} ({size_mb:.2f} MB)")
                if gdrive_cfg.get("enabled", False):
                    upload_to_gdrive(output_path, gdrive_cfg)

        return True

    except Exception as e:
        logger.error(f"Error saat merekam: {e}")
        ACTIVE_STATUS[status_key] = False
        return False


class TargetWatcher(threading.Thread):
    """Worker thread yang memantau satu akun/channel secara terus-menerus."""

    def __init__(self, platform: str, target: str, output_dir: str, check_interval: int = 30, quality: str = "hd"):
        super().__init__(daemon=True)
        self.platform = platform
        self.target = target
        self.quality = quality
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
                check_storage_alert()

                active, stream_url = is_live_active(self.url, self.platform, self.target, quality=self.quality)
                if active:
                    # Format nama file rapi dengan Waktu Indonesia Barat (WIB)
                    now_wib = datetime.now(WIB)
                    timestamp_str = now_wib.strftime("%Y-%m-%d_%H.%M")
                    
                    plat_title = "TikTok" if self.platform.lower() == "tiktok" else (
                        "Band" if self.platform.lower() == "band" else self.platform.capitalize()
                    )
                    safe_target = sanitize_filename(self.target.lstrip("@"))
                    filename = f"[{plat_title}] {safe_target} - {timestamp_str} WIB.mp4"
                    output_file = str(self.output_dir / filename)

                    record_stream(
                        url=stream_url or self.url,
                        output_path=output_file,
                        platform=self.platform,
                        target=self.target,
                        stop_event=self.stop_event
                    )
                    time.sleep(10)
                else:
                    logger.info(f"💤 [{self.platform.upper()} - {self.target}] Sedang offline. Cek lagi dalam {self.check_interval} detik...")
            except Exception as e:
                logger.warning(f"⚠️ Error saat cek [{self.target}]: {e}")

            for _ in range(self.check_interval):
                if self.stop_event.is_set():
                    break
                time.sleep(1)


def load_config(config_file: str = "config.json") -> dict:
    default_cfg = {
        "check_interval_seconds": 30,
        "output_directory": "recordings",
        "segment_minutes": 60,
        "storage_alert_threshold_percent": 15,
        "default_quality": "hd",
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
