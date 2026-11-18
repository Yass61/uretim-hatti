"""Plan görsellerini fal üzerinden üretir. Yazı üretmez; bütün yazılar kurguda bindirilir.

Her plan için birkaç aday üretilir, adaylar denetimden geçer (denetim.py), en iyisi seçilir.
Çağrılar kapıdan (kapi.py) geçer: aynı istem ikinci kez ödenmez, bölüm bütçesi aşılmaz.

Model kimliği ve fiyatı fal'ın kendi sayfasından doğrulandı (18.11.2026):
  fal-ai/recraft/v4/text-to-image — 0,04 USD / görsel.   Ağ çağrısı ilk kez Actions'ta denenecek.
"""
from __future__ import annotations

import os
import time

from kapi import Kapi, ozet

STIL = ("Painterly cinematic realism with visible brushwork and rich surface texture. Single warm key light, "
        "3200K, long soft shadows, deep umber shadow areas, restrained palette of cream, gold and umber with one "
        "muted accent. Shallow atmospheric haze for depth: clear foreground, midground and far background layers. "
        "Vertical 9:16 composition, subject in the upper or lower third, a calm low-detail band across the middle "
        "of the frame for captions. 7th century Hejaz setting: mud-brick, palm trunks, woven palm mats, clay, wool.")
YASAK = ("No human faces. No figures seen from the front; at most distant silhouettes from behind. No text, "
         "letters, calligraphy or signage. No domes, minarets, crescents, arches of later Islamic architecture. "
         "No modern objects, glass, metal tools, books with printed pages. No halos or light around figures.")


def tam_istem(istem: str) -> str:
    return f"{istem.strip()} {STIL} {YASAK}"


def _fal(model: str, istem: str, tohum: int) -> bytes:
    import requests

    b = {"Authorization": f"Key {os.environ['FAL_KEY']}", "Content-Type": "application/json"}
    r = requests.post(f"https://queue.fal.run/{model}", headers=b, timeout=60,
                      json={"prompt": istem, "image_size": "portrait_16_9", "seed": tohum})
    r.raise_for_status()
    is_ = r.json()
    for _ in range(100):
        d = requests.get(is_["status_url"], headers=b, timeout=60).json()
        if d.get("status") == "COMPLETED":
            break
        if d.get("status") in ("FAILED", "ERROR"):
            raise RuntimeError(f"fal işi başarısız: {str(d)[:300]}")
        time.sleep(3)
    else:
        raise RuntimeError("fal işi 5 dakikada bitmedi")
    sonuc = requests.get(is_["response_url"], headers=b, timeout=60).json()
    g = requests.get(sonuc["images"][0]["url"], timeout=120)
    g.raise_for_status()
    return g.content


def istekler(bolum: dict, ayar: dict) -> list[tuple[int, int, dict]]:
    """Üretilecek her görsel için (plan sırası, aday sırası, önbellek girdisi)."""
    g, liste = ayar["gorsel"], []
    for i, p in enumerate(bolum["planlar"]):
        if p.get("kart") or not p.get("istem"):
            continue
        for a in range(p.get("aday", g.get("aday", 2))):
            istem = tam_istem(p["istem"])                # tohum istemden türer: aynı istem, aynı görsel
            liste.append((i, a, {"model": g["model"], "istem": istem, "tohum": int(ozet({"i": istem}), 16) % 90000 + a}))
    return liste


def tahmin(bolum: dict, ayar: dict, kapi: Kapi) -> tuple[float, int, int]:
    return kapi.tahmin([("gorsel", girdi, "img", ayar["gorsel"]["usd"]) for _, _, girdi in istekler(bolum, ayar)])


def uret(bolum: dict, ayar: dict, kapi: Kapi, cagri=_fal) -> dict[int, list[str]]:
    """{plan sırası: [aday dosya yolları]} döner. Aynı istem iki planda geçerse bir kez üretilir."""
    if not os.environ.get("FAL_KEY") and cagri is _fal:
        raise RuntimeError("FAL_KEY yok")
    sonuc: dict[int, list[str]] = {}
    for i, a, girdi in istekler(bolum, ayar):
        yol = kapi.cagir("gorsel", girdi, "img", ayar["gorsel"]["usd"],
                         lambda g=girdi: cagri(g["model"], g["istem"], g["tohum"]))
        sonuc.setdefault(i, []).append(yol)
    return sonuc
