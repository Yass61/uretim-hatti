"""Plan görsellerini fal üzerinden üretir (varsayılan: Recraft). Yazı üretmez; yazılar kurguda bindirilir.

Kullanım:  python3 gorsel.py istemler.json cikti_klasoru
istemler.json: [{"ad": "01-acilis", "istem": "...", "aday": 4}, ...]
NOT: Ağ çağrısı bu ortamda denenemedi. Model kimliği FAL_MODEL ile değiştirilir; Recraft V4.1'in
     fal'daki tam kimliği ilk çalışmada doğrulanmalı (varsayılan bilinen V3 uç noktasıdır).
"""
from __future__ import annotations

import json
import os
import sys
import time

MODEL = os.environ.get("FAL_MODEL", "fal-ai/recraft/v3/text-to-image")
STIL = ("Painterly cinematic realism, rich texture, high contrast, warm 3200K light, deep umber shadows, "
        "cream-gold-umber palette, vertical 9:16, calm empty band across the center for captions.")
YASAK = ("No people shown from the front, no faces, no text, no letters, no calligraphy, no modern objects, "
         "no domes, no minarets.")


def tam_istem(istem: str) -> str:
    return f"{istem.strip()} {STIL} {YASAK}"


def uret(istem: str, adet: int = 2) -> list[str]:
    import requests

    basliklar = {"Authorization": f"Key {os.environ['FAL_KEY']}", "Content-Type": "application/json"}
    adresler = []
    for _ in range(adet):
        r = requests.post(f"https://queue.fal.run/{MODEL}", headers=basliklar, timeout=60,
                          json={"prompt": tam_istem(istem), "image_size": {"width": 1024, "height": 1820}})
        r.raise_for_status()
        is_ = r.json()
        for _ in range(120):
            d = requests.get(is_["status_url"], headers=basliklar, timeout=60).json()
            if d.get("status") == "COMPLETED":
                break
            if d.get("status") in ("FAILED", "ERROR"):
                raise RuntimeError(f"fal işi başarısız: {d}")
            time.sleep(3)
        sonuc = requests.get(is_["response_url"], headers=basliklar, timeout=60).json()
        adresler.append(sonuc["images"][0]["url"])
    return adresler


def main() -> None:
    import requests

    istemler = json.load(open(sys.argv[1], encoding="utf-8"))
    cikti = sys.argv[2]
    os.makedirs(cikti, exist_ok=True)
    for kayit in istemler:
        for i, adres in enumerate(uret(kayit["istem"], kayit.get("aday", 2)), start=1):
            yol = os.path.join(cikti, f"{kayit['ad']}_{i}.png")
            open(yol, "wb").write(requests.get(adres, timeout=120).content)
            print("indirildi:", yol)


if __name__ == "__main__":
    main()
