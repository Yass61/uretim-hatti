"""Ücretli çağrıların tek kapısı: önbellek, harcama defteri, bölüm bütçesi, yeniden deneme.

Aynı istek (aynı model + aynı girdi) ikinci kez ödenmez: sonuç içerik özetine göre `onbellek/`
klasöründe durur. Her çağrı `defter.jsonl` dosyasına yazılır. Bölümün bütçesi aşılacaksa çağrı
yapılmadan durulur. Yarıda kesilen iş yeniden başlatıldığında bitmiş parçalar önbellekten gelir.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone

KOK = os.path.dirname(os.path.abspath(__file__))
ONBELLEK = os.environ.get("ONBELLEK", os.path.join(KOK, "onbellek"))


class ButceAsildi(RuntimeError):
    pass


def ozet(veri: dict) -> str:
    return hashlib.sha256(json.dumps(veri, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:24]


class Kapi:
    def __init__(self, defter_yolu: str, butce_usd: float, onbellek: str | None = None):
        self.defter_yolu, self.butce, self.onbellek = defter_yolu, float(butce_usd), onbellek or ONBELLEK
        os.makedirs(self.onbellek, exist_ok=True)
        os.makedirs(os.path.dirname(os.path.abspath(defter_yolu)), exist_ok=True)

    # ------------------------------------------------------------- defter
    def kayitlar(self) -> list[dict]:
        if not os.path.exists(self.defter_yolu):
            return []
        return [json.loads(s) for s in open(self.defter_yolu, encoding="utf-8") if s.strip()]

    def harcanan(self) -> float:
        return round(sum(k.get("usd", 0.0) for k in self.kayitlar()), 4)

    def _yaz(self, **kayit) -> None:
        kayit["zaman"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with open(self.defter_yolu, "a", encoding="utf-8") as f:
            f.write(json.dumps(kayit, ensure_ascii=False) + "\n")

    # ------------------------------------------------------------ önbellek
    def yol(self, tur: str, girdi: dict, uzanti: str) -> str:
        return os.path.join(self.onbellek, f"{tur}-{ozet(girdi)}.{uzanti}")

    def var_mi(self, tur: str, girdi: dict, uzanti: str) -> bool:
        y = self.yol(tur, girdi, uzanti)
        return os.path.exists(y) and os.path.getsize(y) > 0

    def tahmin(self, istekler: list[tuple[str, dict, str, float]]) -> tuple[float, int, int]:
        """(ödenecek tutar, yeni çağrı sayısı, önbellekten gelecek sayı). Para harcamaz."""
        tekil = list({(i[0], ozet(i[1])): i for i in istekler}.values())    # aynı istek bir kez ödenir
        yeni = [i for i in tekil if not self.var_mi(i[0], i[1], i[2])]
        return round(sum(i[3] for i in yeni), 4), len(yeni), len(tekil) - len(yeni)

    # --------------------------------------------------------------- çağrı
    def cagir(self, tur: str, girdi: dict, uzanti: str, usd: float, uret, deneme: int = 3) -> str:
        """Sonucun dosya yolunu döner. `uret()` bayt döndüren ücretli çağrıdır."""
        y = self.yol(tur, girdi, uzanti)
        if self.var_mi(tur, girdi, uzanti):
            self._yaz(tur=tur, ozet=ozet(girdi), usd=0.0, kaynak="önbellek")
            return y
        if self.harcanan() + usd > self.butce + 1e-9:
            raise ButceAsildi(f"bölüm bütçesi {self.butce:.2f} USD; harcanan {self.harcanan():.2f}, "
                              f"bu çağrı {usd:.3f} USD ({tur})")
        son = None
        for n in range(deneme):
            try:
                veri = uret()
                if not veri:
                    raise RuntimeError("boş cevap")
                gecici = y + ".tmp"
                with open(gecici, "wb") as f:
                    f.write(veri)
                os.replace(gecici, y)                  # yarım dosya önbelleğe girmez
                self._yaz(tur=tur, ozet=ozet(girdi), usd=usd, kaynak="çağrı", deneme=n + 1)
                return y
            except Exception as hata:                  # ağ hatası: bekle, yeniden dene
                son = hata
                if n < deneme - 1:
                    time.sleep(4 * (n + 1))
        self._yaz(tur=tur, ozet=ozet(girdi), usd=0.0, kaynak="hata", hata=str(son)[:300])
        raise RuntimeError(f"{tur} çağrısı {deneme} denemede başarısız: {son}")
