"""Onaylanan videoyu Postproxy üzerinden yayınlar (Instagram Reel; ayar.json "yayin" bölümü).

  python3 paylas.py bolumler/<ad>/bolum.json [--deneme]

Yalnız Telegram'dan "video onay" geldiğinde ya da elle "yayinla" aşamasıyla çalışır.
ayar.yayin.taslak = true iken gönderi Postproxy'de TASLAK olarak açılır; panelden bakıp yayınlarsın.
Anahtar: POSTPROXY_API_KEY (GitHub gizli alanı). Video dosyası doğrudan yüklenir (multipart).
"""
from __future__ import annotations

import json
import os
import sys

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


def form(bolum: dict, yayin: dict) -> list[tuple[str, str]]:
    alanlar = [("post[body]", aciklama(bolum)), ("platforms[instagram][format]", "reel")]
    alanlar += [("profiles[]", p) for p in yayin.get("profiller") or ["instagram"]]
    if yayin.get("taslak", True):
        alanlar.append(("post[draft]", "true"))
    return alanlar


def paylas(bolum_yolu: str, deneme: bool = False) -> dict:
    import requests

    klasor = os.path.dirname(os.path.abspath(bolum_yolu))
    bolum = json.load(open(bolum_yolu, encoding="utf-8"))
    yayin = json.load(open(os.path.join(KOK, "ayar.json"), encoding="utf-8")).get("yayin") or {}
    video = os.path.join(klasor, "uretim", "video.mp4")
    if not os.path.exists(video):
        raise SystemExit("video yok: önce üretim gerekli")
    alanlar = form(bolum, yayin)
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
        f.write(json.dumps({"postproxy": sonuc.get("id") or sonuc, "taslak": yayin.get("taslak", True)},
                           ensure_ascii=False) + "\n")
    return sonuc


if __name__ == "__main__":
    s = paylas(sys.argv[1], "--deneme" in sys.argv)
    print(json.dumps(s, ensure_ascii=False, indent=1)[:1500])
    if "--deneme" not in sys.argv and os.environ.get("TELEGRAM_BOT_TOKEN"):
        import telegram
        b = json.load(open(sys.argv[1], encoding="utf-8"))
        ne = "taslak olarak Postproxy'ye yüklendi (panelden yayınla)" if (json.load(open(os.path.join(
            KOK, "ayar.json"), encoding="utf-8")).get("yayin") or {}).get("taslak", True) else "Instagram'a gönderildi"
        telegram.mesaj(f"📤 {b['baslik']}: {ne}.")
