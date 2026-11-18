"""Telegram'dan gelen kararı işler ve iş akışına ne yapacağını söyler.

  python3 onay.py coz      -> GITHUB_OUTPUT satırları: bolum=…, asama=tahmin|senaryo|uret|yok, gonder=true|false
  python3 onay.py kaydet   -> kararı bolumler/<ad>/kararlar.jsonl dosyasına yazar, Telegram'a kısa cevap verir
  python3 onay.py baslik   -> commit başlığı

Kimlik biçimi: "s:<bölüm>" senaryo onayı, "v:<bölüm>" video onayı. Karar: onay | red | not.
Girdiler ortam değişkenlerinden okunur; bölüm adı yalnız küçük harf, rakam ve tire içerebilir.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone

GUVENLI = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")


def coz(ortam=os.environ) -> dict:
    kimlik = ortam.get("ONAY_KIMLIK") or ""
    if kimlik:                                           # Telegram'dan gelen karar
        tur, _, ad = kimlik.partition(":")
        karar = ortam.get("ONAY_KARAR") or ""
        if tur not in ("s", "v") or not GUVENLI.match(ad) or karar not in ("onay", "red", "not"):
            raise SystemExit(f"geçersiz onay: {kimlik!r} {karar!r}")
        if not os.path.exists(os.path.join("bolumler", ad, "bolum.json")):
            raise SystemExit(f"bölüm yok: {ad}")
        return {"bolum": ad, "tur": tur, "karar": karar,
                "asama": "uret" if (tur, karar) == ("s", "onay") else "yok", "gonder": "true"}
    ad = ortam.get("GIRDI_BOLUM") or ""
    if not GUVENLI.match(ad):
        raise SystemExit(f"geçersiz bölüm adı: {ad!r}")
    asama = ortam.get("GIRDI_ASAMA") or "tahmin"
    if asama not in ("tahmin", "senaryo", "uret"):
        raise SystemExit(f"geçersiz aşama: {asama!r}")
    return {"bolum": ad, "tur": "", "karar": "", "asama": asama,
            "gonder": "false" if ortam.get("GIRDI_GONDER") == "false" else "true"}


CEVAP = {
    ("s", "onay"): "Senaryo onaylandı. Üretim başladı; video hazır olunca buraya gelecek.",
    ("s", "red"): "Senaryo reddedildi. Bölüm üretilmeyecek.",
    ("s", "not"): "Notun kaydedildi. Senaryo düzeltilip yeniden onaya gelecek.",
    ("v", "onay"): "Video onaylandı ve yayına hazır olarak işaretlendi.",
    ("v", "red"): "Video reddedildi.",
    ("v", "not"): "Notun kaydedildi. Video düzeltilip yeniden onaya gelecek.",
}


def kaydet(ortam=os.environ) -> dict:
    i = coz(ortam)
    kayit = {"zaman": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "tur": "senaryo" if i["tur"] == "s" else "video", "karar": i["karar"],
             "not": (ortam.get("ONAY_NOT") or "")[:2000]}
    with open(os.path.join("bolumler", i["bolum"], "kararlar.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(kayit, ensure_ascii=False) + "\n")
    return {**i, **kayit}


if __name__ == "__main__":
    komut = sys.argv[1] if len(sys.argv) > 1 else "coz"
    if komut == "coz":
        s = coz()
        print("\n".join(f"{k}={s[k]}" for k in ("bolum", "asama", "gonder")))
    elif komut == "kaydet":
        s = kaydet()
        if os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"):
            import telegram

            telegram.mesaj(f"{s['bolum']}: " + CEVAP[("s" if s["tur"] == "senaryo" else "v", s["karar"])])
    elif komut == "baslik":
        s = coz()
        print(f"{s['bolum']} {'senaryo' if s['tur'] == 's' else 'video'} {s['karar']}")
