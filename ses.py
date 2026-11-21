"""Anlatım sesini üretir ve cümle zamanlarını çıkarır.

Varsayılan: her cümle ayrı üretilir. ayar.ses.blok=true ise ayet araları arasındaki paragraf tek parça
okunur (tonlama korunur) ve sessizliklerden cümlelere bölünür; bölünemezse cümle cümle üretime dönülür.
Cümle cümle üretimde: süreler ölçülür (tahmin edilmez), düzeltilen tek cümle yeniden ödenir,
gerisi önbellekten gelir. ElevenLabs'te önceki ve sonraki cümle bağlam olarak verilir; tonlama
cümleden cümleye kopmaz. Ses motoruna metnin okunuşu gider (okunus.py); altyazı değişmez.

Ritim (referans videonun ölçümünden): 0,9 sn sessiz açılış, cümle arası 0,55 sn, müzik yatağı yok.
"""
from __future__ import annotations

import json
import os
import subprocess

from kapi import Kapi
from okunus import okunus

ACILIS_SN, ARA_SN, KAPANIS_SN = 0.9, 0.55, 0.6
# Tahminî birim fiyatlar (USD / 1000 harf); ayar.json'daki "fiyatlar" ile ezilir.
FIYAT = {"elevenlabs": 0.08, "google": 0.0, "azure": 0.016, "gemini": 0.02}


def _sure(yol: str) -> float:
    c = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", yol],
                       capture_output=True, text=True, check=True)
    return float(c.stdout.strip())


def _kirp(giris: str, cikis: str) -> None:
    """Baştaki ve sondaki sessizliği atar; her cümle aynı biçimde (48 kHz mono wav) kaydedilir."""
    sus = "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.03"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", giris,
                    "-af", f"{sus},areverse,{sus},areverse,aresample=48000", "-ac", "1", cikis], check=True)


def uret(bolum: dict, ayar: dict, klasor: str, kapi: Kapi, motorlar: dict | None = None) -> dict:
    """bolum["ses"] alanını döner: {"dosya", "zamanlar": {cumle_id: [bas, bit]}, "motor", "ses"}."""
    if motorlar is None:
        from ses_provasi import MOTORLAR as motorlar
    s = ayar["ses"]
    islev, sirlar = motorlar[s["motor"]]
    eksik = [x for x in sirlar if not os.environ.get(x)]
    if eksik:
        raise RuntimeError(f"ses motoru anahtarı yok: {', '.join(eksik)}")
    os.makedirs(klasor, exist_ok=True)
    fiyat = (ayar.get("fiyatlar") or {}).get(s["motor"], FIYAT.get(s["motor"], 0.0))
    konusulan = [c for c in bolum["cumleler"] if not c.get("bekle")]
    parcalar, zamanlar, t = [], {}, ACILIS_SN
    hazir: dict[str, str] = {}
    if s.get("blok"):                                   # bekleme araları arasındaki cümleler tek parça okunur
        gruplar, cur = [], []
        for c in bolum["cumleler"]:
            if c.get("bekle"):
                gruplar.append(cur); cur = []
            else:
                cur.append(c)
        gruplar.append(cur)
        for gi, grup in enumerate(g for g in gruplar if len(g) > 1):
            metinler = [okunus(c["metin"]) for c in grup]
            metin = " ".join(metinler)
            girdi = {"motor": s["motor"], "ses": s["ses"], "model": s.get("model"), "stil": s.get("stil"),
                     "metin": metin, "blok": True}
            ham = kapi.cagir("ses", girdi, "mp3", fiyat * len(metin) / 1000, lambda m=metin: islev(m, dict(s)))
            blok = os.path.join(klasor, f"blok_{gi}.wav")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", ham, "-ar", "48000", "-ac", "1", blok],
                           check=True)
            yollar = bol(blok, metinler, klasor, f"blok_{gi}")
            if yollar:
                hazir.update({c["id"]: y for c, y in zip(grup, yollar)})
    for c in bolum["cumleler"]:
        if c.get("bekle"):                              # ayet kartı / tilavet aralığı
            zamanlar[c["id"]] = [round(t, 3), round(t + c["bekle"], 3)]
            parcalar.append(("sus", c["bekle"] + ARA_SN))
            t += c["bekle"] + ARA_SN
            continue
        i = konusulan.index(c)
        metin = okunus(c["metin"])
        aday = {**s, "onceki": okunus(konusulan[i - 1]["metin"]) if i else "",
                "sonraki": okunus(konusulan[i + 1]["metin"]) if i + 1 < len(konusulan) else ""}
        girdi = {"motor": s["motor"], "ses": s["ses"], "model": s.get("model"), "hiz": s.get("hiz"),
                 "metin": metin, "onceki": aday["onceki"], "sonraki": aday["sonraki"]}
        ham = hazir.get(c["id"]) or kapi.cagir("ses", girdi, "mp3", fiyat * len(metin) / 1000,
                                               lambda: islev(metin, aday))
        wav = os.path.join(klasor, f"{c['id']}.wav")
        _kirp(ham, wav)
        sure = _sure(wav)
        zamanlar[c["id"]] = [round(t, 3), round(t + sure, 3)]
        parcalar += [("ses", wav), ("sus", ARA_SN)]
        t += sure + ARA_SN
    cikti = os.path.join(klasor, "anlatim.wav")
    birlestir([("sus", ACILIS_SN)] + parcalar + [("sus", KAPANIS_SN)], cikti)
    return {"dosya": cikti, "zamanlar": zamanlar,
            "motor": s["motor"], "ses": s["ses"]}


def _sessizlikler(yol: str, esik_db: int = -38, en_az: float = 0.18) -> list[tuple[float, float]]:
    import re
    c = subprocess.run(["ffmpeg", "-hide_banner", "-i", yol, "-af", f"silencedetect=noise={esik_db}dB:d={en_az}",
                        "-f", "null", "-"], capture_output=True, text=True)
    bas = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", c.stderr)]
    bit = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", c.stderr)]
    return list(zip(bas, bit))


def bol(blok_wav: str, metinler: list[str], klasor: str, onek: str) -> list[str] | None:
    """Tek parça okunmuş paragrafı cümlelere böler. Cümle sonları, harf sayısına göre beklenen yere en yakın
    sessizliğe düşer. Uygun sessizlik bulunamazsa None döner (çağıran cümle cümle üretime döner)."""
    toplam = _sure(blok_wav)
    sus = [(a, b) for a, b in _sessizlikler(blok_wav) if 0.05 < a and b < toplam - 0.05]
    harf = [len(m) for m in metinler]
    kesimler, onceki = [], 0.0
    for k in range(1, len(metinler)):
        beklenen = toplam * sum(harf[:k]) / sum(harf)
        adaylar = [(abs((a + b) / 2 - beklenen) - 0.8 * (b - a), (a + b) / 2) for a, b in sus
                   if (a + b) / 2 > onceki + 0.4 and abs((a + b) / 2 - beklenen) < max(1.5, 0.25 * toplam / len(metinler))]
        if not adaylar:
            return None
        onceki = min(adaylar)[1]
        kesimler.append(onceki)
    sinirlar = [0.0] + kesimler + [toplam]
    yollar = []
    for i in range(len(metinler)):
        ham = os.path.join(klasor, f"{onek}_{i}_ham.wav")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", blok_wav, "-ss", f"{sinirlar[i]:.3f}",
                        "-to", f"{sinirlar[i + 1]:.3f}", ham], check=True)
        yollar.append(ham)
    return yollar


def birlestir(parcalar: list[tuple[str, object]], cikti: str) -> None:
    """Ses parçalarını ve sessizlikleri sırayla tek dosyada toplar."""
    girdiler, etiketler = [], []
    for n, (tur, deger) in enumerate(parcalar):
        if tur == "sus":
            girdiler += ["-f", "lavfi", "-t", f"{float(deger):.3f}", "-i", "anullsrc=r=48000:cl=mono"]
        else:
            girdiler += ["-i", str(deger)]
        etiketler.append(f"[{n}:a]")
    gecici = cikti + ".tmp.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *girdiler, "-filter_complex",
                    "".join(etiketler) + f"concat=n={len(parcalar)}:v=0:a=1[a]", "-map", "[a]", gecici], check=True)
    os.replace(gecici, cikti)


def tilavet_ekle(anlatim: str, tilavet: str, bas: float, sure: float, cikti: str) -> None:
    """Tilaveti ayet kartının süresine yerleştirir; sığmazsa sonunu yumuşakça kısar."""
    f = (f"[1:a]atrim=0:{sure:.3f},afade=t=in:d=0.15,afade=t=out:st={max(sure - 0.6, 0):.3f}:d=0.6,"
         f"aresample=48000,adelay={int(bas * 1000)}:all=1[t];[0:a][t]amix=inputs=2:normalize=0[a]")
    gecici = cikti + ".tmp.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", anlatim, "-i", tilavet,
                    "-filter_complex", f, "-map", "[a]", gecici], check=True)
    os.replace(gecici, cikti)


if __name__ == "__main__":
    import sys

    b = json.load(open(sys.argv[1], encoding="utf-8"))
    a = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ayar.json"), encoding="utf-8"))
    k = os.path.join(os.path.dirname(os.path.abspath(sys.argv[1])), "uretim")
    print(json.dumps(uret(b, a, os.path.join(k, "ses"), Kapi(os.path.join(k, "defter.jsonl"), a["butce_usd"])),
                     ensure_ascii=False, indent=1))
