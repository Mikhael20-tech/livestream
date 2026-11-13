"""
Flask Web Dashboard untuk Auto Live Stream Recorder v2.1
"""

import os
import sys
import threading
from datetime import datetime
from flask import Flask, render_template_string, jsonify, request, send_from_directory, abort
from recorder import (
    load_config,
    save_config,
    TargetWatcher,
    LOG_BUFFER,
    ACTIVE_STATUS,
    logger,
    get_vps_health
)

app = Flask(__name__)

# Global state for background watcher threads
ENGINE_LOCK = threading.Lock()
WATCHERS = []
IS_ENGINE_RUNNING = False
TG_LISTENER = None

def start_telegram_listener():
    global TG_LISTENER
    try:
        from telegram_bot import TelegramListener
        if TG_LISTENER is None or not TG_LISTENER.is_alive():
            TG_LISTENER = TelegramListener()
            TG_LISTENER.start()
    except Exception as e:
        logger.error(f"Gagal memulai Telegram Listener: {e}")


def start_engine_background():
    global WATCHERS, IS_ENGINE_RUNNING
    with ENGINE_LOCK:
        if IS_ENGINE_RUNNING:
            return True

        cfg = load_config()
        targets = [t for t in cfg.get("targets", []) if t.get("enabled", True)]
        output_dir = cfg.get("output_directory", "recordings")
        interval = cfg.get("check_interval_seconds", 30)

        logger.info(f"🚀 Memulai Web Auto-Recorder ({len(targets)} target aktif)")

        WATCHERS = []
        for t in targets:
            w = TargetWatcher(
                platform=t.get("platform", "tiktok"),
                target=t.get("username"),
                output_dir=output_dir,
                check_interval=interval,
                quality=t.get("quality", "hd")
            )
            w.start()
            WATCHERS.append(w)

        IS_ENGINE_RUNNING = True
        start_telegram_listener()
        return True


def stop_engine_background():
    global WATCHERS, IS_ENGINE_RUNNING
    with ENGINE_LOCK:
        if not IS_ENGINE_RUNNING:
            return True

        logger.info("🛑 Menghentikan semua pemantauan bot...")
        for w in WATCHERS:
            w.stop()
        WATCHERS = []
        IS_ENGINE_RUNNING = False
        return True


def restart_engine_if_running():
    global IS_ENGINE_RUNNING
    if IS_ENGINE_RUNNING:
        stop_engine_background()
        start_engine_background()


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="id" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>LiveStream Auto Recorder Dashboard</title>
  <link rel="icon" type="image/svg+xml" href="/favicon.ico">
  <script>
    // Sembunyikan notifikasi production Tailwind di console
    const _origWarn = console.warn;
    console.warn = function(...args) {
      if (args[0] && typeof args[0] === 'string' && args[0].includes('tailwindcss.com should not be used in production')) return;
      _origWarn.apply(console, args);
    };
  </script>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          colors: {
            brand: {
              50: '#fff1f2',
              500: '#f43f5e',
              600: '#e11d48',
              700: '#be123c',
            }
          }
        }
      }
    }
  </script>
  <style>
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: #18181b; }
    ::-webkit-scrollbar-thumb { background: #3f3f46; border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: #52525b; }
    .pulse-dot { animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .3; } }
  </style>
</head>
<body class="bg-zinc-950 text-zinc-100 min-h-screen font-sans antialiased pb-16">

  <!-- Top Navigation -->
  <header class="border-b border-zinc-800 bg-zinc-900/80 backdrop-blur sticky top-0 z-40">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
      <div class="flex items-center space-x-3">
        <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-rose-600 to-amber-500 flex items-center justify-center shadow-lg shadow-rose-900/30">
          <i class="fa-solid fa-video text-white text-lg"></i>
        </div>
        <div>
          <h1 class="font-bold text-lg leading-tight flex items-center gap-2">
            Auto Live Recorder
            <span class="text-[11px] px-2 py-0.5 rounded-full bg-rose-500/10 text-rose-400 border border-rose-500/20 font-semibold">v2.1 Pro</span>
          </h1>
          <p class="text-xs text-zinc-400">TikTok, Band.us, YouTube, Twitch, Kick</p>
        </div>
      </div>

      <!-- Quick Actions -->
      <div class="flex items-center space-x-3">
        <a href="https://drive.google.com/drive/folders/{{ gdrive_folder_id }}" target="_blank" class="text-xs px-3 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 flex items-center gap-2 transition">
          <i class="fa-brands fa-google-drive text-amber-400 text-sm"></i>
          <span class="hidden sm:inline">Google Drive</span>
        </a>
        <button id="btn-toggle-engine" onclick="toggleEngine()" class="text-xs font-semibold px-4 py-2 rounded-lg transition flex items-center gap-2 shadow-md">
          <i class="fa-solid fa-power-off"></i>
          <span id="engine-btn-text">Memuat...</span>
        </button>
      </div>
    </div>
  </header>

  <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-8 space-y-8">

    <!-- Status Cards Grid -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <!-- Engine Status -->
      <div class="p-5 rounded-2xl bg-zinc-900/60 border border-zinc-800/80 shadow-sm flex items-center justify-between">
        <div>
          <p class="text-xs font-medium text-zinc-400 uppercase tracking-wider">Status Pemantauan</p>
          <div class="flex items-center gap-2 mt-1">
            <span id="badge-engine" class="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-0.5 rounded-full bg-zinc-800 text-zinc-400">
              <span class="w-2 h-2 rounded-full bg-zinc-500"></span> Memuat...
            </span>
          </div>
        </div>
        <div class="w-12 h-12 rounded-xl bg-zinc-800/70 flex items-center justify-center text-zinc-300 text-lg">
          <i class="fa-solid fa-satellite-dish"></i>
        </div>
      </div>

      <!-- VPS Disk & RAM Health -->
      <div class="p-5 rounded-2xl bg-zinc-900/60 border border-zinc-800/80 shadow-sm flex items-center justify-between">
        <div class="min-w-0 pr-2">
          <p class="text-xs font-medium text-zinc-400 uppercase tracking-wider">Kapasitas SSD VPS</p>
          <div class="flex items-baseline gap-1.5 mt-1">
            <p id="stat-disk-free" class="text-xl font-bold text-white">-- GB</p>
            <span class="text-xs text-zinc-400">tersisa</span>
          </div>
          <div class="w-28 bg-zinc-800 rounded-full h-1.5 mt-1.5 overflow-hidden">
            <div id="stat-disk-bar" class="bg-emerald-500 h-1.5 rounded-full transition-all duration-500" style="width: 0%"></div>
          </div>
        </div>
        <div class="w-12 h-12 rounded-xl bg-zinc-800/70 flex items-center justify-center text-emerald-400 text-lg shrink-0">
          <i class="fa-solid fa-server"></i>
        </div>
      </div>

      <!-- Currently Active Live -->
      <div class="p-5 rounded-2xl bg-zinc-900/60 border border-zinc-800/80 shadow-sm flex items-center justify-between">
        <div>
          <p class="text-xs font-medium text-zinc-400 uppercase tracking-wider">Sedang Direkam</p>
          <p id="stat-recording-now" class="text-2xl font-bold mt-1 text-rose-500">0</p>
        </div>
        <div class="w-12 h-12 rounded-xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400 text-lg">
          <i class="fa-solid fa-record-vinyl animate-spin" style="animation-duration: 4s;"></i>
        </div>
      </div>

      <!-- Target Count -->
      <div class="p-5 rounded-2xl bg-zinc-900/60 border border-zinc-800/80 shadow-sm flex items-center justify-between">
        <div>
          <p class="text-xs font-medium text-zinc-400 uppercase tracking-wider">Target Akun</p>
          <p id="stat-total-targets" class="text-2xl font-bold mt-1 text-white">0</p>
        </div>
        <div class="w-12 h-12 rounded-xl bg-zinc-800/70 flex items-center justify-center text-zinc-300 text-lg">
          <i class="fa-solid fa-users"></i>
        </div>
      </div>
    </div>

    <!-- Main Content Grid -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">

      <!-- Left Column: Target List (2 Cols) -->
      <div class="lg:col-span-2 space-y-6">
        
        <!-- Header & Add Form Toggle -->
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-zinc-900/70 p-5 rounded-2xl border border-zinc-800">
          <div>
            <h2 class="text-base font-bold text-white flex items-center gap-2">
              <i class="fa-solid fa-list-check text-rose-500"></i>
              Daftar Target Pemantauan
            </h2>
            <p class="text-xs text-zinc-400 mt-0.5">Merekam otomatis begitu live & upload bertahap ke Google Drive.</p>
          </div>
          <button onclick="document.getElementById('add-modal').classList.toggle('hidden')" class="px-4 py-2 bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold rounded-xl flex items-center gap-2 shadow-lg shadow-rose-900/20 transition self-start sm:self-auto">
            <i class="fa-solid fa-plus"></i> Tambah Akun Target
          </button>
        </div>

        <!-- Add Target Modal -->
        <div id="add-modal" class="hidden bg-zinc-900 p-6 rounded-2xl border border-zinc-700 shadow-xl space-y-4">
          <div class="flex items-center justify-between border-b border-zinc-800 pb-3">
            <h3 class="font-bold text-sm text-zinc-200 flex items-center gap-2">
              <i class="fa-solid fa-user-plus text-rose-400"></i> Tambah Target Baru
            </h3>
            <button onclick="document.getElementById('add-modal').classList.add('hidden')" class="text-zinc-400 hover:text-white">
              <i class="fa-solid fa-xmark"></i>
            </button>
          </div>

          <form id="form-add-target" onsubmit="addTarget(event)" class="space-y-4">
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label class="block text-xs font-medium text-zinc-400 mb-1">Platform</label>
                <select id="input-platform" class="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:ring-2 focus:ring-rose-500">
                  <option value="tiktok">TikTok Live</option>
                  <option value="band">Band.us Live</option>
                  <option value="youtube">YouTube Live</option>
                  <option value="twitch">Twitch</option>
                  <option value="kick">Kick</option>
                  <option value="custom">URL Streaming Bebas</option>
                </select>
              </div>
              <div>
                <label class="block text-xs font-medium text-zinc-400 mb-1">Kualitas Video</label>
                <select id="input-quality" class="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:ring-2 focus:ring-rose-500">
                  <option value="hd">HD 720p/1080p (Standar)</option>
                  <option value="origin">Origin (Kualitas Asli)</option>
                  <option value="sd">SD 480p (Hemat Kuota)</option>
                  <option value="audio_only">Hanya Audio (MP3/Podcast)</option>
                </select>
              </div>
              <div>
                <label class="block text-xs font-medium text-zinc-400 mb-1">Username / Link</label>
                <input type="text" id="input-username" required placeholder="@akun atau URL band" class="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-3 py-2 text-sm text-zinc-100 focus:outline-none focus:ring-2 focus:ring-rose-500">
              </div>
            </div>

            <div class="flex justify-end space-x-2 pt-2">
              <button type="button" onclick="document.getElementById('add-modal').classList.add('hidden')" class="px-4 py-2 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs font-medium">Batal</button>
              <button type="submit" class="px-5 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold flex items-center gap-1.5">
                <i class="fa-solid fa-check"></i> Simpan Target
              </button>
            </div>
          </form>
        </div>

        <!-- Targets Cards List -->
        <div id="targets-container" class="space-y-3">
          <div class="p-8 text-center text-zinc-500 text-sm">
            <i class="fa-solid fa-circle-notch animate-spin text-xl mb-2"></i>
            <p>Memuat daftar target...</p>
          </div>
        </div>

        <!-- Video Player & Local Gallery -->
        <div class="bg-zinc-900/70 p-5 rounded-2xl border border-zinc-800 space-y-4">
          <div class="flex items-center justify-between">
            <div>
              <h3 class="text-sm font-bold text-white flex items-center gap-2">
                <i class="fa-solid fa-film text-amber-400"></i>
                Pemutar Video & Rekaman Lokal
              </h3>
              <p class="text-xs text-zinc-400">Format nama: [Platform] Nama - Tanggal Jam WIB</p>
            </div>
            <button onclick="loadRecordings()" class="text-xs px-2.5 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition flex items-center gap-1">
              <i class="fa-solid fa-rotate-right"></i> Refresh
            </button>
          </div>

          <div id="recordings-container" class="space-y-2 max-h-60 overflow-y-auto">
            <p class="text-xs text-zinc-500 italic p-3 text-center">Memuat daftar file...</p>
          </div>
        </div>

      </div>

      <!-- Right Column: Live Console & Storage Info -->
      <div class="space-y-6">

        <!-- Real-Time Activity Log Console -->
        <div class="bg-zinc-900/70 rounded-2xl border border-zinc-800 overflow-hidden flex flex-col h-96">
          <div class="px-4 py-3 bg-zinc-900 border-b border-zinc-800 flex items-center justify-between">
            <div class="flex items-center space-x-2">
              <span class="w-2.5 h-2.5 rounded-full bg-emerald-500 pulse-dot"></span>
              <h3 class="text-xs font-bold text-zinc-200 uppercase tracking-wider">Aktivitas Bot (Live Logs)</h3>
            </div>
            <button onclick="clearLogs()" class="text-xs text-zinc-400 hover:text-white" title="Bersihkan tampilan">
              <i class="fa-solid fa-trash-can"></i>
            </button>
          </div>
          <div id="log-console" class="p-4 font-mono text-xs text-zinc-300 flex-1 overflow-y-auto space-y-1.5 leading-relaxed bg-zinc-950/70">
            <p class="text-zinc-500 italic">Menghubungkan ke log recorder...</p>
          </div>
        </div>

        <!-- Google Drive & Segment Info -->
        <div class="p-5 rounded-2xl bg-zinc-900/60 border border-zinc-800 space-y-3">
          <div class="flex items-center gap-3">
            <div class="w-9 h-9 rounded-lg bg-amber-500/10 text-amber-400 flex items-center justify-center">
              <i class="fa-solid fa-cloud-arrow-up"></i>
            </div>
            <div>
              <h4 class="text-xs font-bold text-zinc-200">Auto Sync Google Drive</h4>
              <p class="text-xs text-zinc-400">Segmen per jam langsung ter-upload</p>
            </div>
          </div>
          <div class="p-3 rounded-xl bg-zinc-950 border border-zinc-800 text-xs text-zinc-400 break-all flex items-center justify-between gap-2">
            <span class="truncate font-mono text-[11px] text-zinc-300">Folder ID: {{ gdrive_folder_id }}</span>
            <a href="https://drive.google.com/drive/folders/{{ gdrive_folder_id }}" target="_blank" class="text-rose-400 hover:underline shrink-0 font-medium">Buka Drive</a>
          </div>
        </div>

      </div>

    </div>

  </main>

  <!-- Video Player Modal -->
  <div id="video-modal" class="hidden fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
    <div class="bg-zinc-900 border border-zinc-700 rounded-2xl max-w-3xl w-full p-4 space-y-3 shadow-2xl">
      <div class="flex items-center justify-between border-b border-zinc-800 pb-2">
        <h4 id="video-modal-title" class="font-bold text-xs text-zinc-200 truncate">Memutar Video</h4>
        <button onclick="closeVideoModal()" class="text-zinc-400 hover:text-white text-sm">
          <i class="fa-solid fa-xmark"></i>
        </button>
      </div>
      <div class="aspect-video bg-black rounded-xl overflow-hidden flex items-center justify-center relative">
        <video id="player-element" controls class="w-full h-full object-contain" onerror="onPlayerError()"></video>
        <div id="player-error-msg" class="hidden absolute inset-0 bg-zinc-950/90 flex flex-col items-center justify-center p-4 text-center space-y-2">
          <i class="fa-solid fa-triangle-exclamation text-amber-400 text-2xl"></i>
          <p class="text-xs font-semibold text-zinc-200">Video Sedang Aktif Ditulis / Diunggah</p>
          <p class="text-[11px] text-zinc-400 max-w-sm">File ini baru saja mulai direkam dan header video sedang difinalisasi oleh server. Tunggu 10-20 detik lalu refresh atau tonton langsung di Google Drive.</p>
        </div>
      </div>
      <div class="flex justify-end">
        <button onclick="closeVideoModal()" class="px-4 py-1.5 rounded-lg bg-zinc-800 text-xs text-zinc-300 hover:bg-zinc-700">Tutup</button>
      </div>
    </div>
  </div>

  <!-- Notification Toast -->
  <div id="toast" class="fixed bottom-5 right-5 z-50 transform translate-y-20 opacity-0 transition-all duration-300 px-4 py-3 rounded-xl shadow-2xl flex items-center gap-2 text-xs font-semibold"></div>

  <script>
    let isRunning = false;

    function showToast(msg, isError = false) {
      const toast = document.getElementById('toast');
      toast.className = `fixed bottom-5 right-5 z-50 transform translate-y-0 opacity-100 transition-all duration-300 px-4 py-3 rounded-xl shadow-2xl flex items-center gap-2 text-xs font-semibold ${
        isError ? 'bg-rose-600 text-white' : 'bg-emerald-600 text-white'
      }`;
      toast.innerHTML = `<i class="fa-solid ${isError ? 'fa-circle-exclamation' : 'fa-circle-check'}"></i> ${msg}`;
      setTimeout(() => {
        toast.className = 'fixed bottom-5 right-5 z-50 transform translate-y-20 opacity-0 transition-all duration-300 px-4 py-3 rounded-xl shadow-2xl flex items-center gap-2 text-xs font-semibold';
      }, 3000);
    }

    async function refreshStatus() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();

        isRunning = data.bot_running;

        const btn = document.getElementById('btn-toggle-engine');
        const btnText = document.getElementById('engine-btn-text');
        const badge = document.getElementById('badge-engine');

        if (isRunning) {
          btn.className = "text-xs font-semibold px-4 py-2 rounded-xl bg-rose-600/20 text-rose-400 border border-rose-500/30 hover:bg-rose-600 hover:text-white transition flex items-center gap-2 shadow-md";
          btnText.innerText = "Hentikan Bot";
          badge.className = "inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20";
          badge.innerHTML = `<span class="w-2 h-2 rounded-full bg-emerald-400 pulse-dot"></span> Aktif Memantau`;
        } else {
          btn.className = "text-xs font-semibold px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white transition flex items-center gap-2 shadow-md shadow-emerald-900/20";
          btnText.innerText = "Mulai Bot";
          badge.className = "inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-0.5 rounded-full bg-zinc-800 text-zinc-400 border border-zinc-700";
          badge.innerHTML = `<span class="w-2 h-2 rounded-full bg-zinc-500"></span> Berhenti`;
        }

        document.getElementById('stat-total-targets').innerText = data.targets.length;
        document.getElementById('stat-recording-now').innerText = data.recording_now || 0;

        renderTargets(data.targets);

      } catch (err) {
        console.error("Gagal load status:", err);
      }
    }

    async function refreshHealth() {
      try {
        const res = await fetch('/api/health');
        const h = await res.json();
        document.getElementById('stat-disk-free').innerText = `${h.disk_free_gb} GB`;
        const bar = document.getElementById('stat-disk-bar');
        bar.style.width = `${h.disk_pct}%`;
        if (h.disk_pct > 85) bar.className = 'bg-rose-500 h-1.5 rounded-full';
        else if (h.disk_pct > 70) bar.className = 'bg-amber-500 h-1.5 rounded-full';
        else bar.className = 'bg-emerald-500 h-1.5 rounded-full';
      } catch (e) {}
    }

    function renderTargets(targets) {
      const container = document.getElementById('targets-container');
      if (!targets || targets.length === 0) {
        container.innerHTML = `
          <div class="p-8 text-center bg-zinc-900/40 rounded-2xl border border-dashed border-zinc-800 text-zinc-400 space-y-2">
            <i class="fa-solid fa-user-slash text-2xl text-zinc-600"></i>
            <p class="text-sm">Belum ada akun target yang dipantau.</p>
            <p class="text-xs text-zinc-500">Klik tombol "Tambah Akun Target" di atas untuk menambahkan.</p>
          </div>
        `;
        return;
      }

      const platformIcons = {
        tiktok: { icon: 'fa-tiktok', color: 'text-pink-400 bg-pink-500/10 border-pink-500/20' },
        band: { icon: 'fa-users-rectangle', color: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20' },
        youtube: { icon: 'fa-youtube', color: 'text-red-400 bg-red-500/10 border-red-500/20' },
        twitch: { icon: 'fa-twitch', color: 'text-purple-400 bg-purple-500/10 border-purple-500/20' },
        kick: { icon: 'fa-bolt', color: 'text-green-400 bg-green-500/10 border-green-500/20' },
        custom: { icon: 'fa-globe', color: 'text-blue-400 bg-blue-500/10 border-blue-500/20' }
      };

      container.innerHTML = targets.map((t) => {
        const plat = (t.platform || 'tiktok').toLowerCase();
        const pInfo = platformIcons[plat] || platformIcons.custom;
        const isLive = t.is_live;
        const qual = (t.quality || 'hd').toUpperCase();

        return `
          <div class="p-4 rounded-2xl bg-zinc-900/60 border ${isLive ? 'border-rose-500 shadow-lg shadow-rose-950/40' : 'border-zinc-800/80'} hover:border-zinc-700 transition flex items-center justify-between gap-4">
            <div class="flex items-center space-x-3.5 min-w-0">
              <div class="w-11 h-11 rounded-xl border ${pInfo.color} flex items-center justify-center shrink-0 text-base">
                <i class="fa-brands ${pInfo.icon}"></i>
              </div>
              <div class="min-w-0">
                <div class="flex items-center gap-2">
                  <h4 class="font-bold text-sm text-white truncate">${t.username}</h4>
                  <span class="text-[10px] uppercase font-bold px-2 py-0.5 rounded-full ${pInfo.color}">
                    ${plat}
                  </span>
                  <span class="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 border border-zinc-700">
                    ${qual}
                  </span>
                </div>
                <div class="flex items-center gap-2 mt-1">
                  ${isLive ? `
                    <span class="inline-flex items-center gap-1 text-[11px] font-bold text-rose-400">
                      <span class="w-2 h-2 rounded-full bg-rose-500 pulse-dot"></span> SEDANG LIVE & DIREKAM
                    </span>
                  ` : `
                    <span class="text-xs text-zinc-400 flex items-center gap-1">
                      <span class="w-1.5 h-1.5 rounded-full ${t.enabled ? 'bg-zinc-500' : 'bg-zinc-700'}"></span>
                      ${t.enabled ? 'Standby (Offline)' : 'Dinonaktifkan'}
                    </span>
                  `}
                </div>
              </div>
            </div>

            <div class="flex items-center space-x-2 shrink-0">
              <button onclick="toggleTarget('${t.username}', '${plat}')" title="${t.enabled ? 'Nonaktifkan' : 'Aktifkan'}" class="w-8 h-8 rounded-lg ${t.enabled ? 'bg-zinc-800 text-zinc-300 hover:text-white' : 'bg-zinc-800 text-zinc-600 hover:text-zinc-400'} flex items-center justify-center text-xs transition">
                <i class="fa-solid ${t.enabled ? 'fa-toggle-on text-emerald-400 text-sm' : 'fa-toggle-off'}"></i>
              </button>
              <button onclick="deleteTarget('${t.username}', '${plat}')" title="Hapus Target" class="w-8 h-8 rounded-lg bg-zinc-800/70 hover:bg-rose-900/30 text-zinc-400 hover:text-rose-400 flex items-center justify-center text-xs transition">
                <i class="fa-solid fa-trash"></i>
              </button>
            </div>
          </div>
        `;
      }).join('');
    }

    async function toggleEngine() {
      const endpoint = isRunning ? '/api/bot/stop' : '/api/bot/start';
      try {
        const res = await fetch(endpoint, { method: 'POST' });
        const data = await res.json();
        showToast(data.message, !data.success);
        refreshStatus();
      } catch (err) {
        showToast("Gagal mengubah status bot", true);
      }
    }

    async function addTarget(e) {
      e.preventDefault();
      const platform = document.getElementById('input-platform').value;
      const username = document.getElementById('input-username').value.trim();
      const quality = document.getElementById('input-quality').value;

      if (!username) return;

      try {
        const res = await fetch('/api/target/add', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ platform, username, quality })
        });
        const data = await res.json();
        if (data.success) {
          showToast(data.message);
          document.getElementById('input-username').value = '';
          document.getElementById('add-modal').classList.add('hidden');
          refreshStatus();
        } else {
          showToast(data.message, true);
        }
      } catch (err) {
        showToast("Gagal menambahkan target", true);
      }
    }

    async function deleteTarget(username, platform) {
      if (!confirm(`Hapus target ${username}?`)) return;
      try {
        const res = await fetch('/api/target/delete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, platform })
        });
        const data = await res.json();
        showToast(data.message);
        refreshStatus();
      } catch (err) {
        showToast("Gagal menghapus target", true);
      }
    }

    async function toggleTarget(username, platform) {
      try {
        const res = await fetch('/api/target/toggle', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, platform })
        });
        const data = await res.json();
        showToast(data.message);
        refreshStatus();
      } catch (err) {
        showToast("Gagal mengubah status target", true);
      }
    }

    async function loadRecordings() {
      const c = document.getElementById('recordings-container');
      try {
        const res = await fetch('/api/recordings');
        const data = await res.json();
        if (!data.recordings || data.recordings.length === 0) {
          c.innerHTML = '<p class="text-xs text-zinc-500 italic p-3 text-center">Belum ada rekaman lokal (file langsung otomatis diunggah ke Google Drive).</p>';
          return;
        }

        c.innerHTML = data.recordings.map(r => `
          <div class="p-2.5 rounded-xl bg-zinc-950 border border-zinc-800/80 flex items-center justify-between text-xs">
            <div class="min-w-0 pr-3">
              <p class="font-medium text-zinc-200 truncate" title="${r.name}">${r.name}</p>
              <p class="text-[10px] text-zinc-500">${r.size_mb} MB • ${r.mtime}</p>
            </div>
            <div class="flex items-center space-x-2 shrink-0">
              <button onclick="playVideo('${r.url}', '${r.name}')" class="px-2.5 py-1 rounded bg-rose-600/20 text-rose-400 hover:bg-rose-600 hover:text-white transition flex items-center gap-1">
                <i class="fa-solid fa-play text-[10px]"></i> Putar
              </button>
              <a href="${r.url}" download class="w-6 h-6 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-400 flex items-center justify-center">
                <i class="fa-solid fa-download text-[10px]"></i>
              </a>
            </div>
          </div>
        `).join('');
      } catch (e) {
        c.innerHTML = '<p class="text-xs text-rose-400 p-2 text-center">Gagal memuat rekaman.</p>';
      }
    }

    function playVideo(url, name) {
      document.getElementById('video-modal-title').innerText = name;
      const player = document.getElementById('player-element');
      const errBox = document.getElementById('player-error-msg');
      if (errBox) errBox.classList.add('hidden');
      player.classList.remove('hidden');

      player.pause();
      player.src = url;
      player.load();
      document.getElementById('video-modal').classList.remove('hidden');
      
      player.play().catch(err => {
        console.log("Playback info:", err);
      });
    }

    function onPlayerError() {
      document.getElementById('player-element').classList.add('hidden');
      const errBox = document.getElementById('player-error-msg');
      if (errBox) errBox.classList.remove('hidden');
    }

    function closeVideoModal() {
      const player = document.getElementById('player-element');
      player.pause();
      player.removeAttribute('src');
      player.load();
      document.getElementById('video-modal').classList.add('hidden');
    }

    async function fetchLogs() {
      try {
        const res = await fetch('/api/logs');
        const data = await res.json();
        const consoleEl = document.getElementById('log-console');

        if (data.logs && data.logs.length > 0) {
          consoleEl.innerHTML = data.logs.map(line => {
            let color = 'text-zinc-300';
            if (line.includes('LIVE TERDETEKSI')) color = 'text-rose-400 font-bold';
            else if (line.includes('Sukses') || line.includes('ter-upload')) color = 'text-emerald-400 font-medium';
            else if (line.includes('WARNING') || line.includes('Error')) color = 'text-amber-400';
            return `<div class="${color}">${escapeHtml(line)}</div>`;
          }).join('');
          consoleEl.scrollTop = consoleEl.scrollHeight;
        }
      } catch (e) {}
    }

    function clearLogs() {
      document.getElementById('log-console').innerHTML = '<p class="text-zinc-500 italic">Log dibersihkan.</p>';
    }

    function escapeHtml(text) {
      return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    refreshStatus();
    refreshHealth();
    loadRecordings();
    fetchLogs();
    setInterval(refreshStatus, 4000);
    setInterval(refreshHealth, 10000);
    setInterval(fetchLogs, 2500);
  </script>
</body>
</html>
"""

@app.route("/")
def index():
    cfg = load_config()
    gdrive_folder_id = cfg.get("google_drive_rclone", {}).get("folder_id", "1jv4Di6t7ceemzIljL641y5zSKD9oNq03")
    return render_template_string(HTML_TEMPLATE, gdrive_folder_id=gdrive_folder_id)


@app.route("/favicon.ico")
def favicon():
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="45" fill="#f43f5e"/><polygon points="40,30 70,50 40,70" fill="white"/></svg>'
    return (svg, 200, {'Content-Type': 'image/svg+xml'})


@app.route("/api/health")
def api_health():
    return jsonify(get_vps_health())


@app.route("/recordings/<path:filename>")
def stream_recording(filename):
    cfg = load_config()
    out_dir = os.path.abspath(cfg.get("output_directory", "recordings"))
    full_path = os.path.join(out_dir, filename)
    if not os.path.exists(full_path):
        abort(404)
    if os.path.getsize(full_path) < 1000:
        return "File video masih dalam inisialisasi awal. Mohon tunggu beberapa detik.", 202
    return send_from_directory(out_dir, filename, mimetype="video/mp4", as_attachment=False)


@app.route("/api/recordings")
def api_recordings():
    cfg = load_config()
    out_dir = os.path.abspath(cfg.get("output_directory", "recordings"))
    if not os.path.exists(out_dir):
        return jsonify({"recordings": []})

    files = []
    for f in os.listdir(out_dir):
        if f.endswith(".mp4") or f.endswith(".ts"):
            fp = os.path.join(out_dir, f)
            try:
                st = os.stat(fp)
                files.append({
                    "name": f,
                    "size_mb": round(st.st_size / (1024 * 1024), 2),
                    "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M"),
                    "url": f"/recordings/{f}"
                })
            except Exception:
                pass
    files.sort(key=lambda x: x["mtime"], reverse=True)
    return jsonify({"recordings": files})


@app.route("/api/status")
def api_status():
    cfg = load_config()
    targets = cfg.get("targets", [])

    enriched_targets = []
    recording_count = 0
    for t in targets:
        plat = t.get("platform", "tiktok").lower()
        user = t.get("username", "").lower().lstrip("@")
        status_key = f"{plat}_{user}"
        is_live = ACTIVE_STATUS.get(status_key, False)
        if is_live:
            recording_count += 1

        enriched_targets.append({
            "platform": t.get("platform", "tiktok"),
            "username": t.get("username"),
            "quality": t.get("quality", "hd"),
            "enabled": t.get("enabled", True),
            "is_live": is_live
        })

    return jsonify({
        "bot_running": IS_ENGINE_RUNNING,
        "recording_now": recording_count,
        "targets": enriched_targets,
        "check_interval": cfg.get("check_interval_seconds", 30)
    })


@app.route("/api/logs")
def api_logs():
    return jsonify({
        "logs": list(LOG_BUFFER)
    })


@app.route("/api/bot/start", methods=["POST"])
def api_bot_start():
    start_engine_background()
    return jsonify({"success": True, "message": "Bot perekam berhasil dijalankan!"})


@app.route("/api/bot/stop", methods=["POST"])
def api_bot_stop():
    stop_engine_background()
    return jsonify({"success": True, "message": "Bot pemantau dihentikan."})


@app.route("/api/target/add", methods=["POST"])
def api_target_add():
    data = request.json or {}
    platform = data.get("platform", "tiktok").strip().lower()
    username = data.get("username", "").strip()
    quality = data.get("quality", "hd").strip().lower()

    if not username:
        return jsonify({"success": False, "message": "Username tidak boleh kosong"}), 400

    cfg = load_config()
    cfg.setdefault("targets", [])

    clean_user = username.lower().lstrip("@")
    for t in cfg["targets"]:
        if t.get("username", "").lower().lstrip("@") == clean_user and t.get("platform", "").lower() == platform:
            return jsonify({"success": False, "message": "Target sudah ada di daftar"}), 400

    cfg["targets"].append({
        "platform": platform,
        "username": username,
        "quality": quality,
        "enabled": True
    })
    save_config(cfg)
    logger.info(f"➕ Menambahkan target baru: [{platform.upper()}] {username} ({quality.upper()})")

    restart_engine_if_running()
    return jsonify({"success": True, "message": f"Target [{platform.upper()}] {username} ({quality.upper()}) berhasil ditambahkan!"})


@app.route("/api/target/toggle", methods=["POST"])
def api_target_toggle():
    data = request.json or {}
    platform = data.get("platform", "").strip().lower()
    username = data.get("username", "").strip()

    cfg = load_config()
    for t in cfg.get("targets", []):
        if t.get("username") == username and t.get("platform", "").lower() == platform:
            t["enabled"] = not t.get("enabled", True)
            save_config(cfg)
            state = "diaktifkan" if t["enabled"] else "dinonaktifkan"
            logger.info(f"Target [{platform.upper()}] {username} {state}.")
            restart_engine_if_running()
            return jsonify({"success": True, "message": f"Target {username} {state}."})

    return jsonify({"success": False, "message": "Target tidak ditemukan"}), 404


@app.route("/api/target/delete", methods=["POST"])
def api_target_delete():
    data = request.json or {}
    platform = data.get("platform", "").strip().lower()
    username = data.get("username", "").strip()

    cfg = load_config()
    targets = cfg.get("targets", [])
    new_targets = [t for t in targets if not (t.get("username") == username and t.get("platform", "").lower() == platform)]

    if len(new_targets) < len(targets):
        cfg["targets"] = new_targets
        save_config(cfg)
        logger.info(f"🗑️ Menghapus target: [{platform.upper()}] {username}")
        restart_engine_if_running()
        return jsonify({"success": True, "message": f"Target {username} berhasil dihapus."})

    return jsonify({"success": False, "message": "Target tidak ditemukan"}), 404


if __name__ == "__main__":
    start_engine_background()
    port = int(os.environ.get("PORT", 5000))
    print("=" * 60)
    print("  🌐 Auto Live Stream Recorder Web UI Berjalan!")
    print(f"  👉 Akses di Browser: http://72.60.79.72:{port}")
    print("=" * 60)
    app.run(host="0.0.0.0", port=port, debug=False)
