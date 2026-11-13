"""
Flask Web Dashboard untuk Auto Live Stream Recorder v2.2 Pro
Desain Modern, Responsif, Custom Dropdown & Video Stream Player
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
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>LiveStream Auto Recorder Pro</title>
  <link rel="icon" type="image/svg+xml" href="/favicon.ico">
  
  <!-- Modern Typography -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  
  <!-- Tailwind CSS & FontAwesome -->
  <script>
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
          fontFamily: {
            sans: ['"Plus Jakarta Sans"', 'sans-serif'],
            mono: ['"JetBrains Mono"', 'monospace'],
          },
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
    body { font-family: 'Plus Jakarta Sans', sans-serif; }
    ::-webkit-scrollbar { width: 5px; height: 5px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: #3f3f46; border-radius: 9999px; }
    ::-webkit-scrollbar-thumb:hover { background: #52525b; }
    .pulse-dot { animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .25; } }
    .glass-card { background: rgba(24, 24, 27, 0.65); backdrop-filter: blur(16px); }
    .glass-nav { background: rgba(9, 9, 11, 0.85); backdrop-filter: blur(20px); }
  </style>
</head>
<body class="bg-[#09090b] text-zinc-100 min-h-screen font-sans antialiased selection:bg-rose-500 selection:text-white pb-20">

  <!-- Glow Accents in Background -->
  <div class="fixed top-0 left-1/4 w-96 h-96 bg-rose-600/10 rounded-full blur-3xl pointer-events-none -z-10"></div>
  <div class="fixed bottom-0 right-1/4 w-96 h-96 bg-amber-500/5 rounded-full blur-3xl pointer-events-none -z-10"></div>

  <!-- Top Sticky Navigation -->
  <header class="border-b border-zinc-800/80 glass-nav sticky top-0 z-40 transition-all duration-200">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 sm:h-20 flex items-center justify-between">
      
      <!-- Brand Logo -->
      <div class="flex items-center space-x-3 sm:space-x-4">
        <div class="w-10 h-10 sm:w-12 sm:h-12 rounded-2xl bg-gradient-to-tr from-rose-600 via-rose-500 to-amber-500 flex items-center justify-center shadow-lg shadow-rose-900/40 shrink-0">
          <i class="fa-solid fa-video text-white text-base sm:text-lg"></i>
        </div>
        <div>
          <div class="flex items-center gap-2">
            <h1 class="font-extrabold text-base sm:text-lg tracking-tight text-white leading-none">Auto Recorder</h1>
            <span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-rose-500/15 text-rose-400 border border-rose-500/30 uppercase tracking-wider">v2.2 Pro</span>
          </div>
          <p class="text-[11px] sm:text-xs text-zinc-400 font-medium mt-1 truncate max-w-[200px] sm:max-w-none">Multi-Platform Cloud 24/7 Engine</p>
        </div>
      </div>

      <!-- Quick Action Buttons -->
      <div class="flex items-center space-x-2 sm:space-x-3">
        <a href="https://drive.google.com/drive/folders/{{ gdrive_folder_id }}" target="_blank" class="text-xs font-semibold px-3 sm:px-4 py-2 sm:py-2.5 rounded-xl bg-zinc-900/90 hover:bg-zinc-800 text-zinc-200 border border-zinc-800 flex items-center gap-2 transition shadow-sm hover:border-zinc-700">
          <i class="fa-brands fa-google-drive text-amber-400 text-sm"></i>
          <span class="hidden md:inline">Google Drive</span>
        </a>
        <button id="btn-toggle-engine" onclick="toggleEngine()" class="text-xs font-semibold px-3.5 sm:px-4 py-2 sm:py-2.5 rounded-xl transition flex items-center gap-2 shadow-md">
          <i class="fa-solid fa-power-off text-xs"></i>
          <span id="engine-btn-text">Memuat...</span>
        </button>
      </div>

    </div>
  </header>

  <main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-6 sm:pt-8 space-y-6 sm:space-y-8">

    <!-- Status Metric Cards (Fully Responsive Grid) -->
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
      
      <!-- Card 1: Bot State -->
      <div class="p-4 sm:p-5 rounded-2xl glass-card border border-zinc-800/80 shadow-sm flex flex-col justify-between hover:border-zinc-700 transition">
        <div class="flex items-center justify-between">
          <span class="text-[11px] sm:text-xs font-bold text-zinc-400 uppercase tracking-wider">Status Bot</span>
          <div class="w-8 h-8 rounded-xl bg-zinc-800/80 flex items-center justify-center text-zinc-300 text-xs">
            <i class="fa-solid fa-satellite-dish"></i>
          </div>
        </div>
        <div class="mt-3">
          <span id="badge-engine" class="inline-flex items-center gap-1.5 text-xs font-bold px-2.5 py-1 rounded-full bg-zinc-800 text-zinc-400 border border-zinc-700">
            <span class="w-2 h-2 rounded-full bg-zinc-500"></span> Memuat...
          </span>
        </div>
      </div>

      <!-- Card 2: Active Recordings -->
      <div class="p-4 sm:p-5 rounded-2xl glass-card border border-zinc-800/80 shadow-sm flex flex-col justify-between hover:border-zinc-700 transition">
        <div class="flex items-center justify-between">
          <span class="text-[11px] sm:text-xs font-bold text-zinc-400 uppercase tracking-wider">Sedang Direkam</span>
          <div class="w-8 h-8 rounded-xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400 text-xs">
            <i class="fa-solid fa-record-vinyl animate-spin" style="animation-duration: 4s;"></i>
          </div>
        </div>
        <div class="mt-2 flex items-baseline gap-2">
          <p id="stat-recording-now" class="text-2xl sm:text-3xl font-extrabold text-rose-500 tracking-tight">0</p>
          <span class="text-xs text-zinc-400 font-medium">live aktif</span>
        </div>
      </div>

      <!-- Card 3: Storage VPS -->
      <div class="p-4 sm:p-5 rounded-2xl glass-card border border-zinc-800/80 shadow-sm flex flex-col justify-between hover:border-zinc-700 transition">
        <div class="flex items-center justify-between">
          <span class="text-[11px] sm:text-xs font-bold text-zinc-400 uppercase tracking-wider">Penyimpanan VPS</span>
          <div class="w-8 h-8 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 text-xs">
            <i class="fa-solid fa-server"></i>
          </div>
        </div>
        <div class="mt-2">
          <div class="flex items-baseline justify-between">
            <p id="stat-disk-free" class="text-xl sm:text-2xl font-extrabold text-white tracking-tight">-- GB</p>
            <span id="stat-disk-pct" class="text-[11px] font-bold text-emerald-400">0%</span>
          </div>
          <div class="w-full bg-zinc-800/80 rounded-full h-1.5 mt-2 overflow-hidden">
            <div id="stat-disk-bar" class="bg-emerald-500 h-1.5 rounded-full transition-all duration-700" style="width: 0%"></div>
          </div>
        </div>
      </div>

      <!-- Card 4: Targets Count -->
      <div class="p-4 sm:p-5 rounded-2xl glass-card border border-zinc-800/80 shadow-sm flex flex-col justify-between hover:border-zinc-700 transition">
        <div class="flex items-center justify-between">
          <span class="text-[11px] sm:text-xs font-bold text-zinc-400 uppercase tracking-wider">Total Target</span>
          <div class="w-8 h-8 rounded-xl bg-zinc-800/80 flex items-center justify-center text-zinc-300 text-xs">
            <i class="fa-solid fa-users"></i>
          </div>
        </div>
        <div class="mt-2 flex items-baseline gap-2">
          <p id="stat-total-targets" class="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">0</p>
          <span class="text-xs text-zinc-400 font-medium">akun terdaftar</span>
        </div>
      </div>

    </div>

    <!-- Main Workspace (Responsive 12-Column Grid) -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6 sm:gap-8 items-start">

      <!-- Left Column: Targets & Video Vault (7 Cols on desktop) -->
      <div class="lg:col-span-7 space-y-6 sm:space-y-8">
        
        <!-- Target Header & Add Trigger -->
        <div class="glass-card p-5 sm:p-6 rounded-3xl border border-zinc-800/80 shadow-md space-y-5">
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h2 class="text-base sm:text-lg font-bold text-white flex items-center gap-2.5">
                <span class="w-8 h-8 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400 flex items-center justify-center text-sm">
                  <i class="fa-solid fa-list-check"></i>
                </span>
                Target Pemantauan
              </h2>
              <p class="text-xs text-zinc-400 font-medium mt-1">Bot memantau 24/7 dan merekam begitu streamer online.</p>
            </div>
            
            <button onclick="openAddModal()" class="w-full sm:w-auto px-4 py-2.5 bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold rounded-xl flex items-center justify-center gap-2 shadow-lg shadow-rose-900/30 transition-all hover:scale-[1.02] active:scale-[0.98]">
              <i class="fa-solid fa-plus text-xs"></i> Tambah Akun Target
            </button>
          </div>

          <!-- Target Cards Container -->
          <div id="targets-container" class="space-y-3 pt-1">
            <div class="p-8 text-center text-zinc-500 text-xs font-medium">
              <i class="fa-solid fa-circle-notch animate-spin text-xl mb-2 text-rose-500"></i>
              <p>Menghubungkan ke pemantauan...</p>
            </div>
          </div>
        </div>

        <!-- Video Player & Local Recordings Vault -->
        <div class="glass-card p-5 sm:p-6 rounded-3xl border border-zinc-800/80 shadow-md space-y-4">
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-zinc-800/80 pb-4">
            <div>
              <h3 class="text-sm sm:text-base font-bold text-white flex items-center gap-2.5">
                <span class="w-8 h-8 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400 flex items-center justify-center text-sm">
                  <i class="fa-solid fa-film"></i>
                </span>
                Pemutar Video & Rekaman Lokal
              </h3>
              <p class="text-xs text-zinc-400 font-medium mt-1">Putar hasil rekaman langsung dari browser tanpa download.</p>
            </div>
            <div class="flex items-center gap-2">
              <input type="text" id="search-recordings" oninput="filterRecordings(this.value)" placeholder="Cari nama file..." class="bg-zinc-900/90 border border-zinc-800 rounded-xl px-3 py-1.5 text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-rose-500 w-36 sm:w-44 transition">
              <button onclick="loadRecordings()" class="w-8 h-8 rounded-xl bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border border-zinc-800 flex items-center justify-center transition" title="Refresh file">
                <i class="fa-solid fa-rotate-right text-xs"></i>
              </button>
            </div>
          </div>

          <!-- Video Files List -->
          <div id="recordings-container" class="space-y-2.5 max-h-80 overflow-y-auto pr-1">
            <p class="text-xs text-zinc-500 italic p-4 text-center">Memuat daftar rekaman...</p>
          </div>
        </div>

      </div>

      <!-- Right Column: Real-Time Console & Cloud Info (5 Cols on desktop) -->
      <div class="lg:col-span-5 space-y-6 sm:space-y-8">

        <!-- Sleek Live Terminal Console -->
        <div class="glass-card rounded-3xl border border-zinc-800/80 shadow-md overflow-hidden flex flex-col h-[460px]">
          <!-- macOS Terminal Header -->
          <div class="px-5 py-3.5 bg-zinc-900/90 border-b border-zinc-800/80 flex items-center justify-between">
            <div class="flex items-center space-x-2">
              <span class="w-3 h-3 rounded-full bg-rose-500/80 inline-block"></span>
              <span class="w-3 h-3 rounded-full bg-amber-500/80 inline-block"></span>
              <span class="w-3 h-3 rounded-full bg-emerald-500/80 inline-block"></span>
              <span class="text-xs font-bold text-zinc-300 ml-2 font-mono">live_engine.log</span>
            </div>
            <div class="flex items-center space-x-2">
              <span class="w-2 h-2 rounded-full bg-emerald-400 pulse-dot"></span>
              <button onclick="clearLogs()" class="text-zinc-500 hover:text-zinc-300 text-xs transition p-1" title="Bersihkan log">
                <i class="fa-solid fa-trash-can"></i>
              </button>
            </div>
          </div>

          <!-- Log Content Area -->
          <div id="log-console" class="p-4 sm:p-5 font-mono text-[11px] sm:text-xs text-zinc-300 flex-1 overflow-y-auto space-y-2 leading-relaxed bg-[#0c0c0e]">
            <p class="text-zinc-600 italic">Menghubungkan ke live logger stream...</p>
          </div>
        </div>

        <!-- Google Drive & Cloud Vault Info -->
        <div class="glass-card p-5 sm:p-6 rounded-3xl border border-zinc-800/80 shadow-md space-y-4">
          <div class="flex items-center gap-3.5">
            <div class="w-11 h-11 rounded-2xl bg-amber-500/10 border border-amber-500/20 text-amber-400 flex items-center justify-center text-lg shrink-0">
              <i class="fa-solid fa-cloud-arrow-up"></i>
            </div>
            <div class="min-w-0">
              <h4 class="text-sm font-bold text-white">Google Drive Rclone Cloud</h4>
              <p class="text-xs text-zinc-400 font-medium">Auto-upload per part (60 menit) tanpa delay.</p>
            </div>
          </div>
          <div class="p-3.5 rounded-2xl bg-zinc-900/80 border border-zinc-800/80 text-xs text-zinc-400 flex items-center justify-between gap-3">
            <span class="truncate font-mono text-[11px] text-zinc-300 font-medium">Folder ID: {{ gdrive_folder_id }}</span>
            <a href="https://drive.google.com/drive/folders/{{ gdrive_folder_id }}" target="_blank" class="px-3 py-1 rounded-xl bg-amber-500/15 text-amber-300 hover:bg-amber-500 hover:text-zinc-950 font-bold transition text-xs shrink-0 flex items-center gap-1.5">
              <span>Buka</span> <i class="fa-solid fa-arrow-up-right-from-square text-[10px]"></i>
            </a>
          </div>
        </div>

      </div>

    </div>

  </main>

  <!-- Custom Styled Modern Modal: Tambah Target Baru -->
  <div id="add-modal" class="hidden fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4 transition-all duration-300">
    <div class="bg-[#121215] border border-zinc-700/80 rounded-3xl max-w-lg w-full p-6 sm:p-7 space-y-6 shadow-2xl relative overflow-hidden animate-in fade-in zoom-in-95 duration-200">
      
      <!-- Modal Accent Glow -->
      <div class="absolute -top-16 -right-16 w-36 h-36 bg-rose-600/20 rounded-full blur-2xl pointer-events-none"></div>

      <!-- Header -->
      <div class="flex items-center justify-between border-b border-zinc-800/80 pb-4">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-2xl bg-rose-500/10 border border-rose-500/20 text-rose-400 flex items-center justify-center text-base">
            <i class="fa-solid fa-user-plus"></i>
          </div>
          <div>
            <h3 class="font-extrabold text-base text-white">Tambah Target Pemantauan</h3>
            <p class="text-xs text-zinc-400 font-medium">Pilih platform dan tentukan kualitas rekaman.</p>
          </div>
        </div>
        <button onclick="closeAddModal()" class="w-8 h-8 rounded-xl bg-zinc-800/70 hover:bg-zinc-700 text-zinc-400 hover:text-white flex items-center justify-center transition">
          <i class="fa-solid fa-xmark text-sm"></i>
        </button>
      </div>

      <!-- Form Inputs -->
      <form id="form-add-target" onsubmit="addTarget(event)" class="space-y-5">
        
        <!-- Custom Dropdown 1: Platform Selection -->
        <div>
          <label class="block text-xs font-bold text-zinc-300 mb-2 flex items-center gap-1.5">
            <i class="fa-solid fa-shapes text-rose-400 text-xs"></i> Platform Streaming
          </label>
          <div class="relative">
            <select id="input-platform" class="w-full bg-zinc-900/90 hover:bg-zinc-850 border border-zinc-700/90 focus:border-rose-500 rounded-2xl px-4 py-3 text-sm text-zinc-100 appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-rose-500/20 transition-all font-semibold pr-10 shadow-sm">
              <option value="tiktok" class="bg-zinc-900 py-2.5 text-zinc-100 font-medium">📱 TikTok Live (Otomatis & Tembus 18+)</option>
              <option value="band" class="bg-zinc-900 py-2.5 text-zinc-100 font-medium">👥 Band.us Live Stream</option>
              <option value="youtube" class="bg-zinc-900 py-2.5 text-zinc-100 font-medium">▶️ YouTube Live</option>
              <option value="twitch" class="bg-zinc-900 py-2.5 text-zinc-100 font-medium">🟣 Twitch TV</option>
              <option value="kick" class="bg-zinc-900 py-2.5 text-zinc-100 font-medium">⚡ Kick Live</option>
              <option value="custom" class="bg-zinc-900 py-2.5 text-zinc-100 font-medium">🌐 Custom / URL Bebas</option>
            </select>
            <div class="pointer-events-none absolute inset-y-0 right-0 flex items-center px-4 text-zinc-400">
              <i class="fa-solid fa-chevron-down text-xs"></i>
            </div>
          </div>
        </div>

        <!-- Custom Dropdown 2: Quality Selection -->
        <div>
          <label class="block text-xs font-bold text-zinc-300 mb-2 flex items-center gap-1.5">
            <i class="fa-solid fa-sliders text-amber-400 text-xs"></i> Kualitas Resolusi Video
          </label>
          <div class="relative">
            <select id="input-quality" class="w-full bg-zinc-900/90 hover:bg-zinc-850 border border-zinc-700/90 focus:border-rose-500 rounded-2xl px-4 py-3 text-sm text-zinc-100 appearance-none cursor-pointer focus:outline-none focus:ring-2 focus:ring-rose-500/20 transition-all font-semibold pr-10 shadow-sm">
              <option value="hd" class="bg-zinc-900 py-2.5 text-zinc-100 font-medium">✨ HD 720p / 1080p (Standar Kualitas Terbaik)</option>
              <option value="origin" class="bg-zinc-900 py-2.5 text-zinc-100 font-medium">💎 Origin (Kualitas Maksimal dari Streamer)</option>
              <option value="sd" class="bg-zinc-900 py-2.5 text-zinc-100 font-medium">⚡ SD 480p (Hemat Ruang Penyimpanan)</option>
              <option value="audio_only" class="bg-zinc-900 py-2.5 text-zinc-100 font-medium">🎙️ Hanya Audio (MP3 Podcast / Hemat 90% Storage)</option>
            </select>
            <div class="pointer-events-none absolute inset-y-0 right-0 flex items-center px-4 text-zinc-400">
              <i class="fa-solid fa-chevron-down text-xs"></i>
            </div>
          </div>
        </div>

        <!-- Input Username / Link -->
        <div>
          <label class="block text-xs font-bold text-zinc-300 mb-2 flex items-center gap-1.5">
            <i class="fa-solid fa-at text-rose-400 text-xs"></i> Username atau Link Channel
          </label>
          <input type="text" id="input-username" required placeholder="Contoh: @rrenerren29 atau URL channel" class="w-full bg-zinc-900/90 border border-zinc-700/90 focus:border-rose-500 rounded-2xl px-4 py-3 text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-rose-500/20 transition-all font-semibold shadow-sm">
        </div>

        <!-- Action Buttons -->
        <div class="flex items-center justify-end space-x-3 pt-3 border-t border-zinc-800/80">
          <button type="button" onclick="closeAddModal()" class="px-5 py-2.5 rounded-xl bg-zinc-850 hover:bg-zinc-800 text-zinc-300 text-xs font-bold transition">Batal</button>
          <button type="submit" class="px-6 py-2.5 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold flex items-center gap-2 shadow-lg shadow-rose-900/30 transition-all hover:scale-[1.02]">
            <i class="fa-solid fa-check text-xs"></i> Simpan Target
          </button>
        </div>

      </form>

    </div>
  </div>

  <!-- Custom Video Player Modal -->
  <div id="video-modal" class="hidden fixed inset-0 z-50 bg-black/85 backdrop-blur-md flex items-center justify-center p-3 sm:p-6 transition-all duration-300">
    <div class="bg-[#121215] border border-zinc-700/80 rounded-3xl max-w-4xl w-full p-4 sm:p-6 space-y-4 shadow-2xl relative overflow-hidden">
      
      <!-- Video Header -->
      <div class="flex items-center justify-between border-b border-zinc-800/80 pb-3">
        <div class="flex items-center space-x-3 min-w-0 pr-2">
          <span class="w-7 h-7 rounded-xl bg-rose-500/10 text-rose-400 flex items-center justify-center text-xs shrink-0">
            <i class="fa-solid fa-play"></i>
          </span>
          <h4 id="video-modal-title" class="font-extrabold text-xs sm:text-sm text-zinc-100 truncate">Memutar Video</h4>
        </div>
        <button onclick="closeVideoModal()" class="w-8 h-8 rounded-xl bg-zinc-850 hover:bg-zinc-750 text-zinc-400 hover:text-white flex items-center justify-center transition shrink-0">
          <i class="fa-solid fa-xmark text-sm"></i>
        </button>
      </div>

      <!-- Player Frame -->
      <div class="aspect-video bg-black rounded-2xl overflow-hidden flex items-center justify-center relative border border-zinc-800">
        <video id="player-element" controls preload="metadata" class="w-full h-full object-contain" onerror="onPlayerError()"></video>
        
        <!-- Helpful notice if stream is still being written -->
        <div id="player-error-msg" class="hidden absolute inset-0 bg-zinc-950/95 flex flex-col items-center justify-center p-6 text-center space-y-3">
          <div class="w-12 h-12 rounded-2xl bg-amber-500/10 border border-amber-500/20 text-amber-400 flex items-center justify-center text-xl">
            <i class="fa-solid fa-clock-rotate-left"></i>
          </div>
          <h5 class="text-sm font-bold text-white">Video Sedang Diinisialisasi / Ditulis</h5>
          <p class="text-xs text-zinc-400 max-w-md leading-relaxed">
            File rekaman ini baru saja dibuat. Tunggu beberapa saat agar potongan video terbentuk, atau tonton langsung di Google Drive setelah live selesai.
          </p>
          <button onclick="retryPlayer()" class="px-4 py-2 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-xs font-bold text-zinc-200 transition">
            <i class="fa-solid fa-rotate-right mr-1.5"></i> Coba Putar Ulang
          </button>
        </div>
      </div>

      <!-- Footer Info -->
      <div class="flex items-center justify-between text-xs text-zinc-400 pt-1">
        <span class="text-[11px] font-mono text-zinc-500 flex items-center gap-1.5">
          <i class="fa-solid fa-circle-check text-emerald-400 text-[9px]"></i> Format: Fragmented MP4 (H.264/AAC)
        </span>
        <button onclick="closeVideoModal()" class="px-5 py-2 rounded-xl bg-zinc-850 hover:bg-zinc-800 text-zinc-300 font-bold transition">Tutup</button>
      </div>

    </div>
  </div>

  <!-- Notification Toast -->
  <div id="toast" class="fixed bottom-5 right-5 z-50 transform translate-y-20 opacity-0 transition-all duration-300 px-5 py-3.5 rounded-2xl shadow-2xl flex items-center gap-3 text-xs font-bold border"></div>

  <!-- Client JavaScript -->
  <script>
    let isRunning = false;
    let cachedRecordings = [];
    let currentVideoUrl = '';

    function showToast(msg, isError = false) {
      const toast = document.getElementById('toast');
      toast.className = `fixed bottom-5 right-5 z-50 transform translate-y-0 opacity-100 transition-all duration-300 px-5 py-3.5 rounded-2xl shadow-2xl flex items-center gap-3 text-xs font-bold border ${
        isError ? 'bg-rose-950/90 text-rose-200 border-rose-800/80 shadow-rose-950/50' : 'bg-emerald-950/90 text-emerald-200 border-emerald-800/80 shadow-emerald-950/50'
      }`;
      toast.innerHTML = `<i class="fa-solid ${isError ? 'fa-circle-exclamation text-rose-400 text-sm' : 'fa-circle-check text-emerald-400 text-sm'}"></i> <span>${msg}</span>`;
      setTimeout(() => {
        toast.className = 'fixed bottom-5 right-5 z-50 transform translate-y-20 opacity-0 transition-all duration-300 px-5 py-3.5 rounded-2xl shadow-2xl flex items-center gap-3 text-xs font-bold border';
      }, 3500);
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
          btn.className = "text-xs font-bold px-3.5 sm:px-4 py-2 sm:py-2.5 rounded-xl bg-rose-600/15 text-rose-400 border border-rose-500/30 hover:bg-rose-600 hover:text-white transition flex items-center gap-2 shadow-sm";
          btnText.innerText = "Hentikan Bot";
          badge.className = "inline-flex items-center gap-1.5 text-xs font-bold px-2.5 py-1 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30";
          badge.innerHTML = `<span class="w-2 h-2 rounded-full bg-emerald-400 pulse-dot"></span> Aktif Memantau`;
        } else {
          btn.className = "text-xs font-bold px-3.5 sm:px-4 py-2 sm:py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white transition flex items-center gap-2 shadow-md shadow-emerald-900/30";
          btnText.innerText = "Mulai Bot";
          badge.className = "inline-flex items-center gap-1.5 text-xs font-bold px-2.5 py-1 rounded-full bg-zinc-800 text-zinc-400 border border-zinc-700";
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
        document.getElementById('stat-disk-pct').innerText = `${h.disk_pct}%`;
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
          <div class="p-8 text-center bg-zinc-900/30 rounded-2xl border border-dashed border-zinc-800 text-zinc-400 space-y-2">
            <i class="fa-solid fa-user-slash text-2xl text-zinc-600 mb-1"></i>
            <p class="text-sm font-semibold text-zinc-300">Belum ada akun target yang dipantau.</p>
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
          <div class="p-4 rounded-2xl bg-zinc-900/60 border ${isLive ? 'border-rose-500 shadow-xl shadow-rose-950/40 bg-gradient-to-r from-rose-950/30 to-zinc-900/70' : 'border-zinc-800/80'} hover:border-zinc-700 transition-all duration-200 flex items-center justify-between gap-3 sm:gap-4">
            
            <div class="flex items-center space-x-3 sm:space-x-4 min-w-0">
              <div class="w-11 h-11 rounded-2xl border ${pInfo.color} flex items-center justify-center shrink-0 text-base shadow-sm">
                <i class="fa-brands ${pInfo.icon}"></i>
              </div>
              <div class="min-w-0">
                <div class="flex items-center gap-2 flex-wrap">
                  <h4 class="font-bold text-sm text-white truncate max-w-[150px] sm:max-w-none">${t.username}</h4>
                  <span class="text-[10px] uppercase font-extrabold px-2 py-0.5 rounded-full ${pInfo.color}">
                    ${plat}
                  </span>
                  <span class="text-[10px] font-bold px-1.5 py-0.5 rounded-md bg-zinc-800 text-zinc-400 border border-zinc-700">
                    ${qual}
                  </span>
                </div>
                <div class="flex items-center gap-2 mt-1">
                  ${isLive ? `
                    <span class="inline-flex items-center gap-1.5 text-xs font-extrabold text-rose-400">
                      <span class="w-2 h-2 rounded-full bg-rose-500 pulse-dot"></span> SEDANG LIVE & DIREKAM
                    </span>
                  ` : `
                    <span class="text-xs text-zinc-400 font-medium flex items-center gap-1.5">
                      <span class="w-1.5 h-1.5 rounded-full ${t.enabled ? 'bg-zinc-500' : 'bg-zinc-700'}"></span>
                      ${t.enabled ? 'Standby (Offline)' : 'Dinonaktifkan'}
                    </span>
                  `}
                </div>
              </div>
            </div>

            <div class="flex items-center space-x-1.5 sm:space-x-2 shrink-0">
              <button onclick="toggleTarget('${t.username}', '${plat}')" title="${t.enabled ? 'Nonaktifkan' : 'Aktifkan'}" class="w-8 h-8 sm:w-9 sm:h-9 rounded-xl ${t.enabled ? 'bg-zinc-800 text-zinc-300 hover:text-white' : 'bg-zinc-850 text-zinc-600 hover:text-zinc-400'} flex items-center justify-center text-xs transition border border-zinc-750">
                <i class="fa-solid ${t.enabled ? 'fa-toggle-on text-emerald-400 text-base' : 'fa-toggle-off text-sm'}"></i>
              </button>
              <button onclick="deleteTarget('${t.username}', '${plat}')" title="Hapus Target" class="w-8 h-8 sm:w-9 sm:h-9 rounded-xl bg-zinc-850 hover:bg-rose-950/40 text-zinc-400 hover:text-rose-400 flex items-center justify-center text-xs transition border border-zinc-750">
                <i class="fa-solid fa-trash-can"></i>
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

    function openAddModal() {
      document.getElementById('add-modal').classList.remove('hidden');
    }

    function closeAddModal() {
      document.getElementById('add-modal').classList.add('hidden');
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
          closeAddModal();
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
        cachedRecordings = data.recordings || [];
        renderRecordingsList(cachedRecordings);
      } catch (e) {
        c.innerHTML = '<p class="text-xs text-rose-400 p-3 text-center">Gagal memuat rekaman.</p>';
      }
    }

    function renderRecordingsList(files) {
      const c = document.getElementById('recordings-container');
      if (!files || files.length === 0) {
        c.innerHTML = '<p class="text-xs text-zinc-500 italic p-4 text-center">Belum ada rekaman lokal (file langsung otomatis diunggah ke Google Drive).</p>';
        return;
      }

      c.innerHTML = files.map(r => `
        <div class="p-3 rounded-2xl bg-zinc-900/70 border border-zinc-800/80 hover:border-zinc-700 flex items-center justify-between text-xs transition duration-150">
          <div class="min-w-0 pr-3">
            <p class="font-bold text-zinc-200 truncate" title="${r.name}">${r.name}</p>
            <p class="text-[10px] text-zinc-500 font-medium mt-0.5">${r.size_mb} MB • ${r.mtime} WIB</p>
          </div>
          <div class="flex items-center space-x-2 shrink-0">
            <button onclick="playVideo('${r.url}', '${r.name}')" class="px-3 py-1.5 rounded-xl bg-rose-600/15 hover:bg-rose-600 text-rose-400 hover:text-white transition font-bold flex items-center gap-1.5 shadow-sm">
              <i class="fa-solid fa-play text-[10px]"></i> Putar
            </button>
            <a href="${r.url}" download class="w-8 h-8 rounded-xl bg-zinc-800/80 hover:bg-zinc-700 text-zinc-400 hover:text-white flex items-center justify-center transition border border-zinc-750" title="Unduh Video">
              <i class="fa-solid fa-download text-xs"></i>
            </a>
          </div>
        </div>
      `).join('');
    }

    function filterRecordings(query) {
      const q = query.toLowerCase().trim();
      if (!q) {
        renderRecordingsList(cachedRecordings);
        return;
      }
      const filtered = cachedRecordings.filter(r => r.name.toLowerCase().includes(q));
      renderRecordingsList(filtered);
    }

    function playVideo(url, name) {
      currentVideoUrl = url;
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
        console.log("Player playback notice:", err);
      });
    }

    function retryPlayer() {
      if (currentVideoUrl) {
        playVideo(currentVideoUrl, document.getElementById('video-modal-title').innerText);
      }
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
            else if (line.includes('Sukses') || line.includes('ter-upload')) color = 'text-emerald-400 font-semibold';
            else if (line.includes('WARNING') || line.includes('Error')) color = 'text-amber-400 font-medium';
            return `<div class="${color}">${escapeHtml(line)}</div>`;
          }).join('');
          consoleEl.scrollTop = consoleEl.scrollHeight;
        }
      } catch (e) {}
    }

    function clearLogs() {
      document.getElementById('log-console').innerHTML = '<p class="text-zinc-600 italic">Log dibersihkan.</p>';
    }

    function escapeHtml(text) {
      return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    // Initialize Pollers
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
    print("  🌐 Auto Live Stream Recorder Web UI v2.2 Pro Berjalan!")
    print(f"  👉 Akses di Browser: http://72.60.79.72:{port}")
    print("=" * 60)
    app.run(host="0.0.0.0", port=port, debug=False)
