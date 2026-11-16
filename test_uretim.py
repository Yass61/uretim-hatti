"""Üretim hattının anahtar gerektirmeyen sınamaları.  Çalıştır: python3 test_uretim.py"""
import json
import os

import numpy as np
from PIL import features

import kurgu
import ses_provasi
import telegram
from hareket import Ayar, Hareket, HAREKETLER


def test_arapca_dizgi():
    # raqm yoksa Arapça harfler birleşmez; ayet kartı yanlış basılır
    assert features.check("raqm"), "Pillow raqm desteği yok: Arapça metin doğru dizilemez"


def test_parcala():
    p = kurgu.parcala("Ebû Talha, Medine'de hurmalığı en çok olan Ensârîydi.")
    assert " ".join(p) == "Ebû Talha, Medine'de hurmalığı en çok olan Ensârîydi."
    assert all(len(x.split()) <= 4 for x in p)


def test_cizelge_tahmin_ve_ses():
    bolum = {"cumleler": [{"id": "a", "metin": "Bir iki üç dört beş."}, {"id": "b", "bekle": 2.0}],
             "planlar": [{"gorsel": "x", "cumle": ["a"]}, {"kart": "ayet", "cumle": ["b"]}, {"kart": "son", "sure": 1.0}]}
    c, p, toplam = kurgu.cizelge(bolum)
    assert p[0]["bit"] == p[1]["bas"] and abs(toplam - p[-1]["bit"]) < 1e-6
    bolum["ses"] = {"zamanlar": {"a": [0.5, 3.0]}}
    c, p, _ = kurgu.cizelge(bolum)
    assert c[0]["bas"] == 0.5 and abs(c[0]["parcalar"][-1]["bit"] - 3.0) < 1e-6


def test_hareket_kareleri():
    r = np.random.default_rng(1)
    g = (r.random((192, 108, 3)) * 255).astype(np.uint8)
    d = np.linspace(0, 1, 192, dtype=np.float32)[:, None].repeat(108, axis=1)
    for ad in HAREKETLER:
        h = Hareket(g, d, Ayar(hareket=ad, hüzme=0.2))
        a, b = h.kare(0.0, 0.0), h.kare(1.0, 4.0)
        assert a.shape == g.shape and a.dtype == np.uint8
        assert np.abs(a.astype(int) - b.astype(int)).mean() > 0.5, ad + ": hareket yok"
    # aynı tohum aynı kareyi verir (yeniden üretilebilirlik)
    k1 = Hareket(g, d, Ayar()).kare(0.5, 2.0)
    k2 = Hareket(g, d, Ayar()).kare(0.5, 2.0)
    assert (k1 == k2).all()


def test_telegram_dugme_ve_cevap():
    d = json.loads(telegram.dugmeler("b12", telegram.ONAY))
    assert d["inline_keyboard"][0][0]["callback_data"] == "b12|onay"
    g = {"callback_query": {"data": "b12|red", "message": {"chat": {"id": 42}}}}
    assert telegram.cevap_coz(g, "42") == ("b12", "red", "")
    assert telegram.cevap_coz(g, "99") is None            # başka sohbetten gelen onay sayılmaz
    assert telegram.cevap_coz({"message": {"chat": {"id": 42}, "text": "sesi yavaşlat"}}, "42")[1] == "metin"


def test_kor_numaralama():
    a = [{"ses": str(i)} for i in range(10)]
    s1, s2 = ses_provasi.numarala(a, 5), ses_provasi.numarala(a, 5)
    assert s1 == s2 and [n for n, _ in s1] == list(range(1, 11))
    assert [x["ses"] for _, x in s1] != [x["ses"] for x in a]   # sıra karışmış olmalı


def test_ses_adaylari_dosyasi():
    ayar = json.load(open(os.path.join(os.path.dirname(__file__), "ses_adaylari.json"), encoding="utf-8"))
    assert all(x["motor"] in ses_provasi.MOTORLAR and x["ses"] for x in ayar["adaylar"])


if __name__ == "__main__":
    for ad, f in sorted(globals().items()):
        if ad.startswith("test_"):
            f()
            print("geçti:", ad)
    print("hepsi geçti")
