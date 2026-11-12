# 🔴 Multi-Platform Auto Live Stream Recorder

Bot otomatis untuk memantau dan merekam siaran langsung (Live Stream) dari **TikTok**, **YouTube**, **Twitch**, **Kick**, dan platform streaming lainnya.

---

## ⚡ Fitur Utama

- **Auto-Detect & Auto-Record**: Begitu akun target mulai live, bot langsung otomatis merekam.
- **Kualitas Asli (Lossless)**: Merekam stream langsung ke file `.mp4` tanpa re-encoding (sangat hemat CPU & RAM).
- **Multi-Target**: Bisa memantau banyak akun sekaligus secara bersamaan (multi-threading).
- **Anti-Disconnect**: Auto-reconnect jika koneksi live sempat tersendat.
- **Bisa Dijalankan di VPS**: Agar tetap merekam non-stop meskipun laptopmu mati.

---

## 💻 Cara Pakai di Laptop (Windows)

1. Buka folder ini di PowerShell / Terminal:
   ```powershell
   cd d:\tiktokrec
   ```

2. Jalankan bot:
   ```powershell
   python main.py
   ```

3. Pilih menu:
   - **Menu 1**: Jalankan Auto-Recorder (memantau semua akun di `config.json`).
   - **Menu 2**: Langsung rekam 1 akun atau 1 URL live tertentu saat ini juga.
   - **Menu 3**: Tambah target akun baru (TikTok, YouTube, Twitch, dll).
   - **Menu 4**: Cek & kelola daftar target.
   - **Menu 5**: Cek daftar video hasil rekaman.

---

## 🌐 Cara Jalankan di VPS / Server Cloud (Bisa Merekam Saat Laptop Mati)

Jika kamu punya VPS Linux (misal Ubuntu 22.04 / 24.04):

### 1. Masuk ke VPS via SSH
```bash
ssh root@IP_VPS_KAMU
```

### 2. Install Python & FFmpeg di VPS
```bash
sudo apt update && sudo apt install -y python3 python3-pip ffmpeg git screen
```

### 3. Salin Folder / File Script ini ke VPS
Kamu bisa upload file `main.py`, `recorder.py`, `config.json`, dan `requirements.txt` ke VPS, lalu install dependensinya:
```bash
pip3 install -r requirements.txt
```

### 4. Jalankan 24 Jam di Background Menggunakan `screen`
Agar script tetap berjalan saat jendela SSH ditutup atau laptop dimatikan:
```bash
# Buat session screen baru
screen -S livebot

# Jalankan bot otomatis
python3 main.py --auto
```
- Tekan `Ctrl + A` lalu tekan `D` untuk keluar dari layar screen (bot tetap berjalan di background server).
- Untuk melihat log bot lagi kapan saja, ketik:
  ```bash
  screen -r livebot
  ```

---

## ☁️ Auto-Upload ke Google Drive (Agar Disk VPS Tidak Penuh)

Di file `config.json`, ada pengaturan:
```json
"google_drive_rclone": {
  "enabled": true,
  "rclone_remote": "gdrive",
  "rclone_folder": "TikTokRec",
  "delete_local_after_upload": true
}
```

Jika `"enabled": true`:
1. Setiap kali target selesai live stream, video langsung otomatis di-upload ke folder **`TikTokRec`** di Google Drive kamu.
2. Setelah sukses ter-upload, video di VPS langsung dihapus otomatis (`delete_local_after_upload: true`), sehingga disk server VPS tidak akan pernah kepenuhan.

