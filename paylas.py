"""Onaylanan videoyu Postproxy üzerinden yayınlar (Instagram Reel; ayar.json "yayin" bölümü).

  python3 paylas.py bolumler/<ad>/bolum.json [--deneme]

Yalnız Telegram'dan "video onay" geldiğinde ya da elle "yayinla" aşamasıyla çalışır.
ayar.yayin.taslak = true iken gönderi Postproxy'de TASLAK olarak açılır; panelden bakıp yayınlarsın.
Anahtar: POSTPROXY_API_KEY (GitHub gizli alanı). Video dosyası doğrudan yüklenir (multipart).
"""
from __future__ import annotations

import glob
import json
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

KOK = os.path.dirname(os.path.abspath(__file__))
API = "https://api.postproxy.dev/api"


def aciklama(bolum: dict) -> str:
    satirlar = [bolum.get("paylasim_metni") or bolum["baslik"]]
    if bolum.get("alt_baslik"):
        satirlar.append(bolum["alt_baslik"])
    if bolum.get("kaynak_satirlari"):
        satirlar += ["", "Kaynaklar:"] + [f"• {k}" for k in bolum["kaynak_satirlari"]]
    if bolum.get("etiketler"):
        satirlar += ["", " ".join("#" + e.lstrip("#") for e in bolum["etiketler"])]
    return "\n".join(satirlar)[:2200]                       # Instagram açıklama sınırı


def sonraki_slot(yayin: dict, simdi: datetime | None = None) -> str | None:
    """ayar.yayin.takvim ({"gunler":[1,3,5],"saat":"19:00"}; 0=Pazartesi) içinden, daha önce ayrılmış
    en geç slottan sonraki ilk boş zamanı ISO 8601 olarak verir. Takvim yoksa None (hemen/taslak)."""
    t = yayin.get("takvim")
    if not t:
        return None
    tz = ZoneInfo("Europe/Istanbul")
    simdi = simdi or datetime.now(tz)
    dolu = []
    for y in glob.glob(os.path.join(KOK, "bolumler", "*", "yayin.jsonl")):
        for satir in open(y, encoding="utf-8"):
            try:
                z = json.loads(satir).get("zaman")
            except ValueError:
                z = None
            if z:
                dolu.append(datetime.fromisoformat(z))
    en_erken = max([simdi + timedelta(minutes=30)] + [d + timedelta(minutes=1) for d in dolu])
    sa, dk = map(int, t.get("saat", "19:00").split(":"))
    for gun in range(0, 60):
        aday = (en_erken + timedelta(days=gun)).astimezone(tz).replace(hour=sa, minute=dk, second=0, microsecond=0)
        if aday >= en_erken and aday.weekday() in t["gunler"]:
            return aday.isoformat()
    return None


def form(bolum: dict, yayin: dict, zaman: str | None = None) -> list[tuple[str, str]]:
    alanlar = [("post[body]", aciklama(bolum)), ("platforms[instagram][format]", "reel"),
               ("platforms[instagram][made_with_ai]", "true")]       # Meta: gerçekçi yapay zekâ görüntü/ses etiketi
    alanlar += [("profiles[]", p) for p in yayin.get("profiller") or ["instagram"]]
    if yayin.get("taslak", True):
        alanlar.append(("post[draft]", "true"))
    elif zaman:
        alanlar.append(("post[scheduled_at]", zaman))
    return alanlar


def paylas(bolum_yolu: str, deneme: bool = False) -> dict:
    import requests

    klasor = os.path.dirname(os.path.abspath(bolum_yolu))
    bolum = json.load(open(bolum_yolu, encoding="utf-8"))
    yayin = json.load(open(os.path.join(KOK, "ayar.json"), encoding="utf-8")).get("yayin") or {}
    video = os.path.join(klasor, "uretim", "video.mp4")
    if not os.path.exists(video):
        raise SystemExit("video yok: önce üretim gerekli")
    zaman = sonraki_slot(yayin)
    alanlar = form(bolum, yayin, zaman)
    if deneme:
        return {"deneme": True, "alanlar": alanlar}
    anahtar = os.environ.get("POSTPROXY_API_KEY")
    if not anahtar:
        raise SystemExit("POSTPROXY_API_KEY yok")
    with open(video, "rb") as f:
        r = requests.post(f"{API}/posts", headers={"Authorization": f"Bearer {anahtar}"},
                          data=alanlar, files=[("media[]", ("video.mp4", f, "video/mp4"))], timeout=600)
    if r.status_code >= 400:
        raise SystemExit(f"Postproxy {r.status_code}: {r.text[:400]}")
    sonuc = r.json()
    kayit = os.path.join(klasor, "yayin.jsonl")
    with open(kayit, "a", encoding="utf-8") as f:
        f.write(json.dumps({"postproxy": sonuc.get("id") or sonuc, "taslak": yayin.get("taslak", True),
                            "zaman": None if yayin.get("taslak", True) else zaman},
                           ensure_ascii=False) + "\n")
    return sonuc


if __name__ == "__main__":
    s = paylas(sys.argv[1], "--deneme" in sys.argv)
    print(json.dumps(s, ensure_ascii=False, indent=1)[:1500])
    if "--deneme" not in sys.argv and os.environ.get("TELEGRAM_BOT_TOKEN"):
        import telegram
        b = json.load(open(sys.argv[1], encoding="utf-8"))
        y = json.load(open(os.path.join(KOK, "ayar.json"), encoding="utf-8")).get("yayin") or {}
        ne = "taslak olarak Postproxy'ye yüklendi (panelden yayınla)" if y.get("taslak", True) else \
            "takvime alındı: " + json.loads(open(os.path.join(os.path.dirname(os.path.abspath(sys.argv[1])), "yayin.jsonl"), encoding="utf-8").readlines()[-1]).get("zaman", "?")[:16].replace("T", " ")
        telegram.mesaj(f"📤 {b['baslik']}: {ne}.")
