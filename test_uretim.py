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




def test_okunus():
    from okunus import okunus, sayi, sira
    assert sayi(1461) == "bin dört yüz altmış bir" and sayi(1000) == "bin" and sira(63) == "altmış üçüncü"
    assert okunus("II. Mehmed 1452–1481 arasında %75'ini aldı.", {}) == \
        "ikinci Mehmed bin dört yüz elli iki ile bin dört yüz seksen bir arasında yüzde yetmiş beşini aldı."
    assert okunus("Hz. Ömer b. Hattâb (r.a.) geldi.", {}) == "Hazreti Ömer bin Hattâb radıyallâhu anh geldi."
    assert okunus("Resûlullah (s.a.v.) buyurdu.", {}) == "Resûlullah sallallâhu aleyhi ve sellem buyurdu."
    assert okunus("Ebû Talha'nın bahçesi.", {}) == "Ebû Talha'nın bahçesi."        # sayısız metin değişmez
    assert okunus("Beyruhâ", {"Beyruhâ": "Bey-ru-hâ"}) == "Bey-ru-hâ"
    print("geçti: test_okunus")


def test_kapi():
    import tempfile
    from kapi import ButceAsildi, Kapi
    with tempfile.TemporaryDirectory() as d:
        k = Kapi(os.path.join(d, "defter.jsonl"), 0.10, os.path.join(d, "ob"))
        sayac = []
        uret = lambda: (sayac.append(1), b"veri")[1]
        y1 = k.cagir("gorsel", {"a": 1}, "img", 0.04, uret)
        y2 = k.cagir("gorsel", {"a": 1}, "img", 0.04, uret)           # ikinci kez ödenmez
        assert y1 == y2 and len(sayac) == 1 and k.harcanan() == 0.04
        assert k.tahmin([("gorsel", {"a": 1}, "img", 0.04), ("gorsel", {"a": 2}, "img", 0.04),
                         ("gorsel", {"a": 2}, "img", 0.04)]) == (0.04, 1, 1)
        k.cagir("gorsel", {"a": 2}, "img", 0.04, uret)
        try:
            k.cagir("gorsel", {"a": 3}, "img", 0.04, uret)            # bütçe 0,10: üçüncü çağrı durur
            raise AssertionError("bütçe aşılmalıydı")
        except ButceAsildi:
            pass
        try:
            Kapi(os.path.join(d, "d2.jsonl"), 1, os.path.join(d, "ob")).cagir(
                "ses", {"x": 1}, "mp3", 0.01, lambda: (_ for _ in ()).throw(OSError("ağ")), deneme=1)
            raise AssertionError("hata vermeliydi")
        except RuntimeError:
            pass
    print("geçti: test_kapi")


def test_bolum_denetimi():
    import copy
    import bolum as bd
    kok = os.path.dirname(os.path.abspath(__file__))
    klasor = os.path.join(kok, "bolumler", "ebu-talha")
    b = json.load(open(os.path.join(klasor, "bolum.json"), encoding="utf-8"))
    h, _ = bd.denetle(b, klasor)
    assert h == [], h
    k = copy.deepcopy(b)
    del k["cumleler"][1]["kaynak"]
    k["cumleler"][2]["metin"] = "Bursevî der ki bu böyledir."
    k["planlar"][3]["cumle"] = ["yok"]
    h, _ = bd.denetle(k, klasor)
    assert any("kaynak yok" in x for x in h) and any("Bursevî" in x for x in h) and any("bilinmeyen cümle" in x for x in h)
    print("geçti: test_bolum_denetimi")


def test_denetim_puani():
    import numpy as np
    import denetim
    tam = {"maddeler": [{"ad": ad, "gordugum": "hurma ağaçları ve kerpiç duvar görünüyor", "hukum": "geçti"}
                        for ad, _, _ in denetim.MADDELER]}
    assert denetim.puanla(tam) == (10, [])
    tam["maddeler"][0]["hukum"] = "kaldı"          # büyük hata: -3
    tam["maddeler"][4]["hukum"] = "kaldı"          # küçük hata: -1
    assert denetim.puanla(tam)[0] == 6
    tam["maddeler"][1]["gordugum"] = "yok"         # kanıtsız cevap sayılmaz
    assert denetim.puanla(tam)[0] is None
    sira = iter([{"maddeler": []}, {"maddeler": [{"ad": ad, "gordugum": "avlu, kuyu ve hurma gölgesi var", "hukum": "geçti"}
                                                  for ad, _, _ in denetim.MADDELER]}])
    kare = np.full((64, 36, 3), 120, np.uint8)
    assert denetim.goz(kare, "cümle", "m", sor=lambda *_: next(sira))[0] == 10      # geçersiz cevapta yeniden sorar
    assert denetim.kare_olc(np.zeros((8, 8, 3), np.uint8)) and not denetim.kare_olc(
        np.random.default_rng(1).integers(0, 255, (64, 64, 3)).astype(np.uint8))
    print("geçti: test_denetim_puani")


def test_ses_ve_gorsel_sahte_motorla():
    """Ücretli çağrılar sahte motorla: zamanlar ölçülür, ikinci çalıştırma önbellekten gelir."""
    import subprocess
    import tempfile
    import gorsel
    import ses
    from kapi import Kapi
    sayac = []

    def sahte(metin, aday):
        sayac.append(metin)
        with tempfile.NamedTemporaryFile(suffix=".mp3") as f:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                            f"sine=frequency=180:duration={0.2 + 0.05 * len(metin.split()):.2f}", f.name], check=True)
            return open(f.name, "rb").read()

    b = {"cumleler": [{"id": "a", "metin": "II. Mehmed geldi."}, {"id": "t", "bekle": 1.0}, {"id": "b", "metin": "Sonra gitti."}],
         "planlar": [{"istem": "palm grove", "cumle": ["a"]}, {"kart": "ayet", "cumle": ["t"]}, {"istem": "palm grove", "cumle": ["b"]}]}
    ayar = {"ses": {"motor": "sahte", "ses": "x"}, "gorsel": {"saglayici": "gemini", "aday": 2}, "fiyatlar": {"sahte": 1.0}}
    with tempfile.TemporaryDirectory() as d:
        k = Kapi(os.path.join(d, "defter.jsonl"), 5, os.path.join(d, "ob"))
        s = ses.uret(b, ayar, os.path.join(d, "ses"), k, motorlar={"sahte": (sahte, [])})
        z = s["zamanlar"]
        assert sayac[0] == "ikinci Mehmed geldi."                      # motora okunuş gider
        assert abs(z["a"][0] - ses.ACILIS_SN) < 0.01 and z["a"][1] < z["t"][0] < z["t"][1] < z["b"][0] < z["b"][1]
        assert abs((z["t"][1] - z["t"][0]) - 1.0) < 0.01
        assert abs(ses._sure(s["dosya"]) - (z["b"][1] + ses.ARA_SN + ses.KAPANIS_SN)) < 0.15
        ses.uret(b, ayar, os.path.join(d, "ses"), k, motorlar={"sahte": (sahte, [])})
        assert len(sayac) == 2                                         # ikinci tur önbellekten
        cagri = []
        r = gorsel.uret(b, ayar, k, cagri=lambda m, i, t: (cagri.append(t), b"img")[1])
        assert len(cagri) == 2 and r[0] == r[2] and len(r[0]) == 2     # aynı istem iki planda: bir kez üretilir
        assert "No human faces" in gorsel.tam_istem("x")
    print("geçti: test_ses_ve_gorsel_sahte_motorla")



def test_gorsel_saglayicilari_sahte_ag():
    """Sağlayıcı cevaplarının çözülmesi; ağ sahte (gerçek API'ler bu ortamdan erişilemez)."""
    import base64
    import sys
    import types
    import gorsel

    gonderilen = []

    class Cevap:
        def __init__(self, kod, veri):
            self.status_code, self._veri, self.text = kod, veri, json.dumps(veri)
            self.content = b"PNG"

        def json(self):
            return self._veri

        def raise_for_status(self):
            pass

    sira = []

    def post(url, **kw):
        gonderilen.append((url, kw.get("json")))
        return sira.pop(0)

    sahte = types.SimpleNamespace(post=post, get=lambda *a, **k: Cevap(200, {}))
    eski = sys.modules.get("requests")
    sys.modules["requests"] = sahte
    os.environ["GEMINI_GORSEL_API_KEY"], os.environ["RECRAFT_API_KEY"] = "g", "r"
    try:
        b64 = base64.b64encode(b"resim").decode()
        sira[:] = [Cevap(400, {"error": "Unknown field seed"}),
                   Cevap(200, {"candidates": [{"content": {"parts": [{"text": "x"}, {"inlineData": {"data": b64}}]}}]})]
        assert gorsel._gemini("gemini-nano-banana-2.1", "istem", 5) == b"resim"
        assert "seed" not in gonderilen[-1][1]["generationConfig"]                  # tohumsuz yeniden denedi
        assert gonderilen[-1][1]["generationConfig"]["imageConfig"]["aspectRatio"] == "9:16"
        sira[:] = [Cevap(200, {"candidates": [{"finishReason": "PROHIBITED_CONTENT"}]})]
        try:
            gorsel._gemini("m", "istem", 5)
            raise AssertionError("hata vermeliydi")
        except RuntimeError as h:
            assert "PROHIBITED_CONTENT" in str(h)
        sira[:] = [Cevap(400, {"error": "invalid size"}), Cevap(200, {"data": [{"b64_json": b64}]})]
        assert gorsel._recraft("recraftv4_1", "istem", 5) == b"resim"
        assert gonderilen[-1][1]["size"] == "2:3"                                  # 9:16 reddedilince dikey yedek
        ayar = {"gorsel": {"saglayici": "gemini", "aday": 1, "saglayicilar": {"recraft": {"usd": 0.04}}}}
        assert gorsel.ayar_coz(ayar) == ("gemini", "gemini-nano-banana-2.1", 0.0504)
        assert gorsel.ayar_coz(ayar, "recraft")[2] == 0.04
        assert set(gorsel.hazir_saglayicilar()) >= {"gemini", "recraft"}
    finally:
        del os.environ["GEMINI_GORSEL_API_KEY"], os.environ["RECRAFT_API_KEY"]
        if eski is not None:
            sys.modules["requests"] = eski
        else:
            del sys.modules["requests"]
    print("geçti: test_gorsel_saglayicilari_sahte_ag")


if __name__ == "__main__":
    for ad, f in sorted(globals().items()):
        if ad.startswith("test_"):
            f()
    print("hepsi geçti")
