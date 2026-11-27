import hashlib
import hmac
import html
import json
import os
import re
import secrets
import time
from pathlib import Path
from urllib.parse import quote

try:
    from vercel.blob import sync as blob
except Exception:
    blob = None

from flask import Flask, Response, abort, jsonify, request, send_from_directory

app = Flask(__name__)

PIN = os.environ.get("PIN_GALERI", "1234")
PIN_PACAR = os.environ.get("PIN_PACAR", "")
NAMA_GALERI = "Galeri My MBG"
JUDUL = "Buat Pendekkkk"
PESAN_AWAL = "Hadiah Buat Pendekkkk 156"
FOTO_GANTI_DETIK = 5
MASA_LOGIN_JAM = 12
OFFSET_LIRIK = 0.0
JEDA_FOTO_LOVE_DETIK = 0.35
TAHAN_LOVE_DETIK = 3.5

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "public"
LAGU_DIR = STATIC / "lagu"
AUDIO_EXT = {".mp3", ".m4a", ".ogg", ".wav", ".aac", ".flac"}
COOKIE = "galeri_sesi"
_GAGAL = {}


def _rahasia() -> bytes:
    kunci = os.environ.get("SECRET_KEY") or hashlib.sha256(("galeri::" + PIN).encode()).hexdigest()
    return kunci.encode()


def _buat_token(peran: str) -> str:
    pesan = f"v2.{peran}.{int(time.time() + MASA_LOGIN_JAM * 3600)}"
    return pesan + "." + hmac.new(_rahasia(), pesan.encode(), hashlib.sha256).hexdigest()


def _peran():
    try:
        v, peran, exp, sig = (request.cookies.get(COOKIE) or "").split(".")
        benar = hmac.new(_rahasia(), f"{v}.{peran}.{exp}".encode(), hashlib.sha256).hexdigest()
        if v == "v2" and peran in ("admin", "lihat") and hmac.compare_digest(sig, benar) and int(exp) > time.time():
            return peran
    except Exception:
        pass
    return None


def _sudah_login() -> bool:
    return _peran() is not None


def _ip() -> str:
    return (request.headers.get("x-forwarded-for", "").split(",")[0].strip()) or request.remote_addr or "?"


@app.post("/api/login")
def login():
    ip, kini = _ip(), time.time()
    cat = _GAGAL.get(ip)
    if cat and kini - cat[1] > 300:
        _GAGAL.pop(ip, None)
        cat = None
    if cat and cat[0] >= 5:
        return jsonify(pesan="Terlalu banyak percobaan. Coba lagi 5 menit lagi."), 429
    pin = str((request.get_json(silent=True) or {}).get("pin", ""))
    peran = None
    if hmac.compare_digest(pin.encode(), PIN.encode()):
        peran = "admin"
    elif PIN_PACAR and hmac.compare_digest(pin.encode(), PIN_PACAR.encode()):
        peran = "lihat"
    if peran:
        _GAGAL.pop(ip, None)
        resp = jsonify(ok=True)
        https = request.is_secure or request.headers.get("x-forwarded-proto") == "https"
        resp.set_cookie(COOKIE, _buat_token(peran), max_age=MASA_LOGIN_JAM * 3600,
                        httponly=True, samesite="Lax", secure=https)
        return resp
    _GAGAL[ip] = [(cat[0] + 1) if cat else 1, cat[1] if cat else kini]
    time.sleep(0.7)
    return jsonify(pesan="PIN salah"), 401


@app.post("/api/logout")
def logout():
    resp = jsonify(ok=True)
    resp.delete_cookie(COOKIE)
    return resp


def _url(path: Path) -> str:
    return "/" + "/".join(quote(p) for p in path.relative_to(STATIC).parts)


def _baca_teks(f: Path) -> str:
    raw = f.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16", errors="ignore")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="ignore")


_POLA = re.compile(r"\[(\d+):(\d+(?:[.:]\d+)?)\]")


def _detik(m) -> float:
    return int(m.group(1)) * 60 + float(m.group(2).replace(":", "."))


def _geser_lrc(teks: str, mulai, offset: float) -> str:
    ts = [_detik(m) for m in _POLA.finditer(teks)]
    if not ts:
        return teks
    pertama = min(ts)
    if mulai == "auto":
        mulai = 0.0 if pertama > 45 else None
    geser = ((float(mulai) - pertama) if mulai is not None else 0.0) + offset
    if not geser:
        return teks

    def ganti(m):
        t = max(0.0, _detik(m) + geser)
        return f"[{int(t // 60):02d}:{t % 60:05.2f}]"

    return _POLA.sub(ganti, teks)


def _daftar_lagu():
    if not LAGU_DIR.is_dir():
        return []
    files = sorted(f for f in LAGU_DIR.iterdir() if f.is_file())
    audios = [f for f in files if f.suffix.lower() in AUDIO_EXT]
    lrc = {}
    for f in files:
        if f.suffix.lower() in (".lrc", ".txt") and (f.stem.lower() not in lrc or f.suffix.lower() == ".lrc"):
            lrc[f.stem.lower()] = f
    hasil = []
    for i, a in enumerate(audios):
        lf = lrc.get(a.stem.lower())
        if lf is None and len(audios) == 1 and lrc:
            lf = lrc[sorted(lrc)[0]]
        meta = {}
        mf = a.with_name(a.stem + ".json")
        if mf.exists():
            try:
                meta = json.loads(_baca_teks(mf))
            except Exception:
                meta = {}
        nama = a.stem.replace("_", " ")
        artis, judul = (nama.split(" - ", 1) if " - " in nama else ("", nama))
        teks = _baca_teks(lf) if lf else ""
        teks = _geser_lrc(teks, meta.get("mulai_lirik", "auto"),
                          float(meta.get("offset", 0)) + float(OFFSET_LIRIK))
        hasil.append({
            "id": f"l{i}",
            "judul": meta.get("judul", judul.strip()),
            "artis": meta.get("artis", artis.strip()),
            "audio": _url(a),
            "lirik": teks,
        })
    return hasil


@app.get("/data")
def data():
    if not _sudah_login():
        abort(401)
    return jsonify(lagu=_daftar_lagu(), peran=_peran())


_ID = re.compile(r"^\d{13}-[0-9a-f]{6}$")


def _butuh(admin=False):
    p = _peran()
    if not p:
        abort(401)
    if admin and p != "admin":
        abort(403)
    if blob is None:
        abort(503)


@app.get("/api/foto")
def daftar_foto():
    _butuh()
    try:
        hasil = []
        for b in blob.query_blobs(prefix="thumb/"):
            fid = b.pathname.split("/", 1)[1].rsplit(".", 1)[0]
            if _ID.match(fid):
                hasil.append({"id": fid, "added": int(fid[:13])})
    except Exception:
        return jsonify(pesan="Blob belum tersambung"), 503
    return jsonify(foto=sorted(hasil, key=lambda x: -x["added"]))


@app.get("/api/f/<kind>/<fid>")
def ambil_foto(kind, fid):
    _butuh()
    if kind not in ("foto", "thumb") or not _ID.match(fid):
        abort(404)
    try:
        r = blob.get_blob(f"{kind}/{fid}.jpg", access="private")
    except Exception as e:
        abort(404 if "NotFound" in type(e).__name__ else 503)
    return Response(r.body, mimetype="image/jpeg",
                    headers={"Cache-Control": "private, max-age=31536000, immutable"})


@app.post("/api/foto")
def tambah_foto():
    _butuh(admin=True)
    f, t = request.files.get("foto"), request.files.get("thumb")
    if not f or not t:
        abort(400)
    fid = f"{int(time.time() * 1000)}-{secrets.token_hex(3)}"
    try:
        blob.put_blob(f"foto/{fid}.jpg", f.read(), access="private", content_type="image/jpeg")
        blob.put_blob(f"thumb/{fid}.jpg", t.read(), access="private", content_type="image/jpeg")
    except Exception:
        return jsonify(pesan="Gagal menyimpan ke Blob"), 503
    return jsonify(id=fid)


@app.delete("/api/foto/<fid>")
def hapus_foto(fid):
    _butuh(admin=True)
    if not _ID.match(fid):
        abort(404)
    try:
        blob.delete_blob([f"thumb/{fid}.jpg", f"foto/{fid}.jpg"])
    except Exception:
        return jsonify(pesan="Gagal menghapus"), 503
    return jsonify(ok=True)


@app.get("/lagu/<path:nama>")
def file_lagu(nama):
    if not _sudah_login():
        abort(401)
    return send_from_directory(LAGU_DIR, nama)


PIN_HTML = r"""<!DOCTYPE html><html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><title>__NAMA__</title>
<style>
html,body{margin:0;height:100%;background:radial-gradient(ellipse at center,#2b101b,#0a0508 75%);color:#fff;font-family:Georgia,serif;overflow:hidden;user-select:none}
main{height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px;padding:20px;text-align:center}
.h{font-size:36px;color:#ff7597;text-shadow:0 0 24px rgba(255,117,151,.6)}
h1{margin:0;font-weight:400;font-style:italic;font-size:clamp(22px,6vw,32px)}
p{margin:0;font-size:13px;opacity:.6}
#dots{display:flex;gap:14px;height:16px}
#dots i{width:14px;height:14px;border-radius:50%;border:2px solid #ff7597;transition:background .15s}
#dots i.on{background:#ff7597}
#dots.err{animation:sh .4s}
@keyframes sh{20%,60%{transform:translateX(-9px)}40%,80%{transform:translateX(9px)}}
#pad{display:grid;grid-template-columns:repeat(3,72px);gap:12px}
#pad button{height:60px;border-radius:50%;border:1px solid rgba(255,182,193,.3);background:rgba(20,10,15,.55);color:#fff;font:inherit;font-size:22px;cursor:pointer}
#pad button:active{background:rgba(255,117,151,.35)}
#msg{min-height:1.2em;font-size:13px;color:#ffb3c6}
</style></head><body><main>
<div class="h">&#9829;</div><h1>__NAMA__</h1><p>Masukkan PIN</p>
<div id="dots"></div><div id="msg"></div>
<div id="pad"></div>
</main><script>
const N=__PANJANG__;let pin='',kunci=false;
const dots=document.getElementById('dots'),msg=document.getElementById('msg'),pad=document.getElementById('pad');
for(let i=0;i<N;i++)dots.appendChild(document.createElement('i'));
['1','2','3','4','5','6','7','8','9','','0','\u232b'].forEach(k=>{const b=document.createElement('button');b.type='button';b.textContent=k;if(!k)b.style.visibility='hidden';b.onclick=()=>tekan(k);pad.appendChild(b);});
function gambar(){[...dots.children].forEach((d,i)=>d.classList.toggle('on',i<pin.length));}
function tekan(k){if(kunci)return;if(k==='\u232b')pin=pin.slice(0,-1);else if(/\d/.test(k)&&pin.length<N)pin+=k;gambar();if(pin.length===N)kirim();}
async function kirim(){kunci=true;msg.textContent='';
try{const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin})});
if(r.ok){location.replace('/');return;}
const d=await r.json().catch(()=>({}));msg.textContent=d.pesan||'PIN salah';}
catch(e){msg.textContent='Gagal terhubung';}
dots.classList.add('err');setTimeout(()=>{dots.classList.remove('err');pin='';gambar();kunci=false;},450);}
addEventListener('keydown',e=>{if(/^\d$/.test(e.key))tekan(e.key);else if(e.key==='Backspace')tekan('\u232b');});
</script></body></html>
"""


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
    width: min(74vw, 310px, 38vh);
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

  body:not(.in-player) .pl { display: none !important; }
  body.in-player #view-gallery { display: none; }
  body:not(.in-player) #bg-blur { opacity: 0; }
  #view-gallery {
    position: fixed; inset: 0; z-index: 4; overflow-y: auto; -webkit-overflow-scrolling: touch;
    background: radial-gradient(ellipse at top, rgba(255,117,151,.13), transparent 55%);
  }
  #g-head {
    position: sticky; top: 0; z-index: 5; display: flex; justify-content: space-between;
    align-items: center; gap: 10px; flex-wrap: wrap;
    padding: max(14px, env(safe-area-inset-top)) 16px 12px;
    background: rgba(13, 7, 11, .82); backdrop-filter: blur(14px);
    border-bottom: 1px solid rgba(255,182,193,.12);
  }
  #g-head h1 { margin: 0; font-weight: 400; font-style: italic; font-size: clamp(20px, 5vw, 28px); }
  .hh { color: var(--rose); }
  #g-sub { margin: 2px 0 0; font-size: 12px; opacity: .6; }
  .g-act { display: flex; gap: 8px; }
  .btn {
    background: rgba(20,10,15,.55); color: #fff; border: 1px solid rgba(255,182,193,.3);
    border-radius: 999px; padding: 8px 15px; font: inherit; font-size: 13px; cursor: pointer;
    text-decoration: none; display: inline-block; transition: background .2s, transform .15s;
  }
  .btn:hover { background: rgba(255,117,151,.25); }
  .btn:active { transform: scale(.95); }
  .btn:disabled { opacity: .4; cursor: not-allowed; }
  .btn.primary { background: linear-gradient(135deg, var(--rose), #ff8fab); color: #1f060d; font-weight: bold; border: 0; box-shadow: 0 6px 18px rgba(255,117,151,.35); }
  .btn.danger { color: #ffb3b3; border-color: rgba(255,120,120,.5); }
  #g-empty { text-align: center; padding: 18vh 24px; opacity: .8; }
  #g-empty .big { font-size: 54px; color: var(--rose); text-shadow: 0 0 30px rgba(255,117,151,.5); }
  #g-grid { columns: 2; column-gap: 12px; padding: 14px 14px 120px; }
  @media (min-width: 640px) { #g-grid { columns: 3; } }
  @media (min-width: 980px) { #g-grid { columns: 4; } }
  @media (min-width: 1300px) { #g-grid { columns: 5; } }
  .ph {
    position: relative; margin: 0 0 12px; break-inside: avoid; border-radius: 14px; overflow: hidden;
    background: #231018; cursor: pointer; box-shadow: 0 8px 22px rgba(0,0,0,.5);
    opacity: 0; animation: fup .5s ease forwards; animation-delay: calc(var(--i) * 35ms);
    transition: transform .25s, box-shadow .25s;
  }
  @keyframes fup { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
  .ph:hover { transform: translateY(-3px) rotate(-.4deg); box-shadow: 0 12px 28px rgba(0,0,0,.6), 0 0 18px rgba(255,117,151,.25); }
  .ph img { width: 100%; display: block; }
  .ph.sel { outline: 3px solid var(--rose); outline-offset: -3px; }
  .ph.sel img { filter: brightness(.8); }
  .cek {
    position: absolute; top: 8px; right: 8px; width: 28px; height: 28px; border-radius: 50%;
    border: 2px solid rgba(255,255,255,.75); background: rgba(0,0,0,.3); color: #fff;
    font: bold 13px Georgia, serif; cursor: pointer; padding: 0; opacity: .55; transition: opacity .2s;
  }
  .ph:hover .cek, body.selmode .cek { opacity: 1; }
  .ph.sel .cek { background: var(--rose); border-color: #fff; }
  #selbar {
    position: fixed; left: 50%; bottom: max(16px, env(safe-area-inset-bottom)); transform: translateX(-50%);
    z-index: 8; display: none; align-items: center; gap: 8px; max-width: 96vw;
    background: rgba(20,10,15,.88); backdrop-filter: blur(12px); white-space: nowrap;
    border: 1px solid rgba(255,182,193,.25); border-radius: 999px; padding: 8px 10px 8px 16px; font-size: 13px;
  }
  body.selmode #selbar { display: flex; }
  #selbar .btn { padding: 7px 12px; font-size: 12px; }
  .sheet {
    position: fixed; inset: 0; z-index: 30; background: rgba(0,0,0,.6);
    display: none; align-items: flex-end; justify-content: center;
  }
  .sheet.on { display: flex; }
  .sheet .card {
    width: min(520px, 100%); max-height: 88vh; overflow: auto; display: flex; flex-direction: column; gap: 14px;
    background: #1a0b12; border: 1px solid rgba(255,182,193,.2); border-radius: 22px 22px 0 0;
    padding: 20px 20px max(20px, env(safe-area-inset-bottom));
  }
  .sheet h2 { margin: 0; font-weight: 400; font-style: italic; font-size: 22px; }
  .lagu { display: flex; gap: 12px; align-items: center; padding: 12px; border-radius: 14px; border: 1px solid rgba(255,182,193,.18); cursor: pointer; }
  .lagu:has(input:checked) { border-color: var(--rose); background: rgba(255,117,151,.12); }
  .lagu small { display: block; opacity: .6; font-size: 12px; margin-top: 2px; }
  .lagu input, .row input { accent-color: var(--rose); }
  .row { display: flex; gap: 10px; align-items: center; justify-content: flex-end; font-size: 13px; }
  #lb { position: fixed; inset: 0; z-index: 40; background: rgba(8,3,6,.96); display: none; align-items: center; justify-content: center; touch-action: pan-y; }
  #lb.on { display: flex; }
  #lb-img { max-width: 100%; max-height: 80vh; object-fit: contain; border-radius: 10px; }
  #lb-x { position: absolute; top: max(12px, env(safe-area-inset-top)); right: 12px; }
  .nav { position: absolute; top: 50%; transform: translateY(-50%); font-size: 22px; padding: 8px 15px; }
  #lb-p { left: 10px; } #lb-n { right: 10px; }
  #lb-bar { position: absolute; bottom: max(14px, env(safe-area-inset-bottom)); left: 0; right: 0; display: flex; gap: 10px; justify-content: center; align-items: center; font-size: 12px; }
  #toast {
    position: fixed; left: 50%; top: max(70px, env(safe-area-inset-top)); transform: translate(-50%, -10px); z-index: 50;
    background: rgba(255,117,151,.95); color: #1f060d; padding: 9px 18px; border-radius: 999px; font-size: 13px;
    opacity: 0; pointer-events: none; transition: opacity .3s, transform .3s; max-width: 90vw; text-align: center;
  }
  #toast.show { opacity: 1; transform: translate(-50%, 0); }
  body.viewer #b-tambah, body.viewer #sel-hapus, body.viewer #lb-del { display: none !important; }
  @media (max-width: 520px) { .top-controls .lirik-sync { display: none; } #judul { max-width: 40vw; } }

  body[data-tema="hati"] { --rose: #ff7597; --rose-soft: #ffb3c6; --tint: rgba(10,4,8,.85); --wash: rgba(0,0,0,0); --kan: sway; }
  body[data-tema="bintang"] { --rose: #b9a6ff; --rose-soft: #e1d9ff; --tint: rgba(6,6,28,.9); --wash: rgba(30,20,90,.38); --kan: hop; }
  body[data-tema="sakura"] { --rose: #ff8fb1; --rose-soft: #ffd0df; --tint: rgba(40,14,24,.8); --wash: rgba(255,150,180,.13); --kan: wiggle; }
  body[data-tema="permen"] { --rose: #ff6fb5; --rose-soft: #ffc9e6; --tint: rgba(40,10,50,.75); --wash: rgba(120,200,255,.15); --kan: bob; }
  body[data-tema="neon"] { --rose: #ff3d9a; --rose-soft: #7df3ff; --tint: rgba(0,0,10,.92); --wash: rgba(0,0,0,.35); --kan: glowk; }
  body[data-tema="salju"] { --rose: #6fc3ff; --rose-soft: #d8f0ff; --tint: rgba(4,16,36,.88); --wash: rgba(100,170,255,.16); --kan: waddle; }
  .vignette { background: radial-gradient(circle at center, transparent 30%, var(--tint) 100%), linear-gradient(var(--wash), var(--wash)); transition: background .8s; }
  body[data-tema="bintang"] #lyric .cur { color: #fff6cf; letter-spacing: .05em; }
  body[data-tema="permen"] #lyric .cur { font-style: normal; font-weight: 700; font-family: 'Trebuchet MS', 'Comic Sans MS', sans-serif; }
  body[data-tema="neon"] #lyric .cur { text-shadow: 0 0 6px #fff, 0 0 18px var(--rose), 0 0 36px var(--rose); font-style: normal; letter-spacing: .04em; }
  body[data-tema="salju"] #lyric .cur { text-shadow: 0 0 14px #9fd8ff, 0 2px 12px rgba(0,0,0,.8); }
  body[data-tema="sakura"] #lyric .cur { color: #fff0f5; text-shadow: 0 0 18px rgba(255,143,177,.7), 0 2px 12px rgba(0,0,0,.8); }

  #frame-box:not([data-f="polaroid"]), #frame-box:not([data-f="polaroid"]).tilt-right { transform: none; }
  #frame-box[data-f="hati"], #frame-box[data-f="bintang"] { background: none; padding: 0; box-shadow: none; aspect-ratio: 1 / 1; width: min(84vw, 350px, 42vh); filter: drop-shadow(0 0 16px var(--rose)); }
  #frame-box[data-f="hati"]::before, #frame-box[data-f="bintang"]::before { content: none; }
  #frame-box[data-f="hati"]::after, #frame-box[data-f="bintang"]::after { content: ""; position: absolute; inset: -5%; background: linear-gradient(145deg, var(--rose), var(--rose-soft)); z-index: -1; }
  #frame-box[data-f="hati"]::after, #frame-box[data-f="hati"] #photo-inner { clip-path: url(#c-hati); }
  #frame-box[data-f="bintang"]::after, #frame-box[data-f="bintang"] #photo-inner { clip-path: polygon(50% 0%, 61% 35%, 98% 35%, 68% 57%, 79% 91%, 50% 70%, 21% 91%, 32% 57%, 2% 35%, 39% 35%); }
  #frame-box[data-f="hati"] #photo-inner, #frame-box[data-f="bintang"] #photo-inner { border-radius: 0; }
  #frame-box[data-f="hati"] #frame-caption, #frame-box[data-f="bintang"] #frame-caption, #frame-box[data-f="bulat"] #frame-caption { bottom: -30px; color: var(--rose-soft); }
  #frame-box[data-f="bulat"] { aspect-ratio: 1 / 1; width: min(78vw, 330px, 40vh); padding: 10px; border-radius: 50%; background: conic-gradient(var(--rose), var(--rose-soft), #fff, var(--rose-soft), var(--rose)); box-shadow: 0 0 30px var(--rose); }
  #frame-box[data-f="bulat"] #photo-inner { border-radius: 50%; }
  #frame-box[data-f="bulat"]::before { content: "🎀"; background: none; box-shadow: none; font-size: 26px; top: -18px; }
  #frame-box[data-f="film"] { background: #15110f; padding: 28px 12px; border-radius: 6px; box-shadow: 0 20px 50px rgba(0,0,0,.8), 0 0 22px var(--rose); }
  #frame-box[data-f="film"] #photo-inner { border-radius: 3px; }
  #frame-box[data-f="film"]::before, #frame-box[data-f="film"]::after { content: ""; position: absolute; left: 10px; right: 10px; top: 9px; width: auto; height: 9px; transform: none; border-radius: 2px; background: repeating-linear-gradient(90deg, #f1e7cf 0 9px, transparent 9px 18px); box-shadow: none; }
  #frame-box[data-f="film"]::after { top: auto; bottom: 9px; }
  #frame-box[data-f="film"] #frame-caption { display: none; }
  #frame-box[data-f="lengkung"] { border-radius: 999px 999px 20px 20px; background: linear-gradient(160deg, #fff7ec, #ffd9c7); }
  #frame-box[data-f="lengkung"] #photo-inner { border-radius: 999px 999px 10px 10px; }
  #frame-box[data-f="lengkung"]::before { content: "🌸"; background: none; box-shadow: none; font-size: 24px; top: -16px; }
  body[data-bk="bulat"] .heart-photo, body[data-bk="hati"] .heart-photo { border-radius: 50%; aspect-ratio: 1; padding: 3px; }
  body[data-bk="bulat"] .heart-photo img, body[data-bk="hati"] .heart-photo img { border-radius: 50%; }
  body[data-bk="bintang"] .heart-photo { aspect-ratio: 1; padding: 0; clip-path: polygon(50% 0%, 61% 35%, 98% 35%, 68% 57%, 79% 91%, 50% 70%, 21% 91%, 32% 57%, 2% 35%, 39% 35%); }
  body[data-bk="film"] .heart-photo { background: #15110f; border-radius: 3px; padding: 5px 3px; }
  body[data-bk="lengkung"] .heart-photo { border-radius: 999px 999px 6px 6px; }

  #photo-inner { perspective: 800px; }
  body[data-trans="blur"] .layer.on { animation: inBlur 1.2s ease-out; }
  body[data-trans="slide"] .layer.on { animation: inSlide .9s cubic-bezier(.22,1,.36,1); }
  body[data-trans="drop"] .layer.on { animation: inDrop .9s ease-out; }
  body[data-trans="flip"] .layer.on { animation: inFlip 1s ease-out; }
  body[data-trans="zin"] .layer.on { animation: inZin 1.1s ease-out; }
  @keyframes inBlur { from { filter: blur(16px) brightness(2.2); } to { filter: none; } }
  @keyframes inSlide { from { transform: translateX(45%) rotate(7deg); } to { transform: none; } }
  @keyframes inDrop { 0% { transform: translateY(-80%); } 60% { transform: translateY(7%); } 80% { transform: translateY(-3%); } 100% { transform: none; } }
  @keyframes inFlip { from { transform: rotateY(90deg); } to { transform: rotateY(0); } }
  @keyframes inZin { from { transform: scale(1.5); } to { transform: scale(1); } }

  #karakter { position: fixed; left: 14px; bottom: max(24px, env(safe-area-inset-bottom)); z-index: 7; cursor: pointer; font-size: clamp(44px, 10vw, 66px); line-height: 1; -webkit-tap-highlight-color: transparent; }
  #karakter .k { display: inline-block; transform-origin: 50% 90%; animation: var(--kan) 2.6s ease-in-out infinite; filter: drop-shadow(0 4px 10px rgba(0,0,0,.5)); }
  #karakter .item { position: absolute; right: -14px; top: -6px; font-size: .5em; animation: floaty 2s ease-in-out infinite; }
  #karakter.lompat .k { animation: lompat .55s ease-out; }
  #gelembung { position: fixed; left: calc(14px + clamp(44px, 10vw, 66px) + 8px); bottom: calc(max(24px, env(safe-area-inset-bottom)) + 34px); background: #fff; padding: 6px 12px; border-radius: 18px 18px 18px 4px; font-size: 26px; line-height: 1.2; white-space: nowrap; z-index: 7; pointer-events: none; opacity: 0; transform: translateY(6px) scale(.9); transform-origin: 0 100%; transition: opacity .3s, transform .3s; box-shadow: 0 6px 18px rgba(0,0,0,.45); }
  #gelembung.on { opacity: 1; transform: none; }
  @keyframes sway { 0%, 100% { transform: rotate(-6deg); } 50% { transform: rotate(6deg); } }
  @keyframes hop { 0%, 60%, 100% { transform: translateY(0) scale(1, 1); } 70% { transform: translateY(0) scale(1.1, .88); } 82% { transform: translateY(-16px) scale(.94, 1.08); } }
  @keyframes wiggle { 0%, 100% { transform: rotate(-3deg) translateX(-2px); } 50% { transform: rotate(3deg) translateX(3px); } }
  @keyframes bob { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-9px); } }
  @keyframes glowk { 0%, 100% { transform: scale(1); filter: drop-shadow(0 0 6px var(--rose)); } 50% { transform: scale(1.09); filter: drop-shadow(0 0 18px var(--rose)); } }
  @keyframes waddle { 0%, 100% { transform: rotate(-8deg) translateX(-3px); } 50% { transform: rotate(8deg) translateX(3px); } }
  @keyframes lompat { 0% { transform: translateY(0) scale(1); } 35% { transform: translateY(-24px) scale(1.12, .94); } 100% { transform: translateY(0) scale(1); } }
  @keyframes floaty { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-5px); } }

  .sheet h3 { margin: 4px 0 -4px; font-weight: 400; font-style: italic; font-size: 17px; }
  .pil { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
  .opsi { position: relative; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px; padding: 10px 4px; border-radius: 14px; border: 1px solid rgba(255,182,193,.18); cursor: pointer; text-align: center; font-size: 12px; }
  .opsi input { position: absolute; opacity: 0; pointer-events: none; }
  .opsi:has(input:checked) { border-color: var(--rose); background: rgba(255,117,151,.16); }
  .opsi .ik { font-size: 30px; line-height: 1; }
  .opsi.kecil { padding: 9px 4px; }
</style>
</head>
<body data-tema="hati" data-trans="zoom" data-bk="polaroid">
<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs><clipPath id="c-hati" clipPathUnits="objectBoundingBox"><path d="M0.5,1 C0.12,0.72 0,0.5 0,0.3 C0,0.13 0.12,0 0.27,0 C0.37,0 0.45,0.05 0.5,0.14 C0.55,0.05 0.63,0 0.73,0 C0.88,0 1,0.13 1,0.3 C1,0.5 0.88,0.72 0.5,1 Z"/></clipPath></defs></svg>

<div id="bg-blur"></div>
<div class="vignette"></div>
<canvas id="particles"></canvas>

<div id="judul" class="pl">__JUDUL_HTML__<span class="meta-lagu" id="meta-lagu"></span></div>

<div class="top-controls pl">
  <button id="lm" class="btn-pill lirik-sync" type="button" title="Lirik lebih awal">Lirik −</button>
  <button id="lp" class="btn-pill lirik-sync" type="button" title="Lirik lebih lambat">Lirik +</button>
  <button id="ctrl" class="btn-pill" type="button">Jeda</button>
  <button id="tutup" class="btn-pill" type="button" aria-label="Kembali ke galeri">✕</button>
</div>

<div id="main-wrap" class="pl">
  <div id="frame-box" data-f="polaroid">
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

<div id="karakter" class="pl" role="button" aria-label="Karakter lucu"><span class="k"></span><span class="item"></span></div>
<div id="gelembung" class="pl"></div>

<div id="heart-finale" class="pl">
  <div id="heart-cards"></div>
  <div id="heart-center-badge">
    <span class="big-h">♥</span>
    <span>__JUDUL_HTML__</span>
  </div>
</div>

<div id="barwrap" class="pl" aria-label="Geser posisi lagu"><div id="bar"></div></div>

<div id="overlay" class="hide pl">
  <h1 id="pesan">__PESAN__</h1>
  <button id="mulai" type="button">Putar lagi</button>
  <button id="kembali" class="btn-pill" type="button">Kembali ke galeri</button>
</div>

<div id="view-gallery">
  <header id="g-head">
    <div><h1>__NAMA_GALERI__ <span class="hh">♥</span></h1><p id="g-sub"></p></div>
    <div class="g-act">
      <button id="b-tambah" class="btn primary" type="button">+ Foto</button>
      <button id="b-anim" class="btn" type="button">✦ Animasi</button>
      <button id="b-kunci" class="btn" type="button">Kunci</button>
    </div>
  </header>
  <div id="g-empty" hidden><div class="big">♥</div><p>Belum ada foto.<br>Tambahkan foto kenangan pertamamu.</p></div>
  <div id="g-grid"></div>
  <div id="selbar"><span id="selinfo"></span><button id="sel-batal" class="btn" type="button">Batal</button><button id="sel-hapus" class="btn danger" type="button">Hapus</button><button id="sel-lanjut" class="btn primary" type="button">Lanjut ▸</button></div>
  <input type="file" id="g-file" accept="image/*" multiple hidden>
</div>

<div id="sheet" class="sheet"><div class="card">
  <h2>Pilih lagu</h2>
  <div id="lagu-list"></div>
  <h3>Gaya animasi</h3>
  <div id="tema-list" class="pil"></div>
  <h3>Bingkai foto</h3>
  <div id="bingkai-list" class="pil"></div>
  <label class="row">Ganti foto tiap <input id="detik" type="range" min="3" max="10" value="5"> <b id="detik-v">5</b> detik</label>
  <div class="row"><button id="sh-batal" class="btn" type="button">Batal</button><button id="sh-putar" class="btn primary" type="button">Putar ▸</button></div>
</div></div>

<div id="lb">
  <img id="lb-img" alt="Foto">
  <button id="lb-x" class="btn" type="button">✕</button>
  <button id="lb-p" class="btn nav" type="button" aria-label="Sebelumnya">‹</button>
  <button id="lb-n" class="btn nav" type="button" aria-label="Berikutnya">›</button>
  <div id="lb-bar"><span id="lb-c"></span><a id="lb-dl" class="btn" download="foto.jpg">Unduh</a><button id="lb-del" class="btn danger" type="button">Hapus</button></div>
</div>
<div id="toast"></div>

<script>
const CFG = {
  fotoDetik: __FOTO_DETIK__,
  maksFoto: __MAKS_FOTO__,
  jedaLoveDetik: __JEDA_LOVE_DETIK__,
  tahanLoveDetik: __TAHAN_LOVE_DETIK__,
  artis: __ARTIS_JS__,
  judulLagu: __JUDUL_LAGU_JS__
};

function renderSongMeta() {
  const el = document.getElementById('meta-lagu');
  const parts = [];
  if (CFG.judulLagu) parts.push('♪ ' + CFG.judulLagu);
  if (CFG.artis) parts.push(CFG.artis);
  el.textContent = parts.join(' — ');
}

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

const BINGKAI = { polaroid: 'Polaroid', hati: 'Hati', bulat: 'Bulat', bintang: 'Bintang', film: 'Film', lengkung: 'Jendela' };

const TEMA = {
  hati: {
    nama: 'Hujan Hati', char: ['🐻', '💗'], bingkai: 'polaroid', trans: 'zoom',
    ekspresi: ['💕', '🥰', '😍', '😘', '💗', '😊'],
    fx: { n: 36, dir: 'up', shapes: ['heart', 'petal', 'spark'], colors: ['#ff7597', '#ffb3c6', '#ffd6e0', '#fff0f3', '#ff8fab'], size: [5, 13], vy: [0.35, 1.1], wob: 0.45, alpha: [0.28, 0.7], burst: 'heart' }
  },
  bintang: {
    nama: 'Langit Bintang', char: ['🐰', '🌙'], bingkai: 'bintang', trans: 'blur',
    ekspresi: ['✨', '🥰', '🌙', '💫', '😍', '💕'],
    fx: { n: 80, dir: 'still', shapes: ['star', 'spark', 'dot'], colors: ['#fff6c9', '#ffe58a', '#cdd6ff', '#ffffff'], size: [1.5, 5], alpha: [0.5, 1], twinkle: true, shoot: true, burst: 'star' }
  },
  sakura: {
    nama: 'Sakura Cinta', char: ['🐱', '🌸'], bingkai: 'lengkung', trans: 'slide',
    ekspresi: ['🌸', '😻', '🥰', '💕', '😽', '😊'],
    fx: { n: 34, dir: 'down', shapes: ['blossom', 'petal'], colors: ['#ffc2d4', '#ffd9e4', '#fff0f4', '#ff9fbe'], size: [6, 12], vy: [0.6, 1.5], wob: 0.5, drift: 0.9, alpha: [0.5, 0.9], burst: 'blossom' }
  },
  permen: {
    nama: 'Permen Manis', char: ['🐥', '🍭'], bingkai: 'bulat', trans: 'drop',
    ekspresi: ['🍭', '😋', '💖', '🥰', '😍', '🎀'],
    fx: { n: 30, dir: 'up', shapes: ['bubble', 'dot', 'heart', 'spark'], colors: ['#ff9ecb', '#9ee7ff', '#ffe27a', '#b9a2ff', '#a5f3c3'], size: [6, 18], vy: [0.5, 1.4], wob: 0.5, alpha: [0.5, 0.9], pop: true, burst: 'bubble' }
  },
  neon: {
    nama: 'Neon Malam', char: ['🦊', '💖'], bingkai: 'film', trans: 'flip',
    ekspresi: ['💖', '😍', '🔥', '😘', '💘', '🥰'],
    fx: { n: 28, dir: 'orbit', shapes: ['firefly', 'heartline'], colors: ['#ff3d9a', '#37e8ff', '#ff8ad9', '#9b6bff'], size: [3, 8], alpha: [0.6, 1], trail: true, glow: true, burst: 'heartline' }
  },
  salju: {
    nama: 'Salju Cinta', char: ['🐧', '❄️'], bingkai: 'hati', trans: 'zin',
    ekspresi: ['❄️', '🥰', '😊', '💙', '😍', '🤗'],
    fx: { n: 60, dir: 'down', shapes: ['flake', 'dot', 'spark'], colors: ['#ffffff', '#dff3ff', '#bfe6ff'], size: [3, 9], vy: [0.4, 1.2], wob: 0.4, drift: 0.5, alpha: [0.5, 0.95], burst: 'flake' }
  }
};

const Fx = (() => {
  const cv = document.getElementById('particles');
  const c = cv.getContext('2d');
  const calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let w, h, cfg = TEMA.hati.fx, P = [], B = [], rings = [], shoots = [], tm = 0, nextShoot = 0;
  const R = (a, b) => a + Math.random() * (b - a);
  const pick = a => a[Math.floor(Math.random() * a.length)];
  const resize = () => { w = cv.width = window.innerWidth; h = cv.height = window.innerHeight; };
  window.addEventListener('resize', resize);
  resize();

  const D = {
    heart(s) { const t = s * 0.3; c.beginPath(); c.moveTo(0, t); c.bezierCurveTo(0, 0, -s, 0, -s, t); c.bezierCurveTo(-s, s * 0.7, 0, s * 0.95, 0, s * 1.2); c.bezierCurveTo(0, s * 0.95, s, s * 0.7, s, t); c.bezierCurveTo(s, 0, 0, 0, 0, t); c.fill(); },
    heartline(s) { const t = s * 0.3; c.lineWidth = 1.6; c.beginPath(); c.moveTo(0, t); c.bezierCurveTo(0, 0, -s, 0, -s, t); c.bezierCurveTo(-s, s * 0.7, 0, s * 0.95, 0, s * 1.2); c.bezierCurveTo(0, s * 0.95, s, s * 0.7, s, t); c.bezierCurveTo(s, 0, 0, 0, 0, t); c.stroke(); },
    petal(s) { c.beginPath(); c.ellipse(0, 0, s * 0.55, s, 0, 0, 6.283); c.fill(); },
    spark(s) { c.beginPath(); for (let i = 0; i < 4; i++) { const a = i * Math.PI / 2; c.lineTo(Math.cos(a) * s, Math.sin(a) * s); c.lineTo(Math.cos(a + Math.PI / 4) * s * 0.28, Math.sin(a + Math.PI / 4) * s * 0.28); } c.closePath(); c.fill(); },
    star(s) { c.beginPath(); for (let i = 0; i < 10; i++) { const a = -Math.PI / 2 + i * Math.PI / 5, r = i % 2 ? s * 0.45 : s; c.lineTo(Math.cos(a) * r, Math.sin(a) * r); } c.closePath(); c.fill(); },
    dot(s) { c.beginPath(); c.arc(0, 0, s * 0.5, 0, 6.283); c.fill(); },
    blossom(s) { for (let i = 0; i < 5; i++) { c.save(); c.rotate(i * 1.2566); c.beginPath(); c.ellipse(0, -s * 0.55, s * 0.38, s * 0.55, 0, 0, 6.283); c.fill(); c.restore(); } c.fillStyle = '#fff6f9'; c.beginPath(); c.arc(0, 0, s * 0.16, 0, 6.283); c.fill(); },
    bubble(s) { c.lineWidth = 1.5; c.beginPath(); c.arc(0, 0, s, 0, 6.283); c.save(); c.globalAlpha *= 0.22; c.fill(); c.restore(); c.stroke(); c.fillStyle = '#fff'; c.beginPath(); c.arc(-s * 0.35, -s * 0.35, s * 0.2, 0, 6.283); c.fill(); },
    firefly(s) { const g = c.createRadialGradient(0, 0, 0, 0, 0, s * 3.2); g.addColorStop(0, '#fff'); g.addColorStop(0.25, c.fillStyle); g.addColorStop(1, 'rgba(0,0,0,0)'); c.fillStyle = g; c.beginPath(); c.arc(0, 0, s * 3.2, 0, 6.283); c.fill(); },
    flake(s) { c.lineWidth = 1.2; c.lineCap = 'round'; for (let i = 0; i < 6; i++) { c.save(); c.rotate(i * 1.0472); c.beginPath(); c.moveTo(0, 0); c.lineTo(0, -s); c.moveTo(0, -s * 0.6); c.lineTo(s * 0.3, -s * 0.85); c.moveTo(0, -s * 0.6); c.lineTo(-s * 0.3, -s * 0.85); c.stroke(); c.restore(); } }
  };

  function paint(x, y, s, a, col, sh, rot) {
    c.save();
    c.translate(x, y);
    c.rotate(rot);
    c.globalAlpha = Math.max(0, Math.min(1, a));
    c.fillStyle = c.strokeStyle = col;
    if (cfg.glow) { c.shadowColor = col; c.shadowBlur = 12; }
    D[sh](s);
    c.restore();
  }

  function spawn(first) {
    const s = R(cfg.size[0], cfg.size[1]);
    const p = { x: R(0, w), y: first ? R(0, h) : cfg.dir === 'up' ? h + 24 : cfg.dir === 'down' ? -24 : R(0, h), s, vy: R(...(cfg.vy || [0, 0])), ph: R(0, 6.28), ws: R(0.015, 0.035), rot: R(0, 6.28), rs: R(-0.02, 0.02), a: R(cfg.alpha[0], cfg.alpha[1]), sh: pick(cfg.shapes), col: pick(cfg.colors) };
    if (cfg.dir === 'orbit') { p.cx = R(0, w); p.cy = R(0, h); p.r = R(30, 170); p.ang = R(0, 6.28); p.sp = R(0.003, 0.012) * (Math.random() < 0.5 ? -1 : 1); }
    if (cfg.pop) p.popY = R(h * 0.15, h * 0.8);
    return p;
  }

  function set(key) {
    cfg = TEMA[key].fx;
    P = Array.from({ length: calm ? Math.ceil(cfg.n / 3) : cfg.n }, () => spawn(true));
    B = []; rings = []; shoots = [];
    c.clearRect(0, 0, w, h);
  }

  function origin() {
    if (document.body.classList.contains('in-player')) {
      const r = document.getElementById('frame-box').getBoundingClientRect();
      return [r.left + r.width / 2, r.top + r.height / 2];
    }
    return [w / 2, h / 2];
  }

  function burst(n, big) {
    if (calm) return;
    const [ox, oy] = origin();
    for (let i = 0; i < n; i++) {
      const a = R(0, 6.283), v = R(1.5, big ? 8 : 5);
      B.push({ x: ox, y: oy, vx: Math.cos(a) * v, vy: Math.sin(a) * v - 1.2, s: R(4, big ? 13 : 10), rot: R(0, 6.28), rs: R(-0.08, 0.08), a: 1, col: pick(cfg.colors), sh: Math.random() < 0.7 ? cfg.burst : pick(cfg.shapes) });
    }
  }

  function finale() {
    burst(40, true);
    setTimeout(() => burst(40, true), 700);
    setTimeout(() => burst(40, true), 1500);
  }

  function loop(t) {
    tm = t;
    if (cfg.trail) {
      c.globalCompositeOperation = 'destination-out';
      c.fillStyle = 'rgba(0,0,0,0.16)';
      c.fillRect(0, 0, w, h);
      c.globalCompositeOperation = 'source-over';
    } else c.clearRect(0, 0, w, h);

    for (const p of P) {
      p.ph += p.ws; p.rot += p.rs;
      let a = p.a;
      if (cfg.dir === 'up') { p.y -= p.vy; p.x += Math.sin(p.ph) * cfg.wob; }
      else if (cfg.dir === 'down') { p.y += p.vy; p.x += Math.sin(p.ph) * cfg.wob + (cfg.drift || 0) * (0.6 + Math.sin(t * 0.0007)); }
      else if (cfg.dir === 'still') { p.y -= 0.04; a = p.a * (0.45 + 0.55 * Math.sin(p.ph * 3)); }
      else { p.ang += p.sp; p.cy -= 0.12; p.x = p.cx + Math.cos(p.ang) * p.r; p.y = p.cy + Math.sin(p.ang * 1.3) * p.r * 0.6; if (p.cy < -80) { p.cy = h + 80; p.cx = R(0, w); } }
      if (cfg.pop && p.y < p.popY) { rings.push({ x: p.x, y: p.y, r: p.s, a: 0.8, col: p.col }); Object.assign(p, spawn(false)); }
      else if (cfg.dir === 'up' && p.y < -30) Object.assign(p, spawn(false));
      else if (cfg.dir === 'down' && (p.y > h + 30 || p.x > w + 40)) Object.assign(p, spawn(false), { y: -24 });
      else if (cfg.dir === 'still' && p.y < -10) p.y = h + 10;
      if (p.x < -40) p.x = w + 30;
      paint(p.x, p.y, p.s, a, p.col, p.sh, p.rot);
    }

    for (let i = rings.length - 1; i >= 0; i--) {
      const g = rings[i];
      g.r += 1.6; g.a -= 0.035;
      if (g.a <= 0) { rings.splice(i, 1); continue; }
      c.save(); c.globalAlpha = g.a; c.strokeStyle = g.col; c.lineWidth = 2; c.beginPath(); c.arc(g.x, g.y, g.r, 0, 6.283); c.stroke(); c.restore();
    }

    for (let i = B.length - 1; i >= 0; i--) {
      const b = B[i];
      b.x += b.vx; b.y += b.vy; b.vy += 0.05; b.vx *= 0.99; b.rot += b.rs; b.a -= 0.011;
      if (b.a <= 0) { B.splice(i, 1); continue; }
      paint(b.x, b.y, b.s, b.a, b.col, b.sh, b.rot);
    }

    if (cfg.shoot && !calm) {
      if (t > nextShoot) { shoots.push({ x: R(w * 0.3, w), y: R(0, h * 0.35), vx: -R(8, 12), vy: R(3, 5), l: 1 }); nextShoot = t + R(2200, 5200); }
      for (let i = shoots.length - 1; i >= 0; i--) {
        const s = shoots[i];
        s.x += s.vx; s.y += s.vy; s.l -= 0.014;
        if (s.l <= 0) { shoots.splice(i, 1); continue; }
        const g = c.createLinearGradient(s.x, s.y, s.x - s.vx * 9, s.y - s.vy * 9);
        g.addColorStop(0, 'rgba(255,255,255,' + s.l + ')');
        g.addColorStop(1, 'rgba(255,255,255,0)');
        c.strokeStyle = g; c.lineWidth = 2; c.beginPath(); c.moveTo(s.x, s.y); c.lineTo(s.x - s.vx * 9, s.y - s.vy * 9); c.stroke();
      }
    }
    requestAnimationFrame(loop);
  }

  set('hati');
  requestAnimationFrame(loop);
  return { set, burst, finale };
})();

const kar = document.getElementById('karakter');
const gel = document.getElementById('gelembung');
let temaAktif = 'hati', bingkaiPilih = 'auto', gelTimer = 0;

function setTema(k) {
  temaAktif = k;
  const t = TEMA[k];
  document.body.dataset.tema = k;
  document.body.dataset.trans = t.trans;
  kar.querySelector('.k').textContent = t.char[0];
  kar.querySelector('.item').textContent = t.char[1];
  Fx.set(k);
}

function terapkanBingkai(p) {
  let b = bingkaiPilih === 'auto' ? TEMA[temaAktif].bingkai : bingkaiPilih;
  if (b === 'mix') { const ks = Object.keys(BINGKAI); b = ks[p % ks.length]; }
  frameBox.dataset.f = b;
  document.body.dataset.bk = b;
}

function bicara(txt) {
  gel.textContent = txt;
  gel.classList.add('on');
  clearTimeout(gelTimer);
  gelTimer = setTimeout(() => gel.classList.remove('on'), 4200);
}

function pesanAcak() {
  const l = TEMA[temaAktif].ekspresi;
  const a = l[Math.floor(Math.random() * l.length)];
  return Math.random() < 0.4 ? a + l[Math.floor(Math.random() * l.length)] : a;
}

function lompatKar() {
  kar.classList.remove('lompat');
  void kar.offsetWidth;
  kar.classList.add('lompat');
}

function reaksi() {
  Fx.burst(6);
  lompatKar();
}

kar.addEventListener('click', () => { bicara(pesanAcak()); Fx.burst(16); lompatKar(); });
setInterval(() => { if (started && !inFinale) bicara(pesanAcak()); }, 9000);

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
  return Math.max(last, 20, lines.length ? 0 : fotos.length * CFG.fotoDetik);
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
  terapkanBingkai(p);

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
  Fx.finale();

  const count = Math.min(40, Math.max(fotos.length, 16));
  const minDim = Math.min(window.innerWidth, window.innerHeight);
  const scaleX = Math.min(window.innerWidth * 0.34, minDim * 0.42);
  const scaleY = Math.min(window.innerHeight * 0.28, minDim * 0.36);
  const cardSize = Math.max(34, Math.min(76, minDim * 0.11 * Math.sqrt(16 / count)));

  const els = [];
  for (let i = 0; i < count; i++) {
    const angle = (i / count) * Math.PI * 2;
    const pt = heartPoint(angle, scaleX, scaleY);
    const rot = ((i % 2 === 0 ? 1 : -1) * (4 + (i % 5) * 2.5)).toFixed(1) + 'deg';
    const src = fotos[Math.floor(i * fotos.length / count) % fotos.length];

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

  const stepMs = Math.max(120, Math.min(CFG.jedaLoveDetik * 1000, 9000 / count));
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
      if (idx >= 0) reaksi();
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

let lastPlay = null;
async function mulaiPemutar(urls, lagu, detik, gaya) {
  gaya = gaya || {};
  lastPlay = { urls, lagu, detik, gaya };
  document.body.classList.add('in-player');
  clearFinale();
  overlay.classList.add('hide');
  bingkaiPilih = gaya.bingkai || 'auto';
  setTema(TEMA[gaya.tema] ? gaya.tema : 'hati');
  setTimeout(() => { if (started) bicara(pesanAcak()); }, 1500);
  if (audio) { audio.pause(); audio = null; }
  fotos = urls; CFG.fotoDetik = detik;
  hasLrc = false; lines = []; nudgeSec = 0; usingAudio = false;
  parseLyrics(lagu ? lagu.lirik : '');
  CFG.judulLagu = lagu ? lagu.judul : ''; CFG.artis = lagu ? lagu.artis : '';
  renderSongMeta();
  if (lagu && lagu.audio) {
    const a = new Audio(lagu.audio);
    audio = a; usingAudio = true;
    a.addEventListener('ended', () => { if (a === audio) finish(); });
    a.addEventListener('error', () => { if (a === audio) { usingAudio = false; audio = null; base = 0; startPerf = performance.now(); } });
  }
  curLine = -2; curPhoto = -1; base = 0; startPerf = performance.now();
  started = true; playing = true; ctrlBtn.textContent = 'Jeda';
  if (usingAudio) {
    try { await audio.play(); }
    catch (e) { usingAudio = false; startPerf = performance.now(); }
  }
}

function keluarPemutar() {
  started = false; playing = false; usingAudio = false;
  clearFinale();
  if (audio) { audio.pause(); audio = null; }
  overlay.classList.add('hide');
  bgBlur.style.backgroundImage = '';
  gel.classList.remove('on');
  setTema('hati');
  document.body.classList.remove('in-player');
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

ctrlBtn.addEventListener('click', toggle);
mulaiBtn.addEventListener('click', () => { if (lastPlay) mulaiPemutar(lastPlay.urls, lastPlay.lagu, lastPlay.detik, lastPlay.gaya); });
document.getElementById('kembali').addEventListener('click', keluarPemutar);
document.getElementById('tutup').addEventListener('click', keluarPemutar);
document.getElementById('lm').addEventListener('click', () => adjustSync(-0.2));
document.getElementById('lp').addEventListener('click', () => adjustSync(0.2));
barwrap.addEventListener('click', e => {
  const r = barwrap.getBoundingClientRect();
  seekTo(((e.clientX - r.left) / r.width) * dur());
});

const $ = s => document.querySelector(s);
const G = { items: [], sel: [], mode: false, anim: false, lagu: [], lb: -1 };
const grid = $('#g-grid');
const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
function toast(m, ms = 2600) {
  const t = $('#toast'); t.textContent = m; t.classList.add('show');
  clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove('show'), ms);
}

async function api(url, opt) {
  const r = await fetch(url, opt);
  if (r.status === 401) { location.reload(); throw new Error('login'); }
  return r;
}

async function muat() {
  const r = await api('/api/foto');
  if (!r.ok) { toast('Penyimpanan online (Blob) belum tersambung'); G.items = []; render(); return; }
  const d = await r.json();
  G.items = d.foto.map(f => ({ id: f.id, added: f.added, url: '/api/f/foto/' + f.id, turl: '/api/f/thumb/' + f.id }));
  G.sel = G.sel.filter(id => G.items.some(i => i.id === id));
  render();
}

function render() {
  grid.innerHTML = G.items.map((it, i) =>
    `<figure class="ph" data-id="${it.id}" style="--i:${Math.min(i, 20)}"><img src="${it.turl}" alt="Foto ${i + 1}" loading="lazy"><button class="cek" type="button" aria-label="Pilih foto"></button></figure>`
  ).join('');
  $('#g-empty').hidden = G.items.length > 0;
  ui();
}

function ui() {
  document.body.classList.toggle('selmode', G.mode);
  grid.querySelectorAll('.ph').forEach(f => {
    const n = G.sel.indexOf(f.dataset.id);
    f.classList.toggle('sel', n >= 0);
    f.querySelector('.cek').textContent = n >= 0 ? n + 1 : '';
  });
  $('#g-sub').textContent = G.items.length + ' foto • tersimpan online';
  $('#selinfo').textContent = G.anim ? `Pilih foto (${G.sel.length})` : `${G.sel.length} dipilih`;
  $('#sel-hapus').hidden = G.anim;
  $('#sel-hapus').disabled = !G.sel.length;
  $('#sel-lanjut').disabled = !G.sel.length;
}

function toggleSel(id) {
  const i = G.sel.indexOf(id);
  if (i >= 0) G.sel.splice(i, 1); else G.sel.push(id);
  ui();
}

grid.addEventListener('click', e => {
  const f = e.target.closest('.ph'); if (!f) return;
  const id = f.dataset.id;
  if (e.target.closest('.cek')) { if (!G.mode) { G.mode = true; G.anim = false; } toggleSel(id); }
  else if (G.mode) toggleSel(id);
  else bukaLB(G.items.findIndex(i => i.id === id));
});

$('#b-anim').addEventListener('click', () => {
  if (!G.items.length) return toast('Tambahkan foto dulu ya');
  G.mode = true; G.anim = true; ui(); toast('Ketuk foto sesuai urutan yang kamu mau');
});
$('#sel-batal').addEventListener('click', () => { G.mode = false; G.anim = false; G.sel = []; ui(); });
$('#sel-hapus').addEventListener('click', () => hapus(G.sel.slice()));
$('#b-kunci').addEventListener('click', async () => { await fetch('/api/logout', { method: 'POST' }); location.reload(); });

function muatGbr(f) {
  return new Promise((ok, no) => {
    const u = URL.createObjectURL(f), im = new Image();
    im.onload = () => { im._u = u; ok(im); };
    im.onerror = () => { URL.revokeObjectURL(u); no(); };
    im.src = u;
  });
}
function kecil(im, maks, q) {
  const r = Math.min(1, maks / Math.max(im.naturalWidth, im.naturalHeight));
  const w = Math.round(im.naturalWidth * r), h = Math.round(im.naturalHeight * r);
  const c = document.createElement('canvas'); c.width = w; c.height = h;
  const x = c.getContext('2d'); x.fillStyle = '#fff'; x.fillRect(0, 0, w, h); x.drawImage(im, 0, 0, w, h);
  return new Promise(ok => c.toBlob(ok, 'image/jpeg', q));
}
$('#b-tambah').addEventListener('click', () => $('#g-file').click());
$('#g-file').addEventListener('change', async e => {
  const fs = [...e.target.files]; e.target.value = '';
  let ok = 0, err = '';
  for (let i = 0; i < fs.length; i++) {
    toast(`Mengupload ${i + 1} / ${fs.length}…`, 60000);
    try {
      const im = await muatGbr(fs[i]);
      const fd = new FormData();
      fd.append('foto', await kecil(im, 1800, 0.86), 'f.jpg');
      fd.append('thumb', await kecil(im, 520, 0.8), 't.jpg');
      URL.revokeObjectURL(im._u);
      const r = await api('/api/foto', { method: 'POST', body: fd });
      if (r.ok) ok++; else err = 'Upload gagal, cek koneksi Blob';
    } catch (x) { err = err || 'Ada foto yang tidak bisa dibaca'; }
  }
  await muat();
  toast(ok ? `${ok} foto tersimpan ♥` : (err || 'Tidak ada foto yang tersimpan'));
});

async function hapus(ids) {
  if (!ids.length || !confirm(`Hapus ${ids.length} foto? Ini tidak bisa dibatalkan.`)) return;
  let gagal = 0;
  for (const id of ids) {
    const r = await api('/api/foto/' + id, { method: 'DELETE' });
    if (!r.ok) gagal++;
  }
  G.sel = []; G.mode = false; G.anim = false; G.lb = -1; $('#lb').classList.remove('on');
  await muat();
  toast(gagal ? 'Sebagian foto gagal dihapus' : 'Foto dihapus');
}

function tampilLB() {
  const it = G.items[G.lb]; if (!it) return;
  $('#lb-img').src = it.url; $('#lb-dl').href = it.url;
  $('#lb-c').textContent = `${G.lb + 1} / ${G.items.length}`;
}
function bukaLB(i) { if (i < 0) return; G.lb = i; $('#lb').classList.add('on'); tampilLB(); }
function geserLB(d) { if (G.lb < 0) return; G.lb = (G.lb + d + G.items.length) % G.items.length; tampilLB(); }
function tutupLB() { G.lb = -1; $('#lb').classList.remove('on'); }
$('#lb-x').addEventListener('click', tutupLB);
$('#lb-p').addEventListener('click', () => geserLB(-1));
$('#lb-n').addEventListener('click', () => geserLB(1));
$('#lb-del').addEventListener('click', () => { const it = G.items[G.lb]; if (it) hapus([it.id]); });
let sx = null;
$('#lb').addEventListener('pointerdown', e => { sx = e.clientX; });
$('#lb').addEventListener('pointerup', e => { if (sx !== null && Math.abs(e.clientX - sx) > 60) geserLB(e.clientX < sx ? 1 : -1); sx = null; });

function renderPilihan() {
  let tm = 'hati', bk = 'auto';
  try { tm = localStorage.getItem('tema') || 'hati'; bk = localStorage.getItem('bingkai') || 'auto'; } catch (e) {}
  if (!TEMA[tm]) tm = 'hati';
  $('#tema-list').innerHTML = Object.entries(TEMA).map(([k, t]) =>
    `<label class="opsi"><input type="radio" name="tm" value="${k}" ${k === tm ? 'checked' : ''}><span class="ik">${t.char[0]}</span><b>${t.nama}</b></label>`
  ).join('');
  const bks = [['auto', 'Sesuai gaya']].concat(Object.entries(BINGKAI), [['mix', 'Acak']]);
  $('#bingkai-list').innerHTML = bks.map(([k, n]) =>
    `<label class="opsi kecil"><input type="radio" name="bk" value="${k}" ${k === bk ? 'checked' : ''}><b>${n}</b></label>`
  ).join('');
}

function bukaSheet() {
  let last = ''; try { last = localStorage.getItem('lagu-terakhir') || ''; } catch (e) {}
  const pilih = G.lagu.findIndex(s => s.id === last);
  const cek = i => (i === (pilih >= 0 ? pilih : 0) ? 'checked' : '');
  $('#lagu-list').innerHTML = G.lagu.map((s, i) =>
    `<label class="lagu"><input type="radio" name="lg" value="${i}" ${cek(i)}><span><b>${esc(s.judul)}</b><small>${esc(s.artis || '')}${s.artis ? ' • ' : ''}${s.lirik ? 'ada lirik' : 'tanpa lirik'}</small></span></label>`
  ).join('') +
  `<label class="lagu"><input type="radio" name="lg" value="-1" ${G.lagu.length ? '' : 'checked'}><span><b>Tanpa lagu</b><small>foto saja</small></span></label>`;
  $('#detik').value = CFG.fotoDetik; $('#detik-v').textContent = CFG.fotoDetik;
  renderPilihan();
  $('#sheet').classList.add('on');
}
$('#detik').addEventListener('input', e => { $('#detik-v').textContent = e.target.value; });
$('#sel-lanjut').addEventListener('click', bukaSheet);
$('#sh-batal').addEventListener('click', () => $('#sheet').classList.remove('on'));
$('#sheet').addEventListener('click', e => { if (e.target.id === 'sheet') $('#sheet').classList.remove('on'); });
$('#sh-putar').addEventListener('click', () => {
  const v = +(document.querySelector('input[name="lg"]:checked') || { value: -1 }).value;
  const lagu = G.lagu[v] || null;
  try { if (lagu) localStorage.setItem('lagu-terakhir', lagu.id); } catch (e) {}
  const urls = G.sel.map(id => (G.items.find(i => i.id === id) || {}).url).filter(Boolean);
  $('#sheet').classList.remove('on');
  G.mode = false; G.anim = false; ui();
  const tema = (document.querySelector('input[name="tm"]:checked') || { value: 'hati' }).value;
  const bingkai = (document.querySelector('input[name="bk"]:checked') || { value: 'auto' }).value;
  try { localStorage.setItem('tema', tema); localStorage.setItem('bingkai', bingkai); } catch (e) {}
  mulaiPemutar(urls, lagu, +$('#detik').value, { tema, bingkai });
});

window.addEventListener('keydown', e => {
  if (document.body.classList.contains('in-player')) {
    if (e.code === 'Escape') keluarPemutar();
    else if (started && e.code === 'Space') { e.preventDefault(); toggle(); }
    else if (started && e.code === 'ArrowRight') seekTo(clock() + 5);
    else if (started && e.code === 'ArrowLeft') seekTo(clock() - 5);
    else if (e.key === '[') adjustSync(-0.2);
    else if (e.key === ']') adjustSync(0.2);
    return;
  }
  if (G.lb >= 0) {
    if (e.code === 'Escape') tutupLB();
    else if (e.code === 'ArrowRight') geserLB(1);
    else if (e.code === 'ArrowLeft') geserLB(-1);
  } else if (e.code === 'Escape' && G.mode) $('#sel-batal').click();
});

(async function init() {
  try {
    const r = await fetch('/data');
    if (r.status === 401) { location.reload(); return; }
    const d = await r.json();
    G.lagu = d.lagu || [];
    if (d.peran === 'lihat') document.body.classList.add('viewer');
  } catch (e) {}
  try { await muat(); } catch (e) {}
})();
requestAnimationFrame(tick);
</script>
</body>
</html>
"""


@app.get("/")
def index():
    if not _sudah_login():
        page = (PIN_HTML.replace("__NAMA__", html.escape(NAMA_GALERI))
                .replace("__PANJANG__", str(len(PIN))))
    else:
        page = (
            HTML.replace("__JUDUL_HTML__", html.escape(JUDUL))
            .replace("__NAMA_GALERI__", html.escape(NAMA_GALERI))
            .replace("__ARTIS_JS__", '""')
            .replace("__JUDUL_LAGU_JS__", '""')
            .replace("__PESAN__", html.escape(PESAN_AWAL))
            .replace("__FOTO_DETIK__", str(FOTO_GANTI_DETIK))
            .replace("__MAKS_FOTO__", "0")
            .replace("__JEDA_LOVE_DETIK__", str(JEDA_FOTO_LOVE_DETIK))
            .replace("__TAHAN_LOVE_DETIK__", str(TAHAN_LOVE_DETIK))
        )
    return Response(page, mimetype="text/html", headers={"Cache-Control": "no-store"})


if __name__ == "__main__":
    if not PIN.isdigit():
        print("PERINGATAN: PIN sebaiknya angka saja.")
    if PIN_PACAR and len(PIN_PACAR) != len(PIN):
        print("PERINGATAN: PIN_PACAR harus sama panjang dengan PIN.")
    print("Lagu  :", LAGU_DIR)
    app.run(host="0.0.0.0", port=5000, debug=True)