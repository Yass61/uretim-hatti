"""Bölüm dosyasının (bolum.json) üretim öncesi denetimi. Para harcanmadan önce çalışır.

Kullanım:  python3 bolum.py bolumler/ebu-talha/bolum.json

Hata  : üretim başlamaz (eksik kaynak, kırık plan, kırmızı çizgi).
Uyarı : üretim sürer, Telegram'daki senaryo onayında gösterilir.
"""
from __future__ import annotations

import json
import os
import re
import sys

KAYNAKSIZ_TURLERI = {"kanca", "köprü", "tefekkür"}     # kaynak gerektirmeyen cümle türleri
# Kırmızı çizgiler (proje kararları): müellif adına söz uydurulmaz, fetva verilmez.
YASAK_KALIPLAR = [
    (r"Bursev[îi]\s+(der ki|şöyle der|diyor ki|şöyle diyor)", "“Bursevî der ki” denmez; “Rûhu'l-Beyân'da şöyle geçer” denir"),
    (r"\b1500 yıl", "“1500 yıl” denmez; “bin yılı aşkın” denir"),
]
UYARI_KALIPLAR = [
    (r"\b(caizdir|caiz değildir|haramdır|helaldir|farzdır|vaciptir|mekruhtur|fetva)\b", "fetva dili; içerik fıkhî hüküm vermez"),
    (r"\b(Hanefî|Şâfiî|Mâlikî|Hanbelî)\s+mezheb", "mezhep konusu; içerik mezhep tartışmasına girmez"),
]
EN_UZUN_CUMLE = 14        # kelime; sakin ritim ve okunur altyazı için
SURE_ARALIGI = (30.0, 95.0)
PLAN_ARALIGI = (2.0, 10.0)


def denetle(bolum: dict, klasor: str | None = None, kuran_var=None) -> tuple[list[str], list[str]]:
    h, u = [], []
    for alan in ("baslik", "seri", "cumleler", "planlar", "kaynak_satirlari"):
        if not bolum.get(alan):
            h.append(f"'{alan}' alanı yok ya da boş")
    cumleler, planlar = bolum.get("cumleler") or [], bolum.get("planlar") or []
    kimlikler = [c.get("id") for c in cumleler]
    for k in {k for k in kimlikler if kimlikler.count(k) > 1}:
        h.append(f"cümle kimliği yineleniyor: {k}")
    kaynak_metni = " ".join(bolum.get("kaynak_satirlari") or [])
    for c in cumleler:
        ad = c.get("id", "?")
        if c.get("bekle"):
            continue
        metin = (c.get("metin") or "").strip()
        if not metin:
            h.append(f"{ad}: metin boş")
            continue
        if not c.get("kaynak"):
            if c.get("kaynaksiz") not in KAYNAKSIZ_TURLERI:
                h.append(f"{ad}: kaynak yok. Kaynak yaz ya da kaynaksiz = kanca | köprü | tefekkür de")
        else:
            for parca in re.split(r"\s*·\s*", c["kaynak"]):
                if parca and parca not in kaynak_metni:
                    h.append(f"{ad}: kaynağı ({parca}) son karttaki kaynak satırlarında yok")
        for kalip, neden in YASAK_KALIPLAR:
            if re.search(kalip, metin, flags=re.IGNORECASE):
                h.append(f"{ad}: {neden}")
        for kalip, neden in UYARI_KALIPLAR:
            if re.search(kalip, metin, flags=re.IGNORECASE):
                u.append(f"{ad}: {neden}")
        if len(metin.split()) > EN_UZUN_CUMLE:
            u.append(f"{ad}: {len(metin.split())} kelime; {EN_UZUN_CUMLE} kelimeyi aşan cümle bölünmeli")
    # planlar
    gorulen: list[str] = []
    for i, p in enumerate(planlar, start=1):
        if p.get("kart") not in (None, "ayet", "son"):
            h.append(f"plan {i}: bilinmeyen kart türü '{p.get('kart')}'")
        if not p.get("kart") and not p.get("gorsel") and not p.get("istem"):
            h.append(f"plan {i}: görsel dosyası da görsel istemi de yok")
        if p.get("kart") != "son" and not p.get("cumle") and "sure" not in p:
            h.append(f"plan {i}: cümlesi de süresi de yok")
        for k in p.get("cumle") or []:
            if k not in kimlikler:
                h.append(f"plan {i}: bilinmeyen cümle '{k}'")
            gorulen.append(k)
        if klasor and p.get("gorsel") and not p.get("istem") and not os.path.exists(os.path.join(klasor, p["gorsel"])):
            h.append(f"plan {i}: görsel dosyası yok ({p['gorsel']}) ve üretilecek istem de yazılmamış")
        if p.get("kart") == "ayet" and not bolum.get("ayet"):
            h.append(f"plan {i}: ayet kartı var ama 'ayet' alanı yok")
    for k in kimlikler:
        if gorulen.count(k) == 0:
            h.append(f"cümle hiçbir planda yok: {k}")
        elif gorulen.count(k) > 1:
            h.append(f"cümle birden çok planda: {k}")
    sirali = [k for k in gorulen if k in kimlikler]
    if sirali != sorted(sirali, key=kimlikler.index):
        h.append("planlardaki cümle sırası, cümle listesindeki sırayla aynı değil")
    if planlar and planlar[-1].get("kart") != "son":
        u.append("son plan kaynak kartı değil; kaynaklar videonun sonunda görünmeyecek")
    # ayet
    a = bolum.get("ayet")
    if a is not None:
        if not (isinstance(a, list) and len(a) == 2 and all(isinstance(x, int) for x in a) and 1 <= a[0] <= 114 and a[1] >= 1):
            h.append("'ayet' [sure, ayet] biçiminde iki tam sayı olmalı")
        elif kuran_var is not None and not kuran_var(a[0], a[1]):
            h.append(f"ayet Kur'an verisinde yok: {a[0]}:{a[1]}")
    # süreler (hata yoksa hesaplanabilir)
    if not h:
        from kurgu import cizelge

        _, zp, toplam = cizelge(bolum)
        if not SURE_ARALIGI[0] <= toplam <= SURE_ARALIGI[1]:
            u.append(f"tahmini süre {toplam:.0f} sn; hedef {SURE_ARALIGI[0]:.0f}-{SURE_ARALIGI[1]:.0f} sn")
        for i, p in enumerate(zp, start=1):
            sure = p["bit"] - p["bas"]
            if p.get("kart"):
                continue
            if sure < PLAN_ARALIGI[0]:
                u.append(f"plan {i}: {sure:.1f} sn; çok kısa, koşuşturmaca hissi verir")
            elif sure > PLAN_ARALIGI[1]:
                u.append(f"plan {i}: {sure:.1f} sn; çok uzun, ikiye bölünmeli")
    return h, u


def ozet_metni(bolum: dict, hatalar: list[str], uyarilar: list[str]) -> str:
    """Telegram'daki senaryo onayı için okunur özet."""
    satirlar = [f"📜 {bolum.get('baslik', '')}", ""]
    for c in bolum.get("cumleler", []):
        if c.get("bekle"):
            satirlar.append("  (ayet kartı)")
            continue
        etiket = c.get("kaynak") or c.get("kaynaksiz") or "KAYNAK YOK"
        satirlar.append(f"• {c['metin']}  [{etiket}]")
    if hatalar:
        satirlar += ["", "⛔ Hatalar:"] + [f"- {x}" for x in hatalar]
    if uyarilar:
        satirlar += ["", "⚠️ Uyarılar:"] + [f"- {x}" for x in uyarilar]
    return "\n".join(satirlar)


def main() -> None:
    yol = sys.argv[1]
    bolum = json.load(open(yol, encoding="utf-8"))
    hatalar, uyarilar = denetle(bolum, os.path.dirname(os.path.abspath(yol)))
    print(ozet_metni(bolum, hatalar, uyarilar))
    if hatalar:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
