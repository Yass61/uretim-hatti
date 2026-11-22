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
    parcalar, zamanlar, duraklar, t = [], {}, {}, ACILIS_SN
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
            if yollar:                                   # kırpılmış konuşma hızı makul mü? (harf/sn)
                hizlar = []
                for y, m in zip(yollar, metinler):
                    deneme = y.replace("_ham.wav", "_olc.wav")
                    _kirp(y, deneme)
                    hizlar.append(len(m) / max(_sure(deneme), 0.05))
                ort = sum(len(m) for m in metinler) / max(sum(len(m) / h for m, h in zip(metinler, hizlar)), 0.05)
                if all(0.6 * ort <= h <= 1.6 * ort for h in hizlar):
                    hazir.update({c["id"]: y for c, y in zip(grup, yollar)})
                else:
                    print(f"[ses] paragraf {gi} bölmesi şüpheli (harf/sn: {[round(h) for h in hizlar]}); cümle cümle üretiliyor")
            else:
                print(f"[ses] paragraf {gi} sessizliklerden bölünemedi; cümle cümle üretiliyor")
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
        # cümle içindeki duraklar (virgül nefesleri): altyazı öbekleri bunlara oturur
        duraklar[c["id"]] = [round((a + b) / 2, 3) for a, b in _sessizlikler(wav, -38, 0.12) if 0.15 < a and b < sure - 0.15]
        parcalar += [("ses", wav), ("sus", ARA_SN)]
        t += sure + ARA_SN
    cikti = os.path.join(klasor, "anlatim.wav")
    birlestir([("sus", ACILIS_SN)] + parcalar + [("sus", KAPANIS_SN)], cikti)
    return {"dosya": cikti, "zamanlar": zamanlar, "duraklar": duraklar,
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
    n = len(metinler)
    if len(sus) < n - 1:
        return None
    # Dinamik programlama: n-1 sessizliği, her cümlenin süresi harf payına en yakın olacak ve
    # uzun duraklar tercih edilecek biçimde seç (açgözlü seçim bir kayınca hepsi kayıyordu).
    orta = [(a + b) / 2 for a, b in sus]
    uzun = [b - a for a, b in sus]
    pay = [toplam * h / sum(harf) for h in harf]
    def bedel(bas: float, son: float, i: int) -> float:
        return ((son - bas - pay[i]) / pay[i]) ** 2
    m = len(sus)
    INF = float("inf")
    dp = [[INF] * m for _ in range(n - 1)]
    geri = [[-1] * m for _ in range(n - 1)]
    for j in range(m):
        dp[0][j] = bedel(0.0, orta[j], 0) - 0.6 * uzun[j]
    for i in range(1, n - 1):
        for j in range(i, m):
            for k in range(i - 1, j):
                v = dp[i - 1][k] + bedel(orta[k], orta[j], i) - 0.6 * uzun[j]
                if v < dp[i][j]:
                    dp[i][j], geri[i][j] = v, k
    if n == 1:
        kesimler = []
    else:
        son_j = min(range(m), key=lambda j: dp[n - 2][j] + bedel(orta[j], toplam, n - 1))
        if dp[n - 2][son_j] == INF:
            return None
        sec = [son_j]
        for i in range(n - 2, 0, -1):
            sec.append(geri[i][sec[-1]])
        kesimler = [orta[j] for j in reversed(sec)]
    sinirlar = [0.0] + kesimler + [toplam]
    for i, m in enumerate(metinler):                      # bir cümle beklenenin yarısından kısa ya da iki katından
        beklenen = toplam * harf[i] / sum(harf)           # uzunsa kesim yanlış yere düşmüştür: güvenme
        gercek = sinirlar[i + 1] - sinirlar[i]
        if not (0.55 * beklenen <= gercek <= 1.8 * beklenen):
            return None
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
