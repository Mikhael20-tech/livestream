"""
Main CLI Menu untuk Auto Live Recorder
"""

import os
import sys
import time
from pathlib import Path
from recorder import (
    load_config,
    save_config,
    TargetWatcher,
    record_stream,
    get_stream_url,
    sanitize_filename
)
from datetime import datetime


def banner():
    print("""
=============================================================
           🔴 AUTO LIVE STREAM RECORDER BOT 🔴              
   Mendukung: TikTok, YouTube, Twitch, Kick, & Custom URLs   
=============================================================
""")


def start_auto_recorder():
    cfg = load_config()
    targets = [t for t in cfg.get("targets", []) if t.get("enabled", True)]
    
    if not targets:
        print("\n[!] Belum ada target akun di config.json.")
        print("[!] Tambahkan target terlebih dahulu melalui menu 3.\n")
        return

    output_dir = cfg.get("output_directory", "recordings")
    interval = cfg.get("check_interval_seconds", 30)

    print(f"\n[+] Memulai bot untuk {len(targets)} target:")
    for t in targets:
        print(f"    - [{t.get('platform', 'tiktok').upper()}] {t.get('username')}")
    print(f"[+] Folder output: {os.path.abspath(output_dir)}")
    print("[+] Tekan Ctrl + C kapan saja untuk menghentikan bot.\n")

    watchers = []
    for t in targets:
        w = TargetWatcher(
            platform=t.get("platform", "tiktok"),
            target=t.get("username"),
            output_dir=output_dir,
            check_interval=interval
        )
        w.start()
        watchers.append(w)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n[!] Menghentikan semua pemantauan...")
        for w in watchers:
            w.stop()
        for w in watchers:
            w.join(timeout=2)
        print("[+] Semua proses dihentikan dengan aman. Sampai jumpa!")


def record_single_target():
    print("\n--- REKAM LIVE LANGSUNG (SINGLE) ---")
    print("Pilih Platform:")
    print("1. TikTok")
    print("2. YouTube")
    print("3. Twitch")
    print("4. Kick / URL Bebas")
    p_choice = input("Pilihan [1-4] (default 1): ").strip()

    plat_map = {"1": "tiktok", "2": "youtube", "3": "twitch", "4": "custom"}
    platform = plat_map.get(p_choice, "tiktok")

    target = input("Masukkan Username (misal: @username) atau URL lengkap: ").strip()
    if not target:
        print("[!] Input tidak boleh kosong.")
        return

    cfg = load_config()
    output_dir = Path(cfg.get("output_directory", "recordings"))
    output_dir.mkdir(parents=True, exist_ok=True)

    url = get_stream_url(platform, target)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_target = sanitize_filename(target.lstrip("@"))
    output_file = str(output_dir / f"{platform}_{safe_target}_{timestamp}.mp4")

    print(f"\n[+] Menghubungkan ke: {url}")
    print(f"[+] Output: {output_file}")
    print("[+] Tekan Ctrl + C untuk berhenti merekam.\n")

    try:
        record_stream(
            url=url,
            output_path=output_file,
            platform=platform,
            target=target
        )
    except KeyboardInterrupt:
        print("\n[+] Rekaman dihentikan oleh pengguna.")


def add_target():
    print("\n--- TAMBAH TARGET BARU KE CONFIG ---")
    print("1. TikTok")
    print("2. YouTube")
    print("3. Twitch")
    print("4. Custom URL")
    p_choice = input("Pilihan [1-4] (default 1): ").strip()
    plat_map = {"1": "tiktok", "2": "youtube", "3": "twitch", "4": "custom"}
    platform = plat_map.get(p_choice, "tiktok")

    username = input("Masukkan username (contoh: akun_keren): ").strip()
    if not username:
        print("[!] Username tidak boleh kosong.")
        return

    cfg = load_config()
    cfg.setdefault("targets", [])
    
    # Cek duplikat
    for t in cfg["targets"]:
        if t.get("username").lower() == username.lower() and t.get("platform") == platform:
            print(f"[!] Target {username} sudah ada di daftar.")
            return

    cfg["targets"].append({
        "platform": platform,
        "username": username,
        "enabled": True
    })
    save_config(cfg)
    print(f"[✅] Berhasil menambahkan [{platform.upper()}] {username}!")


def list_targets():
    cfg = load_config()
    targets = cfg.get("targets", [])
    print("\n--- DAFTAR TARGET DI CONFIG ---")
    if not targets:
        print("Belum ada target.")
        return

    for idx, t in enumerate(targets, 1):
        status = "AKTIF" if t.get("enabled", True) else "NONAKTIF"
        print(f"{idx}. [{t.get('platform').upper()}] {t.get('username')} ({status})")

    sub = input("\nIngin hapus salah satu target? (Ketik nomor / tekan Enter untuk batal): ").strip()
    if sub.isdigit():
        num = int(sub)
        if 1 <= num <= len(targets):
            removed = targets.pop(num - 1)
            save_config(cfg)
            print(f"[✅] Dihapus: [{removed.get('platform')}] {removed.get('username')}")


def list_recordings():
    cfg = load_config()
    rec_dir = Path(cfg.get("output_directory", "recordings"))
    if not rec_dir.exists():
        print("\n[!] Belum ada rekaman tersimpan.")
        return

    files = list(rec_dir.glob("*.mp4")) + list(rec_dir.glob("*.ts"))
    print(f"\n--- HASIL REKAMAN ({len(files)} File) ---")
    if not files:
        print("Folder rekaman masih kosong.")
        return

    for f in sorted(files, key=lambda x: x.stat().st_mtime, reverse=True):
        size_mb = f.stat().st_size / (1024 * 1024)
        mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        print(f"- {f.name} ({size_mb:.2f} MB | {mtime})")


def main():
    while True:
        banner()
        print("Menu:")
        print("1. 🚀 Jalankan Auto-Recorder (Pantau Semua Target 24/7)")
        print("2. 🔴 Rekam Langsung 1 Akun Sekarang")
        print("3. ➕ Tambah Target Akun Baru")
        print("4. 📋 Lihat / Hapus Daftar Target")
        print("5. 📁 Lihat Hasil Rekaman")
        print("0. ❌ Keluar")

        choice = input("\nPilih menu [0-5]: ").strip()
        if choice == "1":
            start_auto_recorder()
        elif choice == "2":
            record_single_target()
        elif choice == "3":
            add_target()
        elif choice == "4":
            list_targets()
        elif choice == "5":
            list_recordings()
        elif choice == "0":
            print("\nTerima kasih! Sampai jumpa.\n")
            break
        else:
            print("\n[!] Pilihan tidak valid.")
        
        input("\nTekan Enter untuk kembali ke menu...")


if __name__ == "__main__":
    # Jika dijalankan dengan argumen CLI langsung misal: python main.py --auto
    if len(sys.argv) > 1 and sys.argv[1] == "--auto":
        start_auto_recorder()
    else:
        main()

