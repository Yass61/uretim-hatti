"""Telegram onayından önceki son kapı. Yasin'e yalnız bu denetimden geçen video gider.

İki katman:
  1. Ölçüm (ücretsiz, her zaman çalışır): yazı sığıyor mu, altyazı okunacak kadar ekranda kalıyor mu,
     kare boş ya da karanlık mı, video ölçüleri ve ses düzeyi doğru mu.
  2. Göz (görme modeli; GEMINI_API_KEY varsa): her örnek kare bir denetim listesinden geçer. Model her
     madde için önce ne gördüğünü yazar, sonra hüküm verir; kanıtsız cevap sayılmaz ve yeniden sorulur.
     Puanı kod verir: 10, her büyük hata için eksi 3, her küçük hata için eksi 1. Kare 8 ve üstüyle geçer.

Denetim listesi fikri AI Video Factory'den (MIT, Ersin Koç) alındı; maddeler bu projenin kırmızı
çizgilerine göre yeniden yazıldı (yüz tasviri, model üretimi yazı, dönem dışı nesne).
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import subprocess

import numpy as np
from PIL import Image, ImageDraw

MADDELER = [
    ("yuz", "büyük", "İnsan yüzü ya da önden görünen insan figürü yok (en fazla arkadan, uzak siluet)."),
    ("hale", "büyük", "Hiçbir figürün çevresinde hale, nur ya da kutsallık işareti yok."),
    ("uretilmis_yazi", "büyük", "Resmin kendi içinde harf, yazı, hat ya da tabela yok (sonradan bindirilen altyazı ve kaynak rozeti sayılmaz)."),
    ("donem", "büyük", "Modern nesne, kubbe, minare, hilal ya da 7. yüzyıl Hicaz'ına uymayan yapı yok."),
    ("anlatim", "küçük", "Görüntü, verilen cümlede anlatılanla ilgili; alakasız bir sahne değil."),
    ("altyazi", "büyük", "Altyazı varsa tam görünüyor: kesilmemiş, taşmamış, zeminden ayrışıyor."),
    ("rozet", "küçük", "Kaynak rozeti varsa okunuyor ve altyazıyla üst üste binmiyor."),
    ("bozulma", "büyük", "Yırtılma, erimiş şekil, çift kenar, bulanık leke gibi üretim ya da hareket bozulması yok."),
    ("kompozisyon", "küçük", "Kare boş değil ve aşırı kalabalık değil; bakışın duracağı bir yer var."),
    ("isik", "küçük", "Kare aşırı karanlık ya da patlak değil; ayrıntı seçiliyor."),
]
ISTEM = """Sen bir video kalite denetçisisin. Bu kare, 7. yüzyıl Medine'sinde geçen dinî bir kısa videodan alındı.
O anda seslendirilen cümle: «{cumle}»

Aşağıdaki her madde için ÖNCE karede ne gördüğünü bir cümleyle yaz, SONRA hüküm ver.
Hüküm: "geçti" ya da "kaldı". Görmediğin şeyi yazma; emin değilsen gördüğünü anlat ve "kaldı" de.

{maddeler}

Yalnız şu JSON'u döndür:
{{"maddeler": [{{"ad": "<madde adı>", "gordugum": "<karede gördüğün>", "hukum": "geçti|kaldı"}}]}}"""
GECME = 8


# --------------------------------------------------------------------- ölçüm
def yazi_olc(cumleler: list[dict]) -> list[str]:
    """Altyazı öbekleri sığıyor mu ve okunacak kadar ekranda mı? (kurgu.cizelge çıktısı üzerinde)"""
    from kurgu import F_KALIN, F_ORTA, yazi

    d, sorun = ImageDraw.Draw(Image.new("RGB", (8, 8))), []
    for c in cumleler:
        if c.get("kaynak") and d.textlength(c["kaynak"], font=yazi(F_ORTA, 34)) + 56 > 1000:
            sorun.append(f"{c['id']}: kaynak rozeti kareye sığmıyor")
        if not c.get("altyazi", True):
            continue
        for p in c.get("parcalar", []):
            if d.textlength(p["metin"], font=yazi(F_KALIN, 48)) > 940:
                sorun.append(f"{c['id']}: altyazı en küçük boyutta bile sığmıyor: «{p['metin']}»")
            sure = p["bit"] - p["bas"]
            if sure < 0.45:
                sorun.append(f"{c['id']}: «{p['metin']}» yalnız {sure:.2f} sn ekranda")
            elif len(p["metin"]) / sure > 26:
                sorun.append(f"{c['id']}: «{p['metin']}» okunamayacak kadar hızlı ({len(p['metin']) / sure:.0f} harf/sn)")
    return sorun


def kare_olc(kare: np.ndarray) -> list[str]:
    gri = kare.astype(np.float32).mean(axis=2)
    sorun = []
    if gri.mean() < 16:
        sorun.append("kare neredeyse siyah")
    elif gri.mean() > 238:
        sorun.append("kare neredeyse beyaz")
    if gri.std() < 6:
        sorun.append("kare düz renk; görüntü yok")
    return sorun


def gorsel_puani(yol: str) -> tuple[float, list[str]]:
    """Görme modeli yokken aday görseli ölçümle sıralar: netlik yüksek, altyazı bandı sakin olan öne geçer."""
    import cv2

    im = np.asarray(Image.open(yol).convert("RGB"))
    sorun = kare_olc(im)
    h, w = im.shape[:2]
    if w < 700 or h < 1200:
        sorun.append(f"çözünürlük düşük ({w}x{h})")
    if not 0.5 <= w / h <= 0.62:
        sorun.append(f"dikey 9:16 değil ({w}x{h})")
    gri = cv2.cvtColor(im, cv2.COLOR_RGB2GRAY)
    net = float(cv2.Laplacian(gri, cv2.CV_64F).var())
    bant = gri[int(h * 0.47):int(h * 0.63)]
    bant_ayrinti = float(cv2.Laplacian(bant, cv2.CV_64F).var())
    puan = min(net / 150.0, 5.0) + max(0.0, 5.0 - bant_ayrinti / max(net, 1.0) * 5.0) - 3.0 * len(sorun)
    return round(puan, 2), sorun


def video_olc(yol: str, beklenen_sure: float, ses_var: bool) -> list[str]:
    c = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "stream=codec_type,width,height,r_frame_rate:format=duration", "-of", "json", yol],
                       capture_output=True, text=True)
    if c.returncode != 0:
        return [f"video okunamıyor: {c.stderr.strip()[:200]}"]
    b = json.loads(c.stdout)
    v = next((s for s in b["streams"] if s["codec_type"] == "video"), None)
    sorun = []
    if not v:
        return ["video akışı yok"]
    if (v["width"], v["height"]) != (1080, 1920):
        sorun.append(f"ölçü {v['width']}x{v['height']}; 1080x1920 olmalı")
    if v["r_frame_rate"] not in ("30/1", "30000/1001"):
        sorun.append(f"kare hızı {v['r_frame_rate']}")
    sure = float(b["format"]["duration"])
    if abs(sure - beklenen_sure) > 1.0:
        sorun.append(f"süre {sure:.1f} sn; beklenen {beklenen_sure:.1f} sn")
    if not any(s["codec_type"] == "audio" for s in b["streams"]):
        sorun.append("ses akışı yok")
    elif ses_var:
        sorun += ses_olc(yol)
    return sorun


def ses_olc(yol: str) -> list[str]:
    """Ses düzeyi: hedef -14 LUFS (referans video -13,9), tepe -1 dB'yi aşmamalı."""
    c = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", yol, "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    son = c.stderr[c.stderr.rfind("Summary:"):]
    i = re.search(r"I:\s*(-?[\d.]+) LUFS", son)
    tepe = re.search(r"Peak:\s*(-?[\d.]+) dBFS", son)
    if not i:
        return ["ses düzeyi ölçülemedi"]
    sorun, lufs = [], float(i.group(1))
    if lufs < -40:
        sorun.append("ses neredeyse sessiz")
    elif not -16.5 <= lufs <= -12.0:
        sorun.append(f"ses düzeyi {lufs:.1f} LUFS; hedef -14")
    if tepe and float(tepe.group(1)) > -0.5:
        sorun.append(f"ses tepesi {tepe.group(1)} dB; kırpılma riski")
    return sorun


# ----------------------------------------------------------------------- göz
def puanla(cevap: dict, maddeler=MADDELER) -> tuple[int | None, list[str]]:
    """(puan, bulgular). Kanıtsız ya da eksik cevapta puan None döner: cevap geçersizdir."""
    gelen = {m.get("ad"): m for m in (cevap.get("maddeler") or []) if isinstance(m, dict)}
    puan, bulgu = 10, []
    for ad, agirlik, _ in maddeler:
        m = gelen.get(ad)
        if not m or m.get("hukum") not in ("geçti", "kaldı") or len((m.get("gordugum") or "").strip()) < 12:
            return None, [f"{ad}: kanıtsız ya da eksik cevap"]
        if m["hukum"] == "kaldı":
            puan -= 3 if agirlik == "büyük" else 1
            bulgu.append(f"{ad} ({agirlik}): {m['gordugum'].strip()}")
    return puan, bulgu


def _gemini(jpeg: bytes, istem: str, model: str) -> dict:
    import requests

    govde = {"contents": [{"parts": [{"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(jpeg).decode()}},
                                     {"text": istem}]}],
             "generationConfig": {"temperature": 0, "maxOutputTokens": 4096, "responseMimeType": "application/json"}}
    r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                      params={"key": os.environ["GEMINI_API_KEY"]}, json=govde, timeout=120)
    if r.status_code >= 400:
        raise RuntimeError(f"{r.status_code}: {r.text[:200]}")
    parcalar = ((r.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    return json.loads("".join(p.get("text", "") for p in parcalar))


def goz(kare: np.ndarray | str, cumle: str, model: str, sor=_gemini) -> tuple[int | None, list[str]]:
    """Bir kareyi denetim listesinden geçirir. Geçersiz cevapta bir kez daha sorar."""
    im = Image.open(kare).convert("RGB") if isinstance(kare, str) else Image.fromarray(kare)
    im.thumbnail((720, 1280))
    tampon = io.BytesIO()
    im.save(tampon, "JPEG", quality=88)
    istem = ISTEM.format(cumle=cumle or "(cümle yok)",
                         maddeler="\n".join(f"- {ad}: {aciklama}" for ad, _, aciklama in MADDELER))
    son = (None, ["cevap alınamadı"])
    for _ in range(2):
        try:
            son = puanla(sor(tampon.getvalue(), istem, model))
        except Exception as hata:
            son = (None, [f"görme modeli hatası: {str(hata)[:160]}"])
        if son[0] is not None:
            break
    return son


def ornek_anlar(planlar: list[dict], adet: int) -> list[float]:
    """Her plandan bir an (ortası), en çok `adet` kare; kartlar da dahil."""
    anlar = [(p["bas"] + p["bit"]) / 2 for p in planlar]
    if len(anlar) > adet:
        adim = len(anlar) / adet
        anlar = [anlar[int(i * adim)] for i in range(adet)]
    return anlar


def rapor_metni(sonuc: dict) -> str:
    s = [("✅ Denetim geçti" if sonuc["gecti"] else "⛔ Denetim kaldı")]
    if sonuc.get("goz") == "yok":
        s.append("Göz denetimi yapılmadı (görme modeli anahtarı yok); yalnız ölçümler yapıldı.")
    elif sonuc.get("puanlar"):
        p = [x for x in sonuc["puanlar"] if x is not None]
        s.append(f"Kare puanları: en düşük {min(p) if p else '—'}, ortalama {sum(p) / len(p):.1f}" if p else "Kareler puanlanamadı")
    s += [f"- {x}" for x in sonuc["sorunlar"][:12]]
    return "\n".join(s)
