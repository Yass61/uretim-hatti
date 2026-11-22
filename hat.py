"""Üretim hattı: bir bölüm dosyasından Telegram'daki onaya kadar bütün adımlar.

Kullanım:
  python3 hat.py bolumler/<ad>/bolum.json --tahmin     # ne kadar tutar? para harcamaz
  python3 hat.py bolumler/<ad>/bolum.json --senaryo    # denetle, senaryoyu Telegram'a onaya gönder
  python3 hat.py bolumler/<ad>/bolum.json              # üret, denetle, videoyu Telegram'a onaya gönder
  ... --gonderme                                        # Telegram'a hiçbir şey gönderme (deneme)

Adımlar: denetim → ses → görsel → kurgu → kalite denetimi → Telegram.
Yarıda kesilirse yeniden çalıştırmak yeter: üretilmiş ses ve görseller önbellekten gelir, ödenmez.
Anahtarı olmayan adım atlanır ve raporda söylenir (ses yoksa sessiz kurulur, fal yoksa eldeki görseller kullanılır).
Çıktılar bolumler/<ad>/uretim/ klasörüne yazılır: video.mp4, durum.json, defter.jsonl.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone

import numpy as np
from PIL import Image

import bolum as bolum_denetimi
import denetim
import gorsel
import kurgu
import ses as ses_uretimi
from kapi import Kapi, ozet

KOK = os.path.dirname(os.path.abspath(__file__))


def ayar_oku() -> dict:
    return json.load(open(os.path.join(KOK, "ayar.json"), encoding="utf-8"))


def kuran_var(sure: int, ayet: int) -> bool:
    try:
        kurgu.ayet_oku(sure, ayet)
        return True
    except (SystemExit, FileNotFoundError):
        return False


ONARIM_TURU = 2                                          # kalite kalırsa en çok iki onarım turu


class Hat:
    def __init__(self, bolum_yolu: str, gonder: bool = True):
        self.yol = os.path.abspath(bolum_yolu)
        self.klasor = os.path.dirname(self.yol)
        self.ad = os.path.basename(self.klasor)
        self.cikti = os.path.join(self.klasor, "uretim")
        os.makedirs(self.cikti, exist_ok=True)
        self.bolum = json.load(open(self.yol, encoding="utf-8"))
        self.ayar = ayar_oku()
        self.kapi = Kapi(os.path.join(self.cikti, "defter.jsonl"), self.bolum.get("butce_usd", self.ayar["butce_usd"]))
        self.gonder = gonder and bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))
        self.durum = {"bolum": self.ad, "adimlar": {}, "notlar": []}

    # ----------------------------------------------------------- yardımcılar
    def _kaydet(self) -> None:
        self.durum["guncelleme"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.durum["harcanan_usd"] = self.kapi.harcanan()
        json.dump(self.durum, open(os.path.join(self.cikti, "durum.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)

    def _adim(self, ad: str, sonuc: str, **ek) -> None:
        self.durum["adimlar"][ad] = {"sonuc": sonuc, **ek}
        print(f"[{ad}] {sonuc}", flush=True)
        self._kaydet()

    def _not(self, metin: str) -> None:
        self.durum["notlar"].append(metin)
        print("NOT:", metin, flush=True)

    def _telegram(self):
        import telegram

        return telegram

    # ---------------------------------------------------------------- adımlar
    def denetle(self) -> bool:
        veri = os.path.exists(kurgu.KURAN)
        hatalar, uyarilar = bolum_denetimi.denetle(self.bolum, self.klasor, kuran_var if veri else None)
        if not veri and self.bolum.get("ayet"):
            hatalar.append(f"Kur'an verisi bulunamadı ({kurgu.KURAN}); ayet kartı kurulamaz")
        self.hatalar, self.uyarilar = hatalar, uyarilar
        self._adim("denetim", "kaldı" if hatalar else "geçti", hatalar=hatalar, uyarilar=uyarilar)
        return not hatalar

    def tahmin(self) -> str:
        tutar, yeni, hazir = gorsel.tahmin(self.bolum, self.ayar, self.kapi)
        harf = sum(len(c.get("metin") or "") for c in self.bolum["cumleler"])
        s = self.ayar.get("ses")
        ses_tutar = (self.ayar["fiyatlar"].get(s["motor"], 0) * harf / 1000) if s else 0.0
        return (f"Görsel: {yeni} yeni çağrı ({tutar:.2f} USD), {hazir} tanesi önbellekte\n"
                f"Ses: {harf} harf, en çok {ses_tutar:.2f} USD" + ("" if s else " (ses seçilmedi; sessiz kurulur)") +
                f"\nToplam en çok {tutar + ses_tutar:.2f} USD · bölüm bütçesi {self.kapi.butce:.2f} USD · "
                f"şimdiye kadar {self.kapi.harcanan():.2f} USD")

    def _tilavet_hazirla(self) -> None:
        """ayar.tilavet.okuyucu varsa ayetin okunuşunu indirir; ayet kartının süresini tilavete eşitler."""
        okuyucu = (self.ayar.get("tilavet") or {}).get("okuyucu")
        if not okuyucu or not self.bolum.get("ayet") or (self.bolum.get("tilavet") or {}).get("dosya"):
            return
        import tilavet
        sure, ayet = self.bolum["ayet"]
        hedef = os.path.join(self.cikti, f"tilavet_{okuyucu}_{sure:03d}{ayet:03d}.mp3")
        try:
            if not os.path.exists(hedef):
                tilavet.indir(okuyucu, sure, ayet, hedef)
        except Exception as hata:
            self._not(f"Tilavet indirilemedi ({okuyucu}): {hata}. Ayet kartı tilavetsiz.")
            return
        self.bolum["tilavet"] = {"dosya": os.path.relpath(hedef, self.klasor), "okuyucu": okuyucu,
                                 "okuyucu_adi": tilavet.OKUYUCULAR.get(okuyucu, okuyucu)}
        uzunluk = ses_uretimi._sure(hedef)
        for c in self.bolum["cumleler"]:
            if c["id"] == "tilavet":
                c["bekle"] = round(uzunluk + 0.8, 2)

    def ses(self) -> None:
        if not self.ayar.get("ses"):
            self._not("Ses seçilmedi (ayar.json); video sessiz kuruldu, süreler tahminden.")
            return self._adim("ses", "atlandı")
        self._tilavet_hazirla()
        try:
            s = ses_uretimi.uret(self.bolum, self.ayar, os.path.join(self.cikti, "ses"), self.kapi)
        except RuntimeError as hata:
            self._not(f"Ses üretilemedi: {hata}. Video sessiz kuruldu.")
            return self._adim("ses", "atlandı", neden=str(hata))
        t = self.bolum.get("tilavet") or {}
        tyol = os.path.join(self.klasor, t["dosya"]) if t.get("dosya") else None
        if tyol and os.path.exists(tyol) and "tilavet" in s["zamanlar"]:
            bas, bit = s["zamanlar"]["tilavet"]
            ses_uretimi.tilavet_ekle(s["dosya"], tyol, bas, bit - bas, s["dosya"])
        self.bolum["ses"] = {**s, "dosya": os.path.relpath(s["dosya"], self.klasor)}
        self._adim("ses", "üretildi", motor=s["motor"], sure=round(max(b for _, b in s["zamanlar"].values()), 1))

    def gorseller(self, planlar: list[int] | None = None) -> None:
        istemli = [i for i, p in enumerate(self.bolum["planlar"]) if p.get("istem") and not p.get("kart")
                   and (planlar is None or i in planlar)]
        if not istemli:
            return self._adim("gorsel", "atlandı", neden="planlarda görsel istemi yok; eldeki dosyalar kullanılır")
        saglayici = gorsel.ayar_coz(self.ayar)[0]
        if not gorsel.anahtar(saglayici):
            eksik = [i + 1 for i in istemli if not (self.bolum["planlar"][i].get("gorsel") and os.path.exists(
                os.path.join(self.klasor, self.bolum["planlar"][i]["gorsel"])))]
            if eksik:
                raise SystemExit(f"{saglayici} görsel anahtarı yok ve şu planların hazır görseli de yok: {eksik}")
            self._not(f"{saglayici} görsel anahtarı yok; yeni görsel üretilmedi, eldeki yer tutucu görseller kullanıldı.")
            return self._adim("gorsel", "atlandı", neden=f"{saglayici} anahtarı yok")
        adaylar = gorsel.uret(self.bolum, self.ayar, self.kapi, planlar=planlar)
        goz_var = denetim.goz_anahtari() is not None
        secimler = {}
        for i, yollar in adaylar.items():
            p = self.bolum["planlar"][i]
            cumle = " ".join(c["metin"] for c in self.bolum["cumleler"] if c["id"] in (p.get("cumle") or []) and c.get("metin"))
            puanlar = []
            for y in yollar:
                olcum, sorun = denetim.gorsel_puani(y)
                goz = denetim.goz(y, cumle, self.ayar["denetim"]["model"])[0] if goz_var and not sorun else None
                puanlar.append(((goz if goz is not None else -1), olcum, y))
            puanlar.sort(reverse=True)
            p["gorsel"] = puanlar[0][2]
            secimler[i + 1] = {"secilen": os.path.basename(puanlar[0][2]), "goz": puanlar[0][0], "olcum": puanlar[0][1]}
        self._adim("gorsel", "üretildi", saglayici=saglayici, secimler=secimler)

    def kur(self) -> None:
        self.video = os.path.join(self.cikti, "video.mp4")
        imza = ozet({"bolum": self.bolum, "surum": 2})
        onceki = os.path.join(self.cikti, "video.imza")
        if os.path.exists(self.video) and os.path.exists(onceki) and open(onceki).read() == imza:
            self.kurgu = kurgu.kur(self.bolum, self.klasor, self.video, onizleme=[])
            return self._adim("kurgu", "değişiklik yok; eldeki video kullanıldı")
        self.kurgu = kurgu.kur(self.bolum, self.klasor, self.video)
        open(onceki, "w").write(imza)
        self._adim("kurgu", "kuruldu", sure=round(self.kurgu["sure"], 1))

    def kalite(self) -> bool:
        k, d = self.kurgu, self.ayar["denetim"]
        sorunlar = denetim.yazi_olc(k["cumleler"])
        sorunlar += denetim.video_olc(self.video, k["sure"], bool(self.bolum.get("ses")))
        goz_var, puanlar = denetim.goz_anahtari() is not None, []
        bozuk: set[int] = set()
        obekler = [(pr["bas"], pr["bit"]) for c in k["cumleler"] for pr in c.get("parcalar") or []]
        for t in denetim.ornek_anlar(k["planlar"], d["ornek_kare"], obekler):
            yol = os.path.join(self.cikti, f"kare_{t:06.2f}.jpg")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", self.video,
                            "-frames:v", "1", "-q:v", "3", yol], check=True)
            kare = np.asarray(Image.open(yol).convert("RGB"))
            sorunlar += [f"{t:.1f}. sn: {s}" for s in denetim.kare_olc(kare)]
            if goz_var:
                cumle = " ".join(c.get("metin") or "" for c in k["cumleler"] if c["bas"] <= t < c["bit"])
                kart = any(p.get("kart") and p["bas"] <= t < p["bit"] for p in k["planlar"])
                puan, bulgu = denetim.goz(kare, cumle, d["model"], kart=kart)
                puanlar.append(puan)
                if puan is None:
                    sorunlar.append(f"{t:.1f}. sn: kare denetlenemedi ({bulgu[0]})")
                elif puan < d["gecme_puani"]:
                    sorunlar += [f"{t:.1f}. sn ({puan}/10): {b}" for b in bulgu]
                    if not kart:                         # görsel sahne: yeniden üretilerek onarılabilir
                        bozuk.update(i for i, p in enumerate(k["planlar"]) if p["bas"] <= t < p["bit"])
        self.kalite_sonucu = {"gecti": not sorunlar, "sorunlar": sorunlar, "puanlar": puanlar,
                              "goz": "var" if goz_var else "yok", "bozuk_planlar": sorted(bozuk),
                              "yalniz_gorsel": bool(bozuk) and all("/10)" in x for x in sorunlar)}
        self._adim("kalite", "geçti" if not sorunlar else "kaldı", **self.kalite_sonucu)
        return not sorunlar

    # ----------------------------------------------------------------- akışlar
    def senaryo_onayi(self) -> int:
        gecti = self.denetle()
        metin = bolum_denetimi.ozet_metni(self.bolum, self.hatalar, self.uyarilar)
        if gecti:
            metin += "\n\n" + self.tahmin()
        print(metin)
        if self.gonder:
            self._telegram().mesaj(metin, f"s:{self.ad}" if gecti else None)
        return 0 if gecti else 1

    def uret(self) -> int:
        if not self.denetle():
            metin = bolum_denetimi.ozet_metni(self.bolum, self.hatalar, self.uyarilar)
            print(metin)
            if self.gonder:
                self._telegram().mesaj("Üretim başlamadı.\n\n" + metin)
            return 1
        self.ses()
        self.gorseller()
        self.kur()
        gecti = self.kalite()
        for tur in range(1, ONARIM_TURU + 1):            # yalnız görselden kalan sahneler yeni tohumla yeniden üretilir
            if gecti or not self.kalite_sonucu.get("yalniz_gorsel"):
                break
            bozuk = self.kalite_sonucu["bozuk_planlar"]
            self._not(f"Onarım {tur}: {len(bozuk)} sahne yeniden üretildi (plan {', '.join(str(i + 1) for i in bozuk)}).")
            for i in bozuk:
                p = self.bolum["planlar"][i]
                p["yeniden"] = p.get("yeniden", 0) + 1
                p.pop("gorsel", None)
            self.gorseller(planlar=bozuk)
            self.kur()
            gecti = self.kalite()
        rapor = denetim.rapor_metni(self.kalite_sonucu)
        aciklama = (f"{self.bolum['baslik']}\n{self.kurgu['sure']:.0f} sn · harcanan {self.kapi.harcanan():.2f} USD\n\n"
                    f"{rapor}" + ("\n\n" + "\n".join("ℹ️ " + n for n in self.durum["notlar"]) if self.durum["notlar"] else ""))
        print(aciklama)
        if self.gonder:
            self._telegram().video(self.video, aciklama, f"v:{self.ad}")
        self._adim("gonderim", "Telegram'a gönderildi" if self.gonder else "gönderilmedi")
        return 0 if gecti else 2


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    hat = Hat(sys.argv[1], gonder="--gonderme" not in sys.argv)
    if "--tahmin" in sys.argv:
        print(hat.tahmin())
    elif "--senaryo" in sys.argv:
        raise SystemExit(hat.senaryo_onayi())
    else:
        raise SystemExit(hat.uret())


if __name__ == "__main__":
    main()
