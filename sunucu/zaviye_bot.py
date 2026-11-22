"""Zâviye sunucu botu: Telegram düğmelerini GitHub'a iletir, zamanlanmış işi başlatır, sessiz arızayı haber verir.

Yalnız standart kütüphane kullanır. Webhook yok, dışarıdan port açılmaz: Telegram'ı uzun yoklamayla dinler.
Gizli değerler ortam dosyasından (/etc/zaviye/ortam) gelir; depoya girmez. Claude ya da başka bir ücretli API kullanmaz.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
SOHBET = str(os.environ["TELEGRAM_CHAT_ID"])
GH = os.environ["GITHUB_TOKEN"]
DEPO = os.environ.get("GITHUB_DEPO", "Yass61/uretim-hatti")
DURUM = os.environ.get("ZAVIYE_DURUM", "/var/lib/zaviye/durum.json")
PROGRAM = os.environ.get("ZAVIYE_PROGRAM", "/etc/zaviye/program.json")
TZ = ZoneInfo("Europe/Istanbul")
KIMLIK = re.compile(r"^[sv]:[a-z0-9][a-z0-9-]{0,60}$")


def _istek(url, veri=None, baslik=None, zaman=70):
    r = urllib.request.Request(url, data=json.dumps(veri).encode() if veri is not None else None,
                               headers={"content-type": "application/json", **(baslik or {})})
    with urllib.request.urlopen(r, timeout=zaman) as s:
        g = s.read()
        return s.status, (json.loads(g) if g else {})


def tg(yontem, veri=None, zaman=70):
    try:
        return _istek(f"https://api.telegram.org/bot{TOKEN}/{yontem}", veri or {}, zaman=zaman)[1]
    except Exception as e:
        print("telegram hata:", yontem, type(e).__name__, file=sys.stderr)
        return {}


def gh(yol, veri=None):
    return _istek(f"https://api.github.com/repos/{DEPO}/{yol}", veri,
                  {"authorization": f"Bearer {GH}", "accept": "application/vnd.github+json",
                   "user-agent": "zaviye-bot"}, zaman=30)


def haber(metin):
    tg("sendMessage", {"chat_id": SOHBET, "text": metin})


def durum_oku():
    try:
        return json.load(open(DURUM))
    except Exception:
        return {"yapilan": {}, "bildirilen": [], "bekleyen": {}}


def durum_yaz(d):
    os.makedirs(os.path.dirname(DURUM), exist_ok=True)
    gecici = DURUM + ".tmp"
    json.dump(d, open(gecici, "w"))
    os.replace(gecici, DURUM)


def iletir(yuk):
    try:
        return gh("dispatches", {"event_type": "telegram-onay", "client_payload": yuk})[0] == 204
    except Exception:
        return False


def guncelleme_isle(g):
    cq = g.get("callback_query")
    if cq:
        if str(cq.get("message", {}).get("chat", {}).get("id")) != SOHBET:
            return
        kimlik, _, karar = str(cq.get("data") or "").partition("|")
        if not KIMLIK.match(kimlik) or karar not in ("onay", "red", "not"):
            return
        if karar == "not":
            tg("answerCallbackQuery", {"callback_query_id": cq["id"]})
            tg("sendMessage", {"chat_id": SOHBET, "text": f"Düzeltme notunu bu mesajı yanıtlayarak yaz.\n#{kimlik}",
                               "reply_markup": {"force_reply": True}})
            return
        tamam = iletir({"kimlik": kimlik, "karar": karar, "not": ""})
        tg("answerCallbackQuery", {"callback_query_id": cq["id"],
                                   "text": "Karar alındı." if tamam else "GitHub'a iletilemedi; biraz sonra yeniden dene.",
                                   "show_alert": not tamam})
        return
    m = g.get("message")
    if not m or not m.get("text") or str(m.get("chat", {}).get("id")) != SOHBET:
        return
    es = re.search(r"#([sv]:[a-z0-9-]+)\s*$", (m.get("reply_to_message") or {}).get("text", ""))
    if es and KIMLIK.match(es[1]):
        if not iletir({"kimlik": es[1], "karar": "not", "not": m["text"][:2000]}):
            haber("Not GitHub'a iletilemedi.")


def zamanlanmis(d):
    """program.json: [{"ad": "haftalik", "gun": 0-6 (0=Pazartesi), "saat": "09:00", "is_akisi": "uret.yml", "girdi": {...}}]"""
    try:
        isler = json.load(open(PROGRAM))
    except Exception:
        return
    simdi = datetime.now(TZ)
    for i in isler:
        saat, dk = map(int, i["saat"].split(":"))
        hedef = simdi.replace(hour=saat, minute=dk, second=0, microsecond=0)
        anahtar = f"{i['ad']}-{simdi.date()}"
        if simdi.weekday() != i["gun"] or simdi < hedef or anahtar in d["yapilan"]:
            continue
        d["yapilan"][anahtar] = simdi.isoformat()
        try:
            gh(f"actions/workflows/{i['is_akisi']}/dispatches",
               {"ref": "main", "inputs": i.get("girdi", {})})
            d["bekleyen"][anahtar] = {"ad": i["ad"], "is_akisi": i["is_akisi"], "baslangic": simdi.isoformat()}
        except Exception as e:
            haber(f"Zâviye: '{i['ad']}' üretimi başlatılamadı ({type(e).__name__}). GitHub anahtarını kontrol et.")
    d["yapilan"] = dict(list(d["yapilan"].items())[-60:])


def nobet(d):
    """Başlatılan iş 15 dakikada koşuya dönüşmediyse ve son koşular başarısızsa haber verir (tek seferlik)."""
    simdi = datetime.now(TZ)
    for anahtar, b in list(d["bekleyen"].items()):
        bas = datetime.fromisoformat(b["baslangic"])
        try:
            kosular = gh(f"actions/workflows/{b['is_akisi']}/runs?per_page=5&event=workflow_dispatch")[1]["workflow_runs"]
        except Exception:
            continue
        yeni = [k for k in kosular if datetime.fromisoformat(k["created_at"].replace("Z", "+00:00")) >= bas.astimezone(ZoneInfo("UTC"))]
        if yeni:
            del d["bekleyen"][anahtar]
        elif simdi - bas > timedelta(minutes=15):
            haber(f"Zâviye: '{b['ad']}' üretimi başlatılmadı (GitHub koşu açmadı). Elle başlatmak gerekebilir.")
            del d["bekleyen"][anahtar]
    try:
        for k in gh("actions/runs?per_page=10&status=failure")[1]["workflow_runs"]:
            if k["id"] not in d["bildirilen"] and k.get("run_attempt", 1) >= 1 and k["name"] != "Test":
                d["bildirilen"] = (d["bildirilen"] + [k["id"]])[-100:]
                haber(f"Zâviye: '{k['name']}' çalışması başarısız oldu.\n{k['html_url']}")
    except Exception:
        pass


def main():
    tg("deleteWebhook", {})   # webhook kalmışsa uzun yoklama çalışmaz
    d = durum_oku()
    if not d["bildirilen"]:       # ilk açılışta eski hataları bildirme
        try:
            d["bildirilen"] = [k["id"] for k in gh("actions/runs?per_page=30&status=failure")[1]["workflow_runs"]]
        except Exception:
            pass
        durum_yaz(d)
    ofset, son_nobet = None, 0.0
    while True:
        veri = {"timeout": 50, "allowed_updates": ["callback_query", "message"]}
        if ofset is not None:
            veri["offset"] = ofset
        for g in tg("getUpdates", veri, zaman=70).get("result", []):
            ofset = g["update_id"] + 1
            try:
                guncelleme_isle(g)
            except Exception as e:
                print("işlem hatası:", type(e).__name__, file=sys.stderr)
        if time.time() - son_nobet > 300:
            son_nobet = time.time()
            zamanlanmis(d)
            nobet(d)
            durum_yaz(d)
        if not ofset:
            time.sleep(2)


if __name__ == "__main__":
    main()
