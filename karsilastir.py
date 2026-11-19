"""Aynı sahneleri anahtarı olan her görsel sağlayıcısıyla üretir, Telegram'a yan yana gönderir.

Kullanım:  python3 karsilastir.py bolumler/ebu-talha/bolum.json [plan numaraları, ör. 1 3 9] [--gonderme]
Plan numarası verilmezse üç tipik sahne seçilir: açılış, orta, kapanış. Her sağlayıcıdan plan başına
tek görsel üretilir (karşılaştırma için aday gerekmez). Harcama defteri: bolumler/<ad>/uretim/karsilastirma.jsonl
"""
from __future__ import annotations

import json
import os
import sys

from PIL import Image

import gorsel
from kapi import Kapi

KOK = os.path.dirname(os.path.abspath(__file__))


def onizleme(yol: str, hedef: str) -> str:
    im = Image.open(yol).convert("RGB")
    bilgi = f"{im.width}x{im.height}"
    im.thumbnail((1080, 1920))
    im.save(hedef, "JPEG", quality=90)
    return bilgi


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    yol, secilen = args[0], [int(x) - 1 for x in args[1:]]
    bolum = json.load(open(yol, encoding="utf-8"))
    ayar = json.load(open(os.path.join(KOK, "ayar.json"), encoding="utf-8"))
    ayar["gorsel"]["aday"] = 1
    istemli = [i for i, p in enumerate(bolum["planlar"]) if p.get("istem") and not p.get("kart")]
    if not secilen:
        secilen = [istemli[0], istemli[len(istemli) // 2], istemli[-1]]
    saglayicilar = gorsel.hazir_saglayicilar()
    if not saglayicilar:
        raise SystemExit("Hiçbir görsel sağlayıcısının anahtarı yok (GEMINI_GORSEL_API_KEY, RECRAFT_API_KEY, FAL_KEY).")
    cikti = os.path.join(os.path.dirname(os.path.abspath(yol)), "uretim", "karsilastirma")
    os.makedirs(cikti, exist_ok=True)
    kapi = Kapi(os.path.join(os.path.dirname(cikti), "karsilastirma.jsonl"), 1.0)
    gonder = "--gonderme" not in sys.argv and os.environ.get("TELEGRAM_BOT_TOKEN")
    hatalar = []
    for i in secilen:
        yollar, notlar = [], []
        for s in saglayicilar:
            _, model, usd = gorsel.ayar_coz(ayar, s)
            try:
                y = gorsel.uret(bolum, ayar, kapi, saglayici=s, planlar=[i])[i][0]
            except Exception as hata:
                hatalar.append(f"{s}, plan {i + 1}: {str(hata)[:200]}")
                print("HATA:", hatalar[-1], flush=True)
                continue
            jpg = os.path.join(cikti, f"plan{i + 1:02d}_{s}.jpg")
            boyut = onizleme(y, jpg)
            yollar.append(jpg)
            notlar.append(f"Plan {i + 1} · {s} ({model}) · {boyut} · {usd:.3f} USD")
            print("üretildi:", notlar[-1], flush=True)
        if gonder and len(yollar) >= 2:
            import telegram
            telegram.album(yollar, notlar)
        elif gonder and yollar:
            import telegram
            telegram._cagir("sendPhoto", {"chat_id": os.environ["TELEGRAM_CHAT_ID"], "caption": notlar[0]},
                            {"photo": open(yollar[0], "rb")})
    ozet = (f"Görsel karşılaştırması: {', '.join(saglayicilar)} · {len(secilen)} sahne · "
            f"harcanan {kapi.harcanan():.2f} USD")
    if len(saglayicilar) == 1:
        ozet += "\nYalnız bir sağlayıcının anahtarı var; karşılaştırma için ikincisinin anahtarı da gerekli."
    if hatalar:
        ozet += "\n\nHatalar:\n" + "\n".join("- " + h for h in hatalar)
    print(ozet)
    if gonder:
        import telegram
        telegram.mesaj(ozet + "\n\nHangi üslubu seçtiğini bana yaz.")
    if hatalar and len(hatalar) == len(secilen) * len(saglayicilar):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
