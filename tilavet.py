"""Ayet tilaveti: EveryAyah arşivinden ayet ayet mp3 indirir.

  python3 tilavet.py prova 3 92            -> okuyucu adaylarını indirip Telegram'a numarasız adla yollar
  indir(okuyucu, sure, ayet, hedef)        -> hat bu işlevi kullanır

Dosya adı biçimi: SSSAAA.mp3 (ör. 003092.mp3). Okuyucu klasör adları everyayah.com/data altındadır.
"""
from __future__ import annotations

import json
import os
import random
import sys

OKUYUCULAR = {
    "Alafasy_128kbps": "Mişârî Râşid el-Afâsî",
    "Abdul_Basit_Murattal_192kbps": "Abdülbâsıt Abdüssamed (murattal)",
    "Husary_128kbps": "Mahmûd Halîl el-Husarî",
    "Minshawy_Murattal_128kbps": "Muhammed Sıddîk el-Minşâvî (murattal)",
    "MaherAlMuaiqly128kbps": "Mâhir el-Muaykılî",
    "Ghamadi_40kbps": "Sa'd el-Gâmidî",
    "Yasser_Ad-Dussary_128kbps": "Yâsir ed-Devserî",
    "Abdurrahmaan_As-Sudais_192kbps": "Abdurrahmân es-Sudeys",
}


def indir(okuyucu: str, sure: int, ayet: int, hedef: str) -> str:
    import requests

    url = f"https://everyayah.com/data/{okuyucu}/{sure:03d}{ayet:03d}.mp3"
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    if len(r.content) < 2000:
        raise RuntimeError(f"boş dosya: {url}")
    os.makedirs(os.path.dirname(os.path.abspath(hedef)), exist_ok=True)
    open(hedef, "wb").write(r.content)
    return hedef


def prova(sure: int, ayet: int, cikti: str = "tilavet_prova") -> None:
    import telegram

    sira = list(OKUYUCULAR)
    random.Random(sure * 1000 + ayet).shuffle(sira)
    anahtar, rapor = {}, []
    for no, ok in enumerate(sira, 1):
        try:
            yol = indir(ok, sure, ayet, os.path.join(cikti, f"tilavet_{no}.mp3"))
        except Exception as hata:
            rapor.append(f"{no}: hata ({ok}): {hata}")
            continue
        anahtar[no] = ok
        rapor.append(f"{no}: indirildi")
        telegram.ses(yol, f"Tilavet {no}")
    json.dump(anahtar, open(os.path.join(cikti, "anahtar.json"), "w"), indent=1)
    print("\n".join(rapor))
    telegram.mesaj(f"Tilavet provası ({sure}:{ayet}): {len(anahtar)} okuyucu. Beğendiğin numarayı yaz.")


if __name__ == "__main__":
    if sys.argv[1] == "prova":
        prova(int(sys.argv[2]), int(sys.argv[3]))
