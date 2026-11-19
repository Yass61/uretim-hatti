"""Telegram üzerinden onay: Yasin yalnız buradan müdahil olur.

Gerekli sırlar: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (yalnız bu sohbetten gelen cevap kabul edilir).
NOT: Ağ çağrıları bu ortamda denenemedi (anahtar yok); saf işlevler test_uretim.py ile sınanır.
"""
from __future__ import annotations

import json
import os
import time

API = "https://api.telegram.org/bot{token}/{yontem}"


def _cagir(yontem: str, veri: dict | None = None, dosyalar: dict | None = None, zaman_asimi: int = 120) -> dict:
    import requests

    url = API.format(token=os.environ["TELEGRAM_BOT_TOKEN"], yontem=yontem)
    r = requests.post(url, data=veri or {}, files=dosyalar, timeout=zaman_asimi)
    cevap = r.json()
    if not cevap.get("ok"):
        raise RuntimeError(f"Telegram {yontem} başarısız: {cevap.get('description')}")
    return cevap["result"]


def dugmeler(kimlik: str, secenekler: list[tuple[str, str]]) -> str:
    """Satır içi düğmeler. Geri dönen veri 'kimlik|kod' biçimindedir (64 bayt sınırı)."""
    satir = []
    for etiket, kod in secenekler:
        veri = f"{kimlik}|{kod}"
        if len(veri.encode()) > 64:
            raise ValueError("düğme verisi 64 baytı aşıyor: " + veri)
        satir.append({"text": etiket, "callback_data": veri})
    return json.dumps({"inline_keyboard": [satir]})


ONAY = [("✅ Onayla", "onay"), ("❌ Reddet", "red"), ("✏️ Düzeltme yazacağım", "not")]


def mesaj(metin: str, kimlik: str | None = None, secenekler=None) -> dict:
    veri = {"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": metin[:4000]}
    if kimlik:
        veri["reply_markup"] = dugmeler(kimlik, secenekler or ONAY)
    return _cagir("sendMessage", veri)


def ses(yol: str, baslik: str) -> dict:
    with open(yol, "rb") as f:
        return _cagir("sendAudio", {"chat_id": os.environ["TELEGRAM_CHAT_ID"], "title": baslik, "caption": baslik},
                      {"audio": f})


def video(yol: str, aciklama: str, kimlik: str | None = None) -> dict:
    veri = {"chat_id": os.environ["TELEGRAM_CHAT_ID"], "caption": aciklama[:1000], "supports_streaming": "true"}
    if kimlik:
        veri["reply_markup"] = dugmeler(kimlik, ONAY)
    with open(yol, "rb") as f:      # bot API sınırı 50 MB; 60 sn'lik video bunun çok altında
        return _cagir("sendVideo", veri, {"video": f}, zaman_asimi=600)


def cevap_coz(guncelleme: dict, sohbet: str) -> tuple[str, str, str] | None:
    """Bir güncellemeden (kimlik, karar, not) çıkarır. Başka sohbetten geleni yok sayar."""
    cq = guncelleme.get("callback_query")
    if cq and str(cq.get("message", {}).get("chat", {}).get("id")) == str(sohbet):
        kimlik, _, kod = (cq.get("data") or "").partition("|")
        return (kimlik, kod, "") if kimlik and kod else None
    m = guncelleme.get("message")
    if m and str(m.get("chat", {}).get("id")) == str(sohbet) and m.get("text"):
        return ("", "metin", m["text"])   # serbest metin: bekleyen son işin düzeltme notu sayılır
    return None


def bekle(kimlik: str, sure_sn: int = 300) -> tuple[str, str] | None:
    """kimlik için karar gelene kadar uzun yoklama yapar. Dönen: (karar, not) ya da None."""
    sohbet, bitis, ofset, not_bekliyor = os.environ["TELEGRAM_CHAT_ID"], time.time() + sure_sn, None, False
    while time.time() < bitis:
        veri = {"timeout": 50, "allowed_updates": json.dumps(["callback_query", "message"])}
        if ofset is not None:
            veri["offset"] = ofset
        for g in _cagir("getUpdates", veri, zaman_asimi=70):
            ofset = g["update_id"] + 1
            c = cevap_coz(g, sohbet)
            if not c:
                continue
            k, karar, metin = c
            if k == kimlik and karar in ("onay", "red"):
                return karar, ""
            if k == kimlik and karar == "not":
                not_bekliyor = True
                mesaj("Düzeltme notunu yaz, bekliyorum.")
            elif karar == "metin" and not_bekliyor:
                return "not", metin
    return None


def album(yollar: list[str], aciklamalar: list[str]) -> list:
    """2-10 görseli tek mesajda yan yana gönderir (karşılaştırma için)."""
    medya, dosyalar = [], {}
    for n, (y, a) in enumerate(zip(yollar, aciklamalar)):
        medya.append({"type": "photo", "media": f"attach://g{n}", "caption": a[:1000]})
        dosyalar[f"g{n}"] = open(y, "rb")
    try:
        return _cagir("sendMediaGroup", {"chat_id": os.environ["TELEGRAM_CHAT_ID"], "media": json.dumps(medya)},
                      dosyalar, zaman_asimi=300)
    finally:
        for f in dosyalar.values():
            f.close()
