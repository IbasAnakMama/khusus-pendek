"""
Website "Lagu & Foto" (Recode Aesthetic Frame + Cute Particles + Synced Lyrics + Auto Heart Finale)
"""

import html
import json
import re
from pathlib import Path
from urllib.parse import quote

from flask import Flask, Response, jsonify

app = Flask(__name__)

# ============ PENGATURAN (silakan ubah) ============
JUDUL = "Untuk  Nenek Lampir😘"
ARTIS = "Backstreet Boys"
JUDUL_LAGU = "Shape of My Heart"
PESAN_AWAL = "Hadiah Buat Pendekkkk"
TOMBOL_AWAL = "Mulai"
FOTO_GANTI_DETIK = 5
MAKS_FOTO = 7                      # batas foto yang bisa diupload pengunjung
MULAI_LIRIK_DI_DETIK = 0.0        # detik ke berapa lirik pertama muncul di audio kamu (misal 0.0, 0.5, 1.0)
OFFSET_LIRIK = 0.0                 # geser halus tambahan (bisa + atau - dalam detik)
JEDA_FOTO_LOVE_DETIK = 0.35        # jeda muncul tiap foto membentuk love di akhir
TAHAN_LOVE_DETIK = 3.5             # berapa lama susunan love ditahan sebelum muncul layar selesai
# ===================================================

# File ini ada di api/, jadi root project = satu folder di atasnya.
# Lagu & lirik ada di folder public/lagu/ (disajikan Vercel langsung dari root URL).
ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "public"
LAGU_DIR = STATIC / "lagu"
AUDIO_EXT = {".mp3", ".m4a", ".ogg", ".wav", ".aac", ".flac"}

# Jangan mkdir di sini: filesystem Vercel read-only.


def _url(path: Path) -> str:
    rel = path.relative_to(STATIC)
    return "/" + "/".join(quote(p) for p in rel.parts)


def _baca_teks(f: Path) -> str:
    raw = f.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="ignore")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="ignore")


def _geser_lrc(teks: str, target_first_sec: float, extra_offset: float) -> str:
    """Geser seluruh timestamp [mm:ss.xx] agar baris pertama mulai di target_first_sec."""
    if not teks.strip():
        return teks

    pat = re.compile(r"\[(\d+):(\d+(?:[.:]\d+)?)\]")
    times = []
    for m in pat.finditer(teks):
        mins = int(m.group(1))
        secs = float(m.group(2).replace(":", "."))
        times.append(mins * 60.0 + secs)

    if not times:
        return teks

    first_raw = min(times)
    shift = (target_first_sec - first_raw) + extra_offset

    def repl(match):
        mins = int(match.group(1))
        secs = float(match.group(2).replace(":", "."))
        new_t = max(0.0, mins * 60.0 + secs + shift)
        nm = int(new_t // 60)
        ns = new_t - nm * 60
        return f"[{nm:02d}:{ns:05.2f}]"

    return pat.sub(repl, teks)


@app.route("/data")
def data():
    lagu_all = sorted(LAGU_DIR.iterdir()) if LAGU_DIR.is_dir() else []
    audio = next((f for f in lagu_all if f.suffix.lower() in AUDIO_EXT), None)
    semua = [f for f in lagu_all if f.is_file()]
    kandidat = [f for f in semua if f.suffix.lower() == ".lrc"] + [
        f for f in semua if f.suffix.lower() == ".txt"
    ]
    lirik_mentah = _baca_teks(kandidat[0]) if kandidat else ""
    lirik = _geser_lrc(lirik_mentah, float(MULAI_LIRIK_DI_DETIK), float(OFFSET_LIRIK))

    return jsonify(
        audio=_url(audio) if audio else None,
        lirik=lirik,
        files=[f.name for f in semua],
    )


HTML = r"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>__JUDUL_HTML__</title>
<style>
  :root {
    --ink: #0d070b;
    --rose: #ff7597;
    --rose-soft: #ffb3c6;
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0; height: 100%; background: var(--ink); color: #fff; overflow: hidden;
    font-family: 'Georgia', 'Times New Roman', serif;
    user-select: none;
  }

  #bg-blur {
    position: fixed; inset: -10%;
    background-size: cover; background-position: center;
    filter: blur(45px) brightness(0.32) saturate(1.2);
    transition: background-image 1.5s ease, opacity 0.8s ease;
    z-index: 0;
  }
  .vignette {
    position: fixed; inset: 0; z-index: 1; pointer-events: none;
    background: radial-gradient(circle at center, transparent 30%, rgba(10, 4, 8, 0.85) 100%);
  }

  #particles {
    position: fixed; inset: 0; width: 100%; height: 100%;
    pointer-events: none; z-index: 2;
  }

  #main-wrap {
    position: relative; z-index: 3;
    height: 100%; width: 100%;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    padding: 64px 20px 36px;
    gap: clamp(18px, 3.5vh, 32px);
    transition: opacity 0.6s ease, transform 0.6s ease;
  }
  #main-wrap.hidden-finale {
    opacity: 0; transform: scale(0.94); pointer-events: none;
  }

  #frame-box {
    position: relative;
    width: min(74vw, 310px);
    aspect-ratio: 4 / 5;
    background: linear-gradient(145deg, #ffffff 0%, #fff0f4 100%);
    padding: 12px 12px 38px 12px;
    border-radius: 18px;
    box-shadow:
      0 20px 50px rgba(0, 0, 0, 0.75),
      0 0 28px rgba(255, 117, 151, 0.28);
    transform: rotate(-1.5deg);
    transition: transform 1.2s cubic-bezier(0.22, 1, 0.36, 1);
    flex-shrink: 0;
  }
  #frame-box.tilt-right { transform: rotate(1.5deg); }

  #frame-box::before {
    content: "♥";
    position: absolute; top: -13px; left: 50%; transform: translateX(-50%);
    width: 28px; height: 28px; border-radius: 50%;
    background: var(--rose); color: #fff;
    font-size: 13px; display: flex; align-items: center; justify-content: center;
    box-shadow: 0 4px 12px rgba(255, 117, 151, 0.6);
    z-index: 5;
  }

  #photo-inner {
    position: relative; width: 100%; height: 100%;
    border-radius: 10px; overflow: hidden;
    background: #231018;
  }
  .layer {
    position: absolute; inset: 0; opacity: 0;
    transition: opacity 1.3s ease;
  }
  .layer.on { opacity: 1; }
  .layer img {
    width: 100%; height: 100%; object-fit: cover; display: block;
    animation-timing-function: ease-out;
  }
  @keyframes kb {
    from { transform: scale(1) translate(0, 0); }
    to   { transform: scale(1.08) translate(var(--x), var(--y)); }
  }

  #frame-caption {
    position: absolute; bottom: 9px; left: 0; right: 0;
    text-align: center; color: #7a4958;
    font-size: 12px; font-style: italic; letter-spacing: 0.04em;
  }

  #lyric {
    width: 100%; max-width: 680px;
    min-height: 6.2em;
    display: flex; flex-direction: column;
    align-items: center; justify-content: flex-start;
    text-align: center; padding: 0 12px;
  }
  #lyric .cur {
    font-size: clamp(18px, 3.6vw, 30px);
    line-height: 1.4; font-style: italic; color: #fff;
    text-shadow: 0 2px 16px rgba(0, 0, 0, 0.9), 0 0 24px rgba(255, 117, 151, 0.35);
    min-height: 1.4em;
  }
  #lyric .cur span {
    display: inline-block; margin: 0 0.14em;
    opacity: 0; transform: translateY(8px) scale(0.96);
    animation: wordIn 0.4s cubic-bezier(0.22, 1, 0.36, 1) forwards;
  }
  @keyframes wordIn {
    to { opacity: 1; transform: translateY(0) scale(1); }
  }
  #lyric .cur span.bv { font-size: 0.78em; color: var(--rose-soft); }
  #lyric .nxt {
    margin-top: 10px;
    font-size: clamp(12px, 2vw, 15px);
    color: rgba(255, 228, 236, 0.48);
  }

  /* ================= FINALE LOVE FOTO SATU PER SATU ================= */
  #heart-finale {
    position: fixed; inset: 0; z-index: 12;
    pointer-events: none; opacity: 0;
    transition: opacity 0.7s ease;
  }
  #heart-finale.active {
    opacity: 1; pointer-events: auto;
  }
  .heart-photo {
    position: fixed;
    left: 50%; top: 50%;
    width: var(--sz, 64px);
    aspect-ratio: 4 / 5;
    background: #fff;
    padding: 4px 4px 10px 4px;
    border-radius: 8px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.65), 0 0 16px rgba(255, 117, 151, 0.45);
    opacity: 0;
    transform: translate(calc(-50% + var(--tx, 0px)), calc(-50% + var(--ty, 0px))) scale(0.15) rotate(var(--rot, 0deg));
    transition:
      opacity 0.55s cubic-bezier(0.22, 1, 0.36, 1),
      transform 0.65s cubic-bezier(0.34, 1.56, 0.64, 1);
  }
  .heart-photo.pop {
    opacity: 1;
    transform: translate(calc(-50% + var(--tx, 0px)), calc(-50% + var(--ty, 0px))) scale(1) rotate(var(--rot, 0deg));
  }
  .heart-photo img {
    width: 100%; height: 100%; object-fit: cover; border-radius: 5px; display: block;
  }
  #heart-center-badge {
    position: fixed; left: 50%; top: 53%;
    transform: translate(-50%, -50%) scale(0.8);
    text-align: center;
    opacity: 0;
    transition: opacity 0.8s ease, transform 0.8s ease;
    pointer-events: none;
    text-shadow: 0 2px 18px rgba(0, 0, 0, 0.9), 0 0 22px rgba(255, 117, 151, 0.7);
  }
  #heart-center-badge.show {
    opacity: 1; transform: translate(-50%, -50%) scale(1);
  }
  #heart-center-badge .big-h {
    font-size: clamp(24px, 5vw, 38px); color: var(--rose); display: block;
  }
  #heart-center-badge span {
    font-size: clamp(13px, 2.5vw, 18px); font-style: italic; color: #fff0f4;
  }

  #judul {
    position: fixed; top: max(16px, env(safe-area-inset-top)); left: 18px; z-index: 6;
    font-size: 14px; letter-spacing: 0.04em; opacity: 0.92;
    text-shadow: 0 2px 8px rgba(0,0,0,0.8);
  }
  #judul .meta-lagu {
    display: block; opacity: 0.72; font-size: 11.5px; margin-top: 3px;
    color: var(--rose-soft); font-style: italic;
  }

  .top-controls {
    position: fixed; top: max(12px, env(safe-area-inset-top)); right: 14px; z-index: 6;
    display: flex; gap: 6px; align-items: center; flex-wrap: wrap; justify-content: flex-end;
  }
  .btn-pill {
    background: rgba(20, 10, 15, 0.55); backdrop-filter: blur(8px);
    color: #fff; border: 1px solid rgba(255, 182, 193, 0.28);
    border-radius: 999px; padding: 6px 12px;
    font: inherit; font-size: 12px; cursor: pointer;
    transition: background 0.2s, transform 0.15s;
  }
  .btn-pill:hover { background: rgba(255, 117, 151, 0.28); }
  .btn-pill:active { transform: scale(0.95); }

  #barwrap {
    position: fixed; left: 0; right: 0; bottom: 0; height: 18px;
    cursor: pointer; z-index: 6;
  }
  #bar {
    position: absolute; left: 0; bottom: 0; height: 4px; width: 0;
    background: linear-gradient(90deg, var(--rose), var(--rose-soft));
    box-shadow: 0 0 10px var(--rose);
  }

  #overlay {
    position: fixed; inset: 0; z-index: 25;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center; gap: 18px;
    justify-content: safe center; overflow-y: auto;
    padding: 24px; text-align: center;
    background: radial-gradient(ellipse at center, #2b101b 0%, #0a0508 75%);
    transition: opacity 0.8s ease;
  }
  #overlay.hide { opacity: 0; pointer-events: none; }
  #overlay h1 {
    margin: 0; font-weight: 400; font-style: italic;
    font-size: clamp(26px, 6vw, 44px);
    text-shadow: 0 0 24px rgba(255, 117, 151, 0.4);
  }
  #mulai {
    background: linear-gradient(135deg, var(--rose), #ff8fab);
    color: #1f060d; font-weight: bold; border: 0; border-radius: 999px;
    padding: 12px 36px; font: inherit; font-size: 16px; cursor: pointer;
    box-shadow: 0 8px 25px rgba(255, 117, 151, 0.45);
  }
  #status { font-size: 12px; opacity: 0.6; max-width: 32em; line-height: 1.5; }
  #upload-area {
    display: flex; flex-direction: column; align-items: center; gap: 10px;
    width: 100%; max-width: 420px;
  }
  #pilih-foto {
    padding: 10px 22px; font-size: 14px;
    border-color: rgba(255, 182, 193, 0.55);
  }
  #pilih-foto:disabled, #mulai:disabled { opacity: 0.4; cursor: not-allowed; }
  #thumbs { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; min-height: 4px; }
  .thumb { position: relative; width: 56px; height: 70px; }
  .thumb img {
    width: 100%; height: 100%; object-fit: cover; display: block;
    border-radius: 8px; border: 2px solid #fff;
    box-shadow: 0 4px 12px rgba(0,0,0,0.6);
  }
  .thumb button {
    position: absolute; top: -7px; right: -7px;
    width: 20px; height: 20px; padding: 0; border: 0; border-radius: 50%;
    background: var(--rose); color: #fff; font-size: 14px; line-height: 20px;
    cursor: pointer;
  }
  #foto-info { font-size: 12px; opacity: 0.75; }
</style>
</head>
<body>

<div id="bg-blur"></div>
<div class="vignette"></div>
<canvas id="particles"></canvas>

<div id="judul">__JUDUL_HTML__<span class="meta-lagu" id="meta-lagu"></span></div>

<div class="top-controls">
  <button id="sync-minus" class="btn-pill" type="button" title="Percepat lirik 0.5 detik">-0.5s</button>
  <button id="sync-plus" class="btn-pill" type="button" title="Perlambat lirik 0.5 detik">+0.5s</button>
  <button id="ctrl" class="btn-pill" type="button">Jeda</button>
</div>

<div id="main-wrap">
  <div id="frame-box">
    <div id="photo-inner">
      <div class="layer"><img alt="Foto kenangan"></div>
      <div class="layer"><img alt="Foto kenangan"></div>
    </div>
    <div id="frame-caption">♥</div>
  </div>

  <div id="lyric">
    <div class="cur"></div>
    <div class="nxt"></div>
  </div>
</div>

<div id="heart-finale">
  <div id="heart-cards"></div>
  <div id="heart-center-badge">
    <span class="big-h">♥</span>
    <span>__JUDUL_HTML__</span>
  </div>
</div>

<div id="barwrap" aria-label="Geser posisi lagu"><div id="bar"></div></div>

<div id="overlay">
  <h1 id="pesan">__PESAN__</h1>
  <div id="upload-area">
    <input type="file" id="file-input" accept="image/*" multiple hidden>
    <button id="pilih-foto" class="btn-pill" type="button">+ Pilih foto (maks __MAKS_FOTO__)</button>
    <div id="thumbs"></div>
    <div id="foto-info"></div>
  </div>
  <button id="mulai" type="button">__TOMBOL__</button>
  <div id="status"></div>
</div>

<script>
const CFG = {
  fotoDetik: __FOTO_DETIK__,
  maksFoto: __MAKS_FOTO__,
  jedaLoveDetik: __JEDA_LOVE_DETIK__,
  tahanLoveDetik: __TAHAN_LOVE_DETIK__,
  artis: __ARTIS_JS__,
  judulLagu: __JUDUL_LAGU_JS__
};

(function renderSongMeta() {
  const el = document.getElementById('meta-lagu');
  const parts = [];
  if (CFG.judulLagu) parts.push('♪ ' + CFG.judulLagu);
  if (CFG.artis) parts.push(CFG.artis);
  el.textContent = parts.join(' — ');
})();

const bgBlur = document.getElementById('bg-blur');
const mainWrap = document.getElementById('main-wrap');
const frameBox = document.getElementById('frame-box');
const frameCap = document.getElementById('frame-caption');
const layers = [...document.querySelectorAll('.layer')];
const curEl = document.querySelector('#lyric .cur');
const nxtEl = document.querySelector('#lyric .nxt');
const bar = document.getElementById('bar');
const barwrap = document.getElementById('barwrap');
const overlay = document.getElementById('overlay');
const statusEl = document.getElementById('status');
const mulaiBtn = document.getElementById('mulai');
const ctrlBtn = document.getElementById('ctrl');
const heartFinale = document.getElementById('heart-finale');
const heartCards = document.getElementById('heart-cards');
const heartBadge = document.getElementById('heart-center-badge');

let fotos = [], lines = [], hasLrc = false;
let audio = null, usingAudio = false;
let started = false, playing = false, base = 0, startPerf = 0;
let curLine = -2, curPhoto = -1;
let nudgeSec = 0;
let finaleTimers = [];
let inFinale = false;

const fileInput = document.getElementById('file-input');
const pilihBtn = document.getElementById('pilih-foto');
const thumbsEl = document.getElementById('thumbs');
const fotoInfo = document.getElementById('foto-info');

function renderThumbs(pesanTambahan) {
  thumbsEl.innerHTML = '';
  fotos.forEach((url, i) => {
    const box = document.createElement('div');
    box.className = 'thumb';
    const im = document.createElement('img');
    im.src = url;
    const x = document.createElement('button');
    x.type = 'button';
    x.textContent = '×';
    x.setAttribute('aria-label', 'Hapus foto');
    x.addEventListener('click', () => {
      URL.revokeObjectURL(url);
      fotos.splice(i, 1);
      renderThumbs();
    });
    box.append(im, x);
    thumbsEl.appendChild(box);
  });
  fotoInfo.textContent = fotos.length + ' / ' + CFG.maksFoto + ' foto' + (pesanTambahan ? ' • ' + pesanTambahan : '');
  pilihBtn.disabled = fotos.length >= CFG.maksFoto;
  mulaiBtn.disabled = fotos.length === 0;
}

pilihBtn.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', () => {
  const files = [...fileInput.files].filter(f => f.type.startsWith('image/'));
  const sisa = CFG.maksFoto - fotos.length;
  files.slice(0, sisa).forEach(f => fotos.push(URL.createObjectURL(f)));
  const kelebihan = files.length > sisa;
  fileInput.value = '';
  renderThumbs(kelebihan ? 'maksimal ' + CFG.maksFoto + ' foto' : '');
});
renderThumbs();

(function initParticles() {
  const canvas = document.getElementById('particles');
  const ctx = canvas.getContext('2d');
  let w, h, items = [];

  function resize() {
    w = canvas.width = window.innerWidth;
    h = canvas.height = window.innerHeight;
  }
  window.addEventListener('resize', resize);
  resize();

  const shapes = ['heart', 'petal', 'sparkle'];
  const colors = ['#ff7597', '#ffb3c6', '#ffd6e0', '#fff0f3', '#ff8fab'];

  function spawn(randomY = false) {
    return {
      x: Math.random() * w,
      y: randomY ? Math.random() * h : h + 20,
      size: 5 + Math.random() * 8,
      speedY: 0.35 + Math.random() * 0.75,
      speedX: (Math.random() - 0.5) * 0.5,
      wobble: Math.random() * Math.PI * 2,
      wobbleSpeed: 0.015 + Math.random() * 0.02,
      rot: Math.random() * Math.PI * 2,
      rotSpeed: (Math.random() - 0.5) * 0.02,
      alpha: 0.28 + Math.random() * 0.45,
      shape: shapes[Math.floor(Math.random() * shapes.length)],
      color: colors[Math.floor(Math.random() * colors.length)]
    };
  }

  for (let i = 0; i < 36; i++) items.push(spawn(true));

  function drawHeart(s) {
    ctx.beginPath();
    const top = s * 0.3;
    ctx.moveTo(0, top);
    ctx.bezierCurveTo(0, 0, -s, 0, -s, top);
    ctx.bezierCurveTo(-s, s * 0.7, 0, s * 0.95, 0, s * 1.2);
    ctx.bezierCurveTo(0, s * 0.95, s, s * 0.7, s, top);
    ctx.bezierCurveTo(s, 0, 0, 0, 0, top);
    ctx.fill();
  }

  function drawPetal(s) {
    ctx.beginPath();
    ctx.ellipse(0, 0, s * 0.55, s, 0, 0, Math.PI * 2);
    ctx.fill();
  }

  function drawSparkle(s) {
    ctx.beginPath();
    for (let i = 0; i < 4; i++) {
      const ang = (i * Math.PI) / 2;
      ctx.lineTo(Math.cos(ang) * s, Math.sin(ang) * s);
      ctx.lineTo(Math.cos(ang + Math.PI / 4) * (s * 0.28), Math.sin(ang + Math.PI / 4) * (s * 0.28));
    }
    ctx.closePath();
    ctx.fill();
  }

  function loop() {
    ctx.clearRect(0, 0, w, h);
    for (let p of items) {
      p.y -= p.speedY;
      p.wobble += p.wobbleSpeed;
      p.x += Math.sin(p.wobble) * 0.45 + p.speedX;
      p.rot += p.rotSpeed;

      if (p.y < -25) Object.assign(p, spawn(false));

      ctx.save();
      ctx.translate(p.x, p.y);
      ctx.rotate(p.rot);
      ctx.globalAlpha = p.alpha;
      ctx.fillStyle = p.color;
      if (p.shape === 'heart') drawHeart(p.size);
      else if (p.shape === 'petal') drawPetal(p.size);
      else drawSparkle(p.size * 0.85);
      ctx.restore();
    }
    requestAnimationFrame(loop);
  }
  loop();
})();

function parseLyrics(text) {
  const re = /\[(\d+):(\d+(?:[.:]\d+)?)\]/g;
  const toT = (m, sec) => parseInt(m, 10) * 60 + parseFloat(sec.replace(':', '.'));
  const raws = (text || '').split(/\r?\n/);
  const timed = [], plain = [];

  for (const raw of raws) {
    const line = raw.replace(/^\uFEFF/, '').trim();
    if (!line || /^\[[a-z]+:/i.test(line)) continue;
    const stamps = [...line.matchAll(re)].map(x => toT(x[1], x[2]));
    const txt = line.replace(re, '').trim();
    if (stamps.length) {
      for (const t of stamps) timed.push({ t, text: txt });
    } else {
      plain.push({ t: null, text: line });
    }
  }

  if (timed.length) {
    hasLrc = true;
    timed.sort((a, b) => a.t - b.t);
    lines = timed;
  } else {
    lines = plain;
  }
}

function dur() {
  if (usingAudio && audio && isFinite(audio.duration) && audio.duration > 0) return audio.duration;
  const last = hasLrc && lines.length ? lines[lines.length - 1].t + 6 : lines.length * 4;
  return Math.max(last, 20);
}

function lineTime(i) {
  if (hasLrc) return Math.max(0, lines[i].t + nudgeSec);
  return i * (dur() / Math.max(1, lines.length));
}

function clock() {
  if (usingAudio && audio) return audio.currentTime;
  return playing ? base + (performance.now() - startPerf) / 1000 : base;
}

function findLineIndex(t) {
  if (!lines.length) return -1;
  if (t < lineTime(0)) return -1;
  let ans = 0;
  for (let i = 0; i < lines.length; i++) {
    if (lineTime(i) <= t + 0.05) ans = i;
    else break;
  }
  return ans;
}

function showLine(idx) {
  curEl.innerHTML = '';
  nxtEl.textContent = '';
  if (idx < 0 || !lines[idx] || !lines[idx].text) return;

  const words = lines[idx].text.split(/\s+/);
  let avail = 1.4;
  if (idx + 1 < lines.length) {
    const gap = lineTime(idx + 1) - lineTime(idx);
    if (gap > 0.2) avail = Math.min(1.4, gap * 0.65);
  }
  const step = Math.min(0.09, avail / Math.max(1, words.length));

  let inBv = false;
  words.forEach((w, i) => {
    const s = document.createElement('span');
    s.textContent = w;
    if (w.startsWith('(')) inBv = true;
    if (inBv) s.className = 'bv';
    if (w.endsWith(')')) inBv = false;
    s.style.animationDelay = (i * step).toFixed(3) + 's';
    curEl.appendChild(s);
  });

  for (let j = idx + 1; j < lines.length; j++) {
    if (lines[j].text) {
      nxtEl.textContent = lines[j].text;
      break;
    }
  }
}

function showPhoto(p) {
  const layer = layers[p % 2];
  const other = layers[(p + 1) % 2];
  const img = layer.querySelector('img');

  frameBox.classList.toggle('tilt-right', p % 2 === 1);

  if (fotos.length) {
    const idx = p % fotos.length;
    const url = fotos[idx];
    img.style.display = '';
    img.src = url;
    bgBlur.style.backgroundImage = 'url("' + url + '")';
    frameCap.textContent = `♥  ${idx + 1} / ${fotos.length}`;
  } else {
    img.style.display = 'none';
    frameCap.textContent = 'Pilih foto dulu';
  }

  img.style.setProperty('--x', ((Math.random() - 0.5) * 3) + '%');
  img.style.setProperty('--y', ((Math.random() - 0.5) * 3) + '%');
  img.style.animation = 'none';
  void img.offsetWidth;
  img.style.animation = 'kb ' + (CFG.fotoDetik + 2) + 's ease-out forwards';

  other.classList.remove('on');
  layer.classList.add('on');
}

function heartPoint(angle, scaleX, scaleY) {
  const x = 16 * Math.pow(Math.sin(angle), 3);
  const y = -(
    13 * Math.cos(angle) -
    5 * Math.cos(2 * angle) -
    2 * Math.cos(3 * angle) -
    Math.cos(4 * angle)
  );
  return {
    tx: (x / 16) * scaleX,
    ty: (y / 13) * scaleY - 10
  };
}

function clearFinale() {
  finaleTimers.forEach(id => clearTimeout(id));
  finaleTimers = [];
  inFinale = false;
  heartFinale.classList.remove('active');
  heartBadge.classList.remove('show');
  heartCards.innerHTML = '';
  mainWrap.classList.remove('hidden-finale');
}

function runHeartFinale(onDone) {
  clearFinale();
  if (!fotos.length) {
    if (onDone) onDone();
    return;
  }

  inFinale = true;
  mainWrap.classList.add('hidden-finale');
  heartFinale.classList.add('active');

  const count = Math.max(fotos.length, 16);
  const minDim = Math.min(window.innerWidth, window.innerHeight);
  const scaleX = Math.min(window.innerWidth * 0.34, minDim * 0.42);
  const scaleY = Math.min(window.innerHeight * 0.28, minDim * 0.36);
  const cardSize = Math.max(46, Math.min(76, minDim * 0.11));

  const els = [];
  for (let i = 0; i < count; i++) {
    const angle = (i / count) * Math.PI * 2;
    const pt = heartPoint(angle, scaleX, scaleY);
    const rot = ((i % 2 === 0 ? 1 : -1) * (4 + (i % 5) * 2.5)).toFixed(1) + 'deg';
    const src = fotos[i % fotos.length];

    const card = document.createElement('div');
    card.className = 'heart-photo';
    card.style.setProperty('--sz', cardSize + 'px');
    card.style.setProperty('--tx', pt.tx.toFixed(1) + 'px');
    card.style.setProperty('--ty', pt.ty.toFixed(1) + 'px');
    card.style.setProperty('--rot', rot);

    const img = document.createElement('img');
    img.src = src;
    img.alt = 'Foto kenangan';
    card.appendChild(img);
    heartCards.appendChild(card);
    els.push(card);
  }

  const stepMs = Math.max(150, CFG.jedaLoveDetik * 1000);
  els.forEach((card, idx) => {
    const tId = setTimeout(() => {
      requestAnimationFrame(() => card.classList.add('pop'));
    }, idx * stepMs);
    finaleTimers.push(tId);
  });

  const totalAppearMs = count * stepMs;
  const badgeTimer = setTimeout(() => {
    heartBadge.classList.add('show');
  }, totalAppearMs + 250);
  finaleTimers.push(badgeTimer);

  if (onDone) {
    const endTimer = setTimeout(() => {
      onDone();
    }, totalAppearMs + CFG.tahanLoveDetik * 1000);
    finaleTimers.push(endTimer);
  }
}

function tick() {
  if (started) {
    const t = clock();
    const idx = findLineIndex(t);
    if (idx !== curLine) {
      curLine = idx;
      showLine(idx);
    }
    const p = Math.floor(t / CFG.fotoDetik);
    if (p !== curPhoto) {
      curPhoto = p;
      showPhoto(p);
    }
    bar.style.width = Math.min(100, (t / dur()) * 100) + '%';
    if (!usingAudio && t > dur() + 3) finish();
  }
  requestAnimationFrame(tick);
}

function seekTo(t) {
  if (!started) return;
  clearFinale();
  t = Math.max(0, Math.min(t, dur()));
  if (usingAudio && audio) audio.currentTime = t;
  else { base = t; startPerf = performance.now(); }
  curLine = -2;
}

function finish() {
  if (inFinale) return;
  started = false; playing = false;
  runHeartFinale(() => {
    document.getElementById('pesan').textContent = 'Selesai ♥';
    mulaiBtn.textContent = 'Putar lagi';
    overlay.classList.remove('hide');
  });
}

async function start() {
  if (!fotos.length) return;
  clearFinale();
  overlay.classList.add('hide');
  curLine = -2; curPhoto = -1; nudgeSec = 0;
  base = 0; startPerf = performance.now();
  started = true; playing = true;
  ctrlBtn.textContent = 'Jeda';
  if (usingAudio && audio) {
    audio.currentTime = 0;
    try { await audio.play(); }
    catch (e) { usingAudio = false; startPerf = performance.now(); }
  }
}

function toggle() {
  if (!started) return;
  if (usingAudio && audio) {
    if (audio.paused) { audio.play(); ctrlBtn.textContent = 'Jeda'; }
    else { audio.pause(); ctrlBtn.textContent = 'Putar'; }
  } else if (playing) {
    base = clock(); playing = false; ctrlBtn.textContent = 'Putar';
  } else {
    startPerf = performance.now(); playing = true; ctrlBtn.textContent = 'Jeda';
  }
}

function adjustSync(delta) {
  nudgeSec = Math.round((nudgeSec + delta) * 10) / 10;
  curLine = -2;
  nxtEl.textContent = `Geser lirik: ${nudgeSec > 0 ? '+' : ''}${nudgeSec}s`;
}

async function init() {
  try {
    const r = await fetch('/data');
    const d = await r.json();
    parseLyrics(d.lirik);
    if (d.audio) {
      audio = new Audio(d.audio);
      audio.preload = 'auto';
      usingAudio = true;
      audio.addEventListener('ended', finish);
      audio.addEventListener('error', () => { usingAudio = false; audio = null; });
    }
    const info = [];
    info.push(d.audio ? 'lagu siap' : 'lagu belum ada');
    info.push(lines.length ? `${lines.length} baris lirik siap` : 'lirik belum ada');
    statusEl.textContent = info.join(' • ');
  } catch (e) {
    statusEl.textContent = 'Gagal memuat data dari server.';
  }
}

mulaiBtn.addEventListener('click', start);
ctrlBtn.addEventListener('click', toggle);
document.getElementById('sync-minus').addEventListener('click', () => adjustSync(-0.5));
document.getElementById('sync-plus').addEventListener('click', () => adjustSync(0.5));
barwrap.addEventListener('click', e => {
  const r = barwrap.getBoundingClientRect();
  seekTo(((e.clientX - r.left) / r.width) * dur());
});
window.addEventListener('keydown', e => {
  if (!started) return;
  if (e.code === 'Space') { e.preventDefault(); toggle(); }
  else if (e.code === 'ArrowRight') seekTo(clock() + 5);
  else if (e.code === 'ArrowLeft') seekTo(clock() - 5);
});

init();
requestAnimationFrame(tick);
</script>
</body>
</html>
"""


@app.route("/")
def index():
    page = (
        HTML.replace("__JUDUL_HTML__", html.escape(JUDUL))
        .replace("__ARTIS_JS__", json.dumps(ARTIS, ensure_ascii=False))
        .replace("__JUDUL_LAGU_JS__", json.dumps(JUDUL_LAGU, ensure_ascii=False))
        .replace("__PESAN__", html.escape(PESAN_AWAL))
        .replace("__TOMBOL__", html.escape(TOMBOL_AWAL))
        .replace("__FOTO_DETIK__", str(FOTO_GANTI_DETIK))
        .replace("__MAKS_FOTO__", str(MAKS_FOTO))
        .replace("__JEDA_LOVE_DETIK__", str(JEDA_FOTO_LOVE_DETIK))
        .replace("__TAHAN_LOVE_DETIK__", str(TAHAN_LOVE_DETIK))
    )
    return Response(page, mimetype="text/html")


if __name__ == "__main__":
    print("Lagu  :", LAGU_DIR)
    app.run(host="0.0.0.0", port=5000, debug=True)