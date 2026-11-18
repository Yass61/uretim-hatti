"""Seslendirme için Türkçe okunuş: yazıdaki metin altyazıda aynen kalır, ses motoruna okunuşu gider.

    okunus("II. Mehmed 1452–1481 arasında %75'ini aldı.")
    -> "ikinci Mehmed bin dört yüz elli iki ile bin dört yüz seksen bir arasında yüzde yetmiş beşini aldı."

Kurallar AI Video Factory'deki (MIT, Ersin Koç) Türkçe okuma yaklaşımından esinlenerek sıfırdan yazıldı;
dinî metne özgü kısaltmalar (Hz., s.a.v., r.a. …) ve hicrî/milâdî tarih kalıpları eklendi.
Özel okunuşlar `okunus_sozlugu.json` dosyasından gelir; oraya satır eklemek kod değişikliği gerektirmez.
"""
from __future__ import annotations

import json
import os
import re

BIRLER = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"]
ONLAR = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"]
BUYUKLER = ["", "bin", "milyon", "milyar", "trilyon"]
SIRA_EKI = {"bir": "birinci", "iki": "ikinci", "üç": "üçüncü", "dört": "dördüncü", "beş": "beşinci",
            "altı": "altıncı", "yedi": "yedinci", "sekiz": "sekizinci", "dokuz": "dokuzuncu",
            "on": "onuncu", "yirmi": "yirminci", "otuz": "otuzuncu", "kırk": "kırkıncı", "elli": "ellinci",
            "altmış": "altmışıncı", "yetmiş": "yetmişinci", "seksen": "sekseninci", "doksan": "doksanıncı",
            "yüz": "yüzüncü", "bin": "bininci", "milyon": "milyonuncu", "milyar": "milyarıncı", "sıfır": "sıfırıncı"}
ROMA = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}

# Okunurken açılan kısaltmalar. Sıra önemlidir: uzun olan önce denenir.
KISALTMALAR = [
    (r"\(s\.a\.v\.?\)|\bs\.a\.v\.?|\(sav\)|\(s\.a\.s\.?\)|\bs\.a\.s\.?", "sallallâhu aleyhi ve sellem"),
    (r"\(r\.anhümâ\)|\(r\.anhüma\)", "radıyallâhu anhümâ"),
    (r"\(r\.anhüm\)", "radıyallâhu anhüm"),
    (r"\(r\.anhâ\)|\(r\.anha\)", "radıyallâhu anhâ"),
    (r"\(r\.a\.?\)|\br\.a\.(?=\s|$|[,;])|\(r\.anh\)", "radıyallâhu anh"),
    (r"\(a\.s\.?\)|\ba\.s\.(?=\s|$|[,;])", "aleyhisselâm"),
    (r"\(c\.c\.?\)|\bc\.c\.(?=\s|$|[,;])", "celle celâlüh"),
    (r"\(k\.s\.?\)|\bk\.s\.(?=\s|$|[,;])", "kuddise sirruh"),
    (r"\(rh\.a\.?\)|\brh\.a\.", "rahmetullâhi aleyh"),
    (r"\bHz\.\s*", "Hazreti "),
    (r"\bb\.\s+(?=[A-ZÂÎÛÇĞİÖŞÜ])", "bin "),          # Ömer b. Hattâb
    (r"\bvb\.", "ve benzeri"),
    (r"\bvs\.", "vesaire"),
    (r"\byy\.", "yüzyıl"),
    (r"\bbkz\.", "bakınız"),
    (r"\bö\.\s*(?=\d)", "ölümü "),
    (r"\bM\.Ö\.\s*", "milattan önce "),
    (r"\bM\.S\.\s*", "milattan sonra "),
]


def sayi(n: int) -> str:
    """Tam sayıyı yazıyla verir: 1461 -> 'bin dört yüz altmış bir'."""
    if n == 0:
        return "sıfır"
    if n < 0:
        return "eksi " + sayi(-n)
    parcalar, basamak = [], 0
    while n:
        n, uc = divmod(n, 1000)
        if uc:
            yuz, kalan = divmod(uc, 100)
            on, bir = divmod(kalan, 10)
            s = []
            if yuz:
                s.append("yüz" if yuz == 1 else BIRLER[yuz] + " yüz")
            if on:
                s.append(ONLAR[on])
            if bir:
                s.append(BIRLER[bir])
            metin = " ".join(s)
            if basamak == 1 and uc == 1:
                metin = "bin"                      # "bir bin" denmez
            elif basamak:
                metin += " " + BUYUKLER[basamak]
            parcalar.append(metin)
        basamak += 1
    return " ".join(reversed(parcalar))


def sira(n: int) -> str:
    """Sıra sayısı: 2 -> 'ikinci', 63 -> 'altmış üçüncü'."""
    kelimeler = sayi(n).split()
    kelimeler[-1] = SIRA_EKI[kelimeler[-1]]
    return " ".join(kelimeler)


def roma(s: str) -> int | None:
    toplam, onceki = 0, 0
    for h in reversed(s):
        d = ROMA.get(h)
        if d is None:
            return None
        toplam += -d if d < onceki else d
        onceki = max(onceki, d)
    return toplam if 0 < toplam < 40 else None      # hükümdar, cilt, yüzyıl: küçük sayılar


def _ondalik(tam: str, kesir: str) -> str:
    if kesir == "5":
        return ("yarım" if tam == "0" else sayi(int(tam)) + " buçuk")
    return f"{sayi(int(tam))} virgül {sayi(int(kesir))}"


def _sozluk() -> dict[str, str]:
    yol = os.path.join(os.path.dirname(os.path.abspath(__file__)), "okunus_sozlugu.json")
    if not os.path.exists(yol):
        return {}
    return {k: v for k, v in json.load(open(yol, encoding="utf-8")).items() if not k.startswith("_")}


def okunus(metin: str, sozluk: dict[str, str] | None = None) -> str:
    """Altyazı metnini ses motoruna verilecek okunuşa çevirir."""
    m = metin
    for yazi, soyle in sorted((sozluk if sozluk is not None else _sozluk()).items(), key=lambda x: -len(x[0])):
        m = re.sub(r"(?<![\wâîûÂÎÛ])" + re.escape(yazi), soyle, m)
    for kalip, acilim in KISALTMALAR:
        m = re.sub(kalip, acilim, m, flags=re.IGNORECASE if kalip.startswith(r"\(") else 0)
    m = re.sub(r"(\d)['’](?=[a-zçğıöşü])", "\\1\x01", m)     # "92'de": ek sayıya bitişik okunur
    # hicrî / milâdî: "h. 505", "m. 1111"
    m = re.sub(r"\b[hH]\.\s*(\d{1,4})\b", lambda g: "hicrî " + sayi(int(g.group(1))), m)
    m = re.sub(r"\b[mM]\.\s*(\d{3,4})\b", lambda g: "milâdî " + sayi(int(g.group(1))), m)
    # cilt ve sayfa: "c. 2, s. 63" -> "ikinci cilt, sayfa altmış üç"
    m = re.sub(r"\bc\.\s*(\d+)", lambda g: sira(int(g.group(1))) + " cilt", m)
    m = re.sub(r"\bs\.\s*(\d+)", lambda g: "sayfa " + sayi(int(g.group(1))), m)
    # Roma rakamlı sıra: "II. Mehmed", "XIII. yüzyıl"
    m = re.sub(r"\b([IVXLC]+)\.(?=\s+\S)", lambda g: sira(roma(g.group(1))) if roma(g.group(1)) else g.group(0), m)
    # aralık: "1452–1481" -> "… ile …"
    m = re.sub(r"\b(\d{1,4})\s*[–—-]\s*(\d{1,4})\b", lambda g: f"{sayi(int(g.group(1)))} ile {sayi(int(g.group(2)))}", m)
    # yüzde, kesir, ondalık, binlik ayraçlı sayı
    m = re.sub(r"%\s*(\d+)(?:,(\d+))?", lambda g: "yüzde " + (_ondalik(g.group(1), g.group(2)) if g.group(2) else sayi(int(g.group(1)))), m)
    m = re.sub(r"\b(\d+)/(\d+)\b", lambda g: f"{sayi(int(g.group(2)))}{_bulunma(int(g.group(2)))} {sayi(int(g.group(1)))}", m)
    m = re.sub(r"\b(\d{1,3}(?:\.\d{3})+)\b", lambda g: sayi(int(g.group(1).replace(".", ""))), m)
    m = re.sub(r"\b(\d+),(\d+)\b", lambda g: _ondalik(g.group(1), g.group(2)), m)
    # sıra sayısı: "3. gün" (cümle sonu noktasıyla karışmasın diye ardından küçük harf beklenir)
    m = re.sub(r"\b(\d+)\.(?=\s+[a-zâîûçğıöşü])", lambda g: sira(int(g.group(1))), m)
    m = re.sub(r"\b\d+\b", lambda g: sayi(int(g.group(0))), m)
    return re.sub(r"\s{2,}", " ", m.replace("\x01", "")).strip()


def _bulunma(n: int) -> str:
    """Kesirde payda eki: 4 -> 'te' (dörtte), 3 -> 'te' (üçte), 2 -> 'de' (ikide)."""
    son = sayi(n).split()[-1]
    sert = son[-1] in "çfhkpsşt"
    kalin = [h for h in son if h in "aıouâû"]
    ince = [h for h in son if h in "eiöüî"]
    son_unlu_kalin = bool(kalin) and (not ince or son.rfind(kalin[-1]) > son.rfind(ince[-1]))
    return ("t" if sert else "d") + ("a" if son_unlu_kalin else "e")


if __name__ == "__main__":
    import sys

    print(okunus(" ".join(sys.argv[1:]) or "II. Mehmed 1452–1481 arasında %75'ini aldı."))
