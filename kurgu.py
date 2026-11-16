"""Bir bölüm dosyasından (bolum.json) dikey videoyu kurar.

Kullanım:  python3 kurgu.py bolumler/ebu-talha/bolum.json cikti.mp4 [--onizleme 3.0 12.5]

bolum.json alanları (örnek: deneme/bolum.json):
  ayet        : [sure, ayet] — metin ve meal kütüphanedeki Kur'an verisinden okunur, elle yazılmaz
  cumleler    : [{id, metin, kaynak?, altyazi?, bekle?}]
  planlar     : [{gorsel | kart, cumle: [id...], hareket?, huzme?, sure?}]
  ses         : (isteğe bağlı) {dosya, zamanlar: {cumle_id: [bas, bit]}} — yoksa süre kelime sayısından tahmin edilir
  tilavet     : (isteğe bağlı) {dosya, okuyucu}

Görüntü modeli asla yazı üretmez: ayet, meal, altyazı ve kaynak rozeti burada bindirilir.
"""
from __future__ import annotations

import gzip
import json
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from derinlik import derinlik as derinlik_bul
from hareket import Ayar, Hareket

W, H, FPS = 1080, 1920, 30
KOK = os.path.dirname(os.path.abspath(__file__))
KURAN = os.environ.get("KURAN_VERISI", os.path.join(KOK, "..", "kuran", "kuran.jsonl.gz"))
F_KALIN = os.path.join(KOK, "fonts/Inter-Bold.otf")
F_ORTA = os.path.join(KOK, "fonts/Inter-Medium.otf")
F_SERIF = os.path.join(KOK, "fonts/DejaVuSerif.ttf")
F_KURAN = os.path.join(KOK, "fonts/AmiriQuran.ttf")
KREM, ALTIN, KAHVE = (248, 238, 218), (220, 194, 131), (81, 65, 40)

# Sakin anlatım ritmi (pilot sonrası karar): ses yokken süre tahmini
SN_KELIME, SN_PARCA, SN_CUMLE_SONU, SN_ARA, GECIS = 0.43, 0.08, 0.30, 0.70, 0.7


def yazi(yol: str, boyut: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(yol, boyut)


def ayet_oku(sure: int, ayet: int) -> dict:
    with gzip.open(KURAN, "rt", encoding="utf-8") as f:
        for satir in f:
            d = json.loads(satir)
            if (d["sure"], d["ayet"]) == (sure, ayet):
                return d
    raise SystemExit(f"ayet bulunamadı: {sure}:{ayet}")


# ------------------------------------------------------------ zaman çizelgesi
def parcala(metin: str) -> list[str]:
    """Cümleyi 3-4 kelimelik altyazı öbeklerine böler."""
    kelimeler, parcalar, cur = metin.split(), [], []
    for i, k in enumerate(kelimeler):
        cur.append(k)
        son = k[-1] in ",.;:!?”" or i == len(kelimeler) - 1
        if len(cur) >= 4 or son or sum(len(x) for x in cur) >= 20:
            parcalar.append(" ".join(cur))
            cur = []
    return parcalar


def cizelge(bolum: dict) -> tuple[list[dict], list[dict], float]:
    zamanlar = (bolum.get("ses") or {}).get("zamanlar") or {}
    t, cumleler = 0.0, []
    for c in bolum["cumleler"]:
        parcalar = []
        if c["id"] in zamanlar:                       # gerçek ses: süre sesten gelir
            bas, bit = zamanlar[c["id"]]
            ps = parcala(c["metin"])
            toplam = sum(len(p) for p in ps) or 1
            u = bas
            for p in ps:                                 # öbekler harf sayısına orantılı dağıtılır
                dur = (bit - bas) * len(p) / toplam
                parcalar.append({"metin": p, "bas": u, "bit": u + dur})
                u += dur
            t = bit
        elif c.get("bekle"):
            bas, t = t, t + c["bekle"]
            bit = t
        else:
            bas = t
            for p in parcala(c["metin"]):
                dur = SN_KELIME * len(p.split()) + SN_PARCA + (SN_CUMLE_SONU if p[-1] in ".!?:”" else 0)
                parcalar.append({"metin": p, "bas": t, "bit": t + dur})
                t += dur
            t += SN_ARA
            bit = t
        cumleler.append({**c, "bas": bas, "bit": bit, "parcalar": parcalar})
    kimlik = {c["id"]: c for c in cumleler}
    planlar = []
    for p in bolum["planlar"]:
        if "sure" in p:
            bas, t = t, t + p["sure"]
            bit = t
        else:
            bas, bit = kimlik[p["cumle"][0]]["bas"], kimlik[p["cumle"][-1]]["bit"]
        planlar.append({**p, "bas": bas, "bit": bit})
    for i in range(len(planlar) - 1):                    # planlar arasında boşluk kalmasın
        planlar[i]["bit"] = planlar[i + 1]["bas"]
    return cumleler, planlar, t


# -------------------------------------------------------------------- kartlar
def zemin() -> Image.Image:
    ys = np.linspace(0, 1, H)[:, None, None]
    arr = (np.array([58, 38, 30]) * (1 - ys) + np.array([36, 24, 20]) * ys).repeat(W, axis=1)
    img = Image.fromarray(arr.astype(np.uint8), "RGB")
    d = ImageDraw.Draw(img)
    for ic, kal in ((90, 6), (120, 2), (150, 2)):
        d.rounded_rectangle([ic, ic + 120, W - ic, H - ic - 120], 28, outline=ALTIN, width=kal)
    return img


def satirla(d: ImageDraw.ImageDraw, kelimeler: list[str], fnt, genislik: int, **kw) -> list[str]:
    satirlar, cur = [], []
    for k in kelimeler:
        if cur and d.textlength(" ".join(cur + [k]), font=fnt, **kw) > genislik:
            satirlar.append(" ".join(cur))
            cur = [k]
        else:
            cur.append(k)
    return satirlar + ([" ".join(cur)] if cur else [])


def ayet_karti(bolum: dict) -> Image.Image:
    sure, ayet = bolum["ayet"]
    a = ayet_oku(sure, ayet)
    arapca = a["arapca"].replace("‏", "").strip()
    img = zemin()
    d = ImageDraw.Draw(img)
    kw = dict(direction="rtl", language="ar")
    boyut = 78
    while True:                                          # uzun ayette yazı küçülür, taşmaz
        fq = yazi(F_KURAN, boyut)
        satirlar = satirla(d, arapca.split(), fq, 800, **kw)
        fm = yazi(F_SERIF, max(int(boyut * 0.56), 30))
        meal = satirla(d, a["elmalili"].strip().split(), fm, 780)
        yuk = len(satirlar) * boyut * 1.92 + 180 + len(meal) * fm.size * 1.5 + 90
        if yuk <= 1250 or boyut <= 40:
            break
        boyut -= 4
    y = (H - yuk) / 2
    for s in satirlar:
        d.text((W / 2, y), s, font=fq, fill=KREM, anchor="ma", **kw)
        y += boyut * 1.92
    y += 110
    d.line([(W / 2 - 120, y), (W / 2 + 120, y)], fill=ALTIN, width=3)
    y += 70
    for s in meal:
        d.text((W / 2, y), s, font=fm, fill=KREM, anchor="ma")
        y += fm.size * 1.5
    d.text((W / 2, y + 40), bolum.get("ayet_etiketi", f"{sure}:{ayet}") + " · Elmalılı meali",
           font=yazi(F_ORTA, 34), fill=ALTIN, anchor="ma")
    return img


def son_kart(bolum: dict) -> Image.Image:
    img = zemin()
    d = ImageDraw.Draw(img)
    d.text((W / 2, 800), bolum.get("seri", ""), font=yazi(F_KALIN, 70), fill=KREM, anchor="mm")
    d.text((W / 2, 910), bolum.get("alt_baslik", ""), font=yazi(F_ORTA, 46), fill=ALTIN, anchor="mm")
    for i, s in enumerate(bolum.get("kaynak_satirlari", [])):
        d.text((W / 2, 1060 + i * 54), s, font=yazi(F_ORTA, 34), fill=KREM, anchor="mm")
    return img


def altyazi(metin: str) -> Image.Image:
    boyut = 80
    olc = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    fnt = yazi(F_KALIN, boyut)
    while olc.textlength(metin, font=fnt) > 940 and boyut > 48:
        boyut -= 4
        fnt = yazi(F_KALIN, boyut)
    ov = Image.new("RGBA", (W, 220), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    kelimeler = metin.split()
    x = (W - d.textlength(metin, font=fnt)) / 2
    bosluk = d.textlength(" ", font=fnt)
    for i, k in enumerate(kelimeler):
        renk = ALTIN if (i == len(kelimeler) - 1 and len(kelimeler) > 1) else KREM
        d.text((x, 110), k, font=fnt, fill=renk, anchor="lm", stroke_width=7, stroke_fill=KAHVE)
        x += d.textlength(k, font=fnt) + bosluk
    return ov


def rozet(metin: str) -> Image.Image:
    fnt = yazi(F_ORTA, 34)
    w = int(ImageDraw.Draw(Image.new("RGB", (8, 8))).textlength(metin, font=fnt)) + 56
    ov = Image.new("RGBA", (w, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    d.rounded_rectangle([0, 0, w - 1, 63], 32, fill=(40, 28, 22, 190), outline=ALTIN + (220,), width=2)
    d.text((w / 2, 32), metin, font=fnt, fill=KREM, anchor="mm")
    return ov


# --------------------------------------------------------------------- kurgu
SIRA = ["yaklas", "saga", "yuksel", "sola", "capraz", "uzaklas"]


def gorsel_yukle(yol: str) -> np.ndarray:
    """Görseli 9:16'ya ortadan kırpar ve 1080x1920'ye getirir."""
    im = Image.open(yol).convert("RGB")
    oran = W / H
    if im.width / im.height > oran:
        yeni = int(im.height * oran)
        im = im.crop(((im.width - yeni) // 2, 0, (im.width - yeni) // 2 + yeni, im.height))
    else:
        yeni = int(im.width / oran)
        im = im.crop((0, (im.height - yeni) // 2, im.width, (im.height - yeni) // 2 + yeni))
    return np.asarray(im.resize((W, H), Image.LANCZOS))


def hazirla(bolum: dict, klasor: str):
    cumleler, planlar, toplam = cizelge(bolum)
    for i, p in enumerate(planlar):
        if p.get("kart") == "ayet":
            p["sabit"] = np.asarray(ayet_karti(bolum))
        elif p.get("kart") == "son":
            p["sabit"] = np.asarray(son_kart(bolum))
        else:
            g = gorsel_yukle(os.path.join(klasor, p["gorsel"]))
            dyol = os.path.join(klasor, p["derinlik"]) if p.get("derinlik") else None
            if dyol and os.path.exists(dyol):
                d = np.asarray(Image.open(dyol).convert("L").resize((W, H))).astype(np.float32) / 255
            else:
                d, _ = derinlik_bul(g)
            p["motor"] = Hareket(g, d, Ayar(hareket=p.get("hareket", SIRA[i % len(SIRA)]),
                                             hüzme=p.get("huzme", 0.0), isik_x=p.get("isik_x", 0.75),
                                             isik_y=p.get("isik_y", 0.25), tohum=7 + i))
    yazilar = [(pr["bas"], pr["bit"], altyazi(pr["metin"]))
               for c in cumleler if c.get("altyazi", True) for pr in c["parcalar"]]
    rozetler = [(c["bas"], c["bit"], rozet(c["kaynak"])) for c in cumleler if c.get("kaynak")]
    return cumleler, planlar, toplam, yazilar, rozetler


def plan_karesi(p: dict, t: float) -> np.ndarray:
    if "sabit" in p:
        return p["sabit"]
    sure = max(p["bit"] - p["bas"], 0.1) + GECIS          # erime boyunca hareket sürsün
    return p["motor"].kare((t - p["bas"]) / sure, t - p["bas"])


def kare(t: float, planlar, yazilar, rozetler) -> Image.Image:
    i = max(k for k, p in enumerate(planlar) if p["bas"] <= t + 1e-9)
    p = planlar[i]
    k = plan_karesi(p, t)
    if i > 0 and t - p["bas"] < GECIS:
        a = (t - p["bas"]) / GECIS
        once = plan_karesi(planlar[i - 1], t)
        k = (once.astype(np.float32) * (1 - a) + k.astype(np.float32) * a).astype(np.uint8)
    img = Image.fromarray(k)
    for bas, bit, ov in rozetler:
        if bas <= t < bit:
            img.paste(ov, ((W - ov.width) // 2, 1430), ov)
            break
    for bas, bit, ov in yazilar:
        if bas <= t < bit:
            img.paste(ov, (0, int(H * 0.55) - 110), ov)
            break
    return img


def main() -> None:
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    bolum_yolu, cikti = sys.argv[1], sys.argv[2]
    klasor = os.path.dirname(os.path.abspath(bolum_yolu))
    bolum = json.load(open(bolum_yolu, encoding="utf-8"))
    cumleler, planlar, toplam, yazilar, rozetler = hazirla(bolum, klasor)
    print(f"toplam {toplam:.1f} sn, {len(planlar)} plan, {len(yazilar)} altyazı öbeği")
    if "--onizleme" in sys.argv:
        for z in sys.argv[sys.argv.index("--onizleme") + 1:]:
            kare(float(z), planlar, yazilar, rozetler).save(f"{os.path.splitext(cikti)[0]}_{z}.jpg", quality=90)
        return
    ses = (bolum.get("ses") or {}).get("dosya")
    gecici = os.path.splitext(cikti)[0] + ".tmp.mp4"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-"]
    if ses:
        cmd += ["-i", os.path.join(klasor, ses), "-af", "loudnorm=I=-14:TP=-1.5:LRA=11"]
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
    cmd += ["-c:v", "libx264", "-crf", "21", "-maxrate", "5M", "-bufsize", "10M", "-preset", "medium",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", gecici]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(int(toplam * FPS)):
        pr.stdin.write(kare(i / FPS, planlar, yazilar, rozetler).tobytes())
    pr.stdin.close()
    if pr.wait() != 0:
        raise SystemExit("ffmpeg hata verdi")
    os.replace(gecici, cikti)
    print("yazıldı:", cikti)


if __name__ == "__main__":
    main()
