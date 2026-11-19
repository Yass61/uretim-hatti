"""Plan görsellerini üretir. Yazı üretmez; bütün yazılar kurguda bindirilir.

Sağlayıcılar (ayar.json → gorsel.saglayici):
  gemini  : Google Nano Banana 2.1 (gemini-nano-banana-2.1). GEMINI_GORSEL_API_KEY, yoksa GEMINI_API_KEY.
            2K dikey görsel 0,0504 USD, 1K 0,0336 USD (Gemini API fiyat sayfası, Ekim 2026).
  recraft : Recraft'ın kendi API'si, aracısız. RECRAFT_API_KEY. V4.1 0,035 USD, V4 0,04 USD.
  fal     : fal üzerinden Recraft V4. FAL_KEY. 0,04 USD.

Her plan için birkaç aday üretilir, adaylar denetimden geçer (denetim.py), en iyisi seçilir.
Çağrılar kapıdan (kapi.py) geçer: aynı istem ikinci kez ödenmez, bölüm bütçesi aşılmaz.
Ağ çağrıları ilk kez Actions'ta denenecek; bu ortamdan bu servislere erişim yok.
"""
from __future__ import annotations

import base64
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

SAGLAYICILAR = {
    #            varsayılan model                   görsel başı USD   anahtar(lar)
    "gemini":  ("gemini-nano-banana-2.1",           0.0504,           ("GEMINI_GORSEL_API_KEY", "GEMINI_API_KEY")),
    "recraft": ("recraftv4_1",                      0.035,            ("RECRAFT_API_KEY",)),
    "fal":     ("fal-ai/recraft/v4/text-to-image",  0.04,             ("FAL_KEY",)),
}


def tam_istem(istem: str) -> str:
    return f"{istem.strip()} {STIL} {YASAK}"


def anahtar(saglayici: str) -> str | None:
    return next((os.environ[a] for a in SAGLAYICILAR[saglayici][2] if os.environ.get(a)), None)


def hazir_saglayicilar() -> list[str]:
    return [s for s in SAGLAYICILAR if anahtar(s)]


# ------------------------------------------------------------------ sağlayıcılar
def _gemini(model: str, istem: str, tohum: int, boyut: str = "2K") -> bytes:
    import requests

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    govde = {"contents": [{"parts": [{"text": istem}]}],
             "generationConfig": {"responseModalities": ["IMAGE"], "seed": tohum,
                                  "imageConfig": {"aspectRatio": "9:16", "imageSize": boyut}}}
    r = requests.post(url, params={"key": anahtar("gemini")}, json=govde, timeout=180)
    if r.status_code == 400 and "seed" in r.text:              # tohumu kabul etmeyen sürüm
        govde["generationConfig"].pop("seed")
        r = requests.post(url, params={"key": anahtar("gemini")}, json=govde, timeout=180)
    if r.status_code >= 400:
        raise RuntimeError(f"Gemini {r.status_code}: {r.text[:300]}")
    aday = (r.json().get("candidates") or [{}])[0]
    for p in (aday.get("content") or {}).get("parts") or []:
        veri = p.get("inlineData") or p.get("inline_data")
        if veri and veri.get("data"):
            return base64.b64decode(veri["data"])
    raise RuntimeError(f"Gemini görsel döndürmedi (bitiş nedeni: {aday.get('finishReason')})")


def _recraft(model: str, istem: str, tohum: int) -> bytes:
    import requests

    b = {"Authorization": f"Bearer {anahtar('recraft')}", "Content-Type": "application/json"}
    url = "https://external.api.recraft.ai/v1/images/generations"
    govde = {"prompt": istem[:10000], "model": model, "size": "9:16", "n": 1, "random_seed": tohum,
             "response_format": "b64_json", "image_format": "png"}
    r = requests.post(url, headers=b, json=govde, timeout=180)
    if r.status_code == 400 and "size" in r.text:              # 9:16 desteklenmiyorsa en yakın dikey oran
        govde["size"] = "2:3"
        r = requests.post(url, headers=b, json=govde, timeout=180)
    if r.status_code >= 400:
        raise RuntimeError(f"Recraft {r.status_code}: {r.text[:300]}")
    d = r.json()["data"][0]
    if d.get("b64_json"):
        return base64.b64decode(d["b64_json"])
    g = requests.get(d["url"], timeout=120)                    # adres yaklaşık 24 saat geçerli
    g.raise_for_status()
    return g.content


def _fal(model: str, istem: str, tohum: int) -> bytes:
    import requests

    b = {"Authorization": f"Key {anahtar('fal')}", "Content-Type": "application/json"}
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


CAGRILAR = {"gemini": _gemini, "recraft": _recraft, "fal": _fal}


# ---------------------------------------------------------------------- hat
def ayar_coz(ayar: dict, saglayici: str | None = None) -> tuple[str, str, float]:
    g = ayar["gorsel"]
    s = saglayici or g.get("saglayici", "gemini")
    if s not in SAGLAYICILAR:
        raise ValueError(f"bilinmeyen görsel sağlayıcısı: {s}")
    ozel = (g.get("saglayicilar") or {}).get(s, {})
    return s, ozel.get("model", SAGLAYICILAR[s][0]), float(ozel.get("usd", SAGLAYICILAR[s][1]))


def istekler(bolum: dict, ayar: dict, saglayici: str | None = None,
             planlar: list[int] | None = None) -> list[tuple[int, int, dict]]:
    """Üretilecek her görsel için (plan sırası, aday sırası, önbellek girdisi)."""
    s, model, _ = ayar_coz(ayar, saglayici)
    liste = []
    for i, p in enumerate(bolum["planlar"]):
        if p.get("kart") or not p.get("istem") or (planlar is not None and i not in planlar):
            continue
        istem = tam_istem(p["istem"])                    # tohum istemden türer: aynı istem, aynı görsel
        for a in range(p.get("aday", ayar["gorsel"].get("aday", 2))):
            liste.append((i, a, {"saglayici": s, "model": model, "istem": istem,
                                 "tohum": int(ozet({"i": istem}), 16) % 90000 + a}))
    return liste


def tahmin(bolum: dict, ayar: dict, kapi: Kapi, saglayici: str | None = None) -> tuple[float, int, int]:
    usd = ayar_coz(ayar, saglayici)[2]
    return kapi.tahmin([("gorsel", girdi, "img", usd) for _, _, girdi in istekler(bolum, ayar, saglayici)])


def uret(bolum: dict, ayar: dict, kapi: Kapi, cagri=None, saglayici: str | None = None,
         planlar: list[int] | None = None) -> dict[int, list[str]]:
    """{plan sırası: [aday dosya yolları]} döner. Aynı istem iki planda geçerse bir kez üretilir."""
    s, _, usd = ayar_coz(ayar, saglayici)
    if cagri is None:
        if not anahtar(s):
            raise RuntimeError(f"{s} görsel anahtarı yok ({' ya da '.join(SAGLAYICILAR[s][2])})")
        cagri = CAGRILAR[s]
    sonuc: dict[int, list[str]] = {}
    for i, a, girdi in istekler(bolum, ayar, s, planlar):
        yol = kapi.cagir("gorsel", girdi, "img", usd,
                         lambda g=girdi: cagri(g["model"], g["istem"], g["tohum"]))
        sonuc.setdefault(i, []).append(yol)
    return sonuc
