"""Durağan kareye kodla hareket verir: derinlik haritasına göre katmanlı kamera
hareketi (2.5D), ışık hüzmesi, havada asılı toz ve film greni.

Girdi : RGB görsel (H, W, 3 uint8) ve derinlik haritası (H, W float, 0 = uzak, 1 = yakın)
Çıktı : kare üreten bir üreteç; ffmpeg'e ham video olarak verilir.

Video modeli kullanılmaz; her şey numpy ve OpenCV ile hesaplanır.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

# Kamera hareketi hazır ayarları: (yatay kayma, dikey kayma, yakınlaşma) birim genlikte
HAREKETLER = {
    "yaklas": (0.0, 0.0, 1.0),        # yavaş içeri süzülme
    "uzaklas": (0.0, 0.0, -1.0),
    "sola": (-1.0, 0.0, 0.35),
    "saga": (1.0, 0.0, 0.35),
    "yuksel": (0.0, -1.0, 0.35),
    "alcal": (0.0, 1.0, 0.35),
    "capraz": (0.7, -0.5, 0.6),
}


@dataclass
class Ayar:
    hareket: str = "yaklas"
    genlik: float = 1.0          # 1.0 = sakin; 1.5 üstü belirgin
    kayma_px: float = 46.0       # en yakın katmanın toplam kayması (1080 genişlikte)
    yakinlasma: float = 0.075    # toplam yakınlaşma oranı
    derinlik_farki: float = 0.55 # yakın katman uzak katmana göre ne kadar fazla hareket eder
    toz: int = 70                # toz zerresi sayısı (0 = kapalı)
    hüzme: float = 0.0           # ışık hüzmesi şiddeti (0 = kapalı, 0.25 iyi)
    isik_x: float = 0.75         # ışık kaynağı (ekran oranı)
    isik_y: float = 0.25
    gren: float = 1.4
    tohum: int = 7


def yumusat(t: float) -> float:
    """Başta ve sonda yavaşlayan geçiş (hareket hiç 'başlamış' gibi görünmez)."""
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def derinlik_hazirla(derinlik: np.ndarray, boyut: tuple[int, int]) -> np.ndarray:
    """Derinliği 0-1 aralığına çeker, kenar yırtılmasını önlemek için yumuşatır."""
    d = derinlik.astype(np.float32)
    lo, hi = np.percentile(d, 1), np.percentile(d, 99)
    d = np.clip((d - lo) / max(hi - lo, 1e-6), 0, 1)
    d = cv2.resize(d, boyut, interpolation=cv2.INTER_LINEAR)
    # Kenarı koruyan yumuşatma: katman içi düz, katman sınırı yumuşak
    d = cv2.GaussianBlur(d, (0, 0), 7.0 * boyut[0] / 1080.0)
    return d


class Hareket:
    def __init__(self, gorsel: np.ndarray, derinlik: np.ndarray, ayar: Ayar | None = None):
        self.a = ayar or Ayar()
        self.h, self.w = gorsel.shape[:2]
        self.gorsel = gorsel
        self.d = derinlik_hazirla(derinlik, (self.w, self.h))
        self.olcek = self.w / 1080.0
        yy, xx = np.mgrid[0:self.h, 0:self.w].astype(np.float32)
        self.xx, self.yy = xx, yy
        self.cx, self.cy = self.w / 2.0, self.h * 0.47
        r = np.random.default_rng(self.a.tohum)
        n = self.a.toz
        # toz: konum (0-1), derinlik, boyut, parlaklık, sürüklenme, titreşim fazı
        self.toz = {
            "x": r.random(n), "y": r.random(n), "z": r.random(n) ** 0.7,
            "r": r.uniform(1.2, 3.4, n), "p": r.uniform(0.25, 0.9, n),
            "vx": r.uniform(-0.012, 0.012, n), "vy": r.uniform(-0.02, -0.004, n),
            "faz": r.uniform(0, 6.28, n), "hiz": r.uniform(0.6, 1.8, n),
        }
        self.gren_r = np.random.default_rng(self.a.tohum + 1)
        self._huzme = self._huzme_hazirla() if self.a.hüzme > 0 else None
        self._vinyet = self._vinyet_hazirla()

    # ------------------------------------------------------------ katmanlar
    def _vinyet_hazirla(self) -> np.ndarray:
        r = np.sqrt(((self.xx - self.w / 2) / (self.w / 2)) ** 2 + ((self.yy - self.h / 2) / (self.h / 2)) ** 2)
        return (1 - 0.42 * np.clip(r - 0.45, 0, 1) ** 1.6).astype(np.float32)[..., None]

    def _huzme_hazirla(self) -> np.ndarray:
        """Işık kaynağından yayılan yumuşak hüzmeler; çeyrek çözünürlükte hesaplanır."""
        k = 4
        hh, ww = self.h // k, self.w // k
        yy, xx = np.mgrid[0:hh, 0:ww].astype(np.float32)
        lx, ly = self.a.isik_x * ww, self.a.isik_y * hh
        self._huzme_ang = np.arctan2(yy - ly, xx - lx)
        uz = np.sqrt((xx - lx) ** 2 + (yy - ly) ** 2) / hh
        return np.exp(-uz * 1.3).astype(np.float32)

    def _huzme_kare(self, t_sn: float) -> np.ndarray:
        ang = self._huzme_ang
        # geniş, düşük kontrastlı ve çok yavaş dönen şeritler: yıldız patlaması gibi değil, pus gibi
        s = 0.5 + 0.5 * np.sin(ang * 7 + t_sn * 0.08)
        s2 = 0.5 + 0.5 * np.sin(ang * 13 - t_sn * 0.05 + 1.3)
        desen = 0.45 + 0.35 * s ** 2 + 0.20 * s2 ** 2
        nefes = 0.88 + 0.12 * math.sin(t_sn * 0.5)
        kucuk = (desen * self._huzme * self.a.hüzme * nefes).astype(np.float32)
        kucuk = cv2.GaussianBlur(kucuk, (0, 0), 6)
        return cv2.resize(kucuk, (self.w, self.h), interpolation=cv2.INTER_LINEAR)

    def _toz_ciz(self, kare: np.ndarray, t_sn: float, ox: float, oy: float) -> None:
        z = self.toz
        for i in range(len(z["x"])):
            # derinliği büyük (yakın) zerre kamera ile daha çok kayar
            px = ((z["x"][i] + z["vx"][i] * t_sn) % 1.0) * self.w - ox * (0.4 + z["z"][i]) * 1.4
            py = ((z["y"][i] + z["vy"][i] * t_sn) % 1.0) * self.h - oy * (0.4 + z["z"][i]) * 1.4
            yar = z["r"][i] * (0.6 + z["z"][i]) * self.olcek
            par = z["p"][i] * (0.55 + 0.45 * math.sin(z["faz"][i] + t_sn * z["hiz"][i]))
            k = int(yar * 3) + 1
            x0, y0 = int(px) - k, int(py) - k
            x1, y1 = x0 + 2 * k + 1, y0 + 2 * k + 1
            if x0 < 0 or y0 < 0 or x1 > self.w or y1 > self.h:
                continue
            gy, gx = np.mgrid[-k:k + 1, -k:k + 1].astype(np.float32)
            leke = np.exp(-(gx ** 2 + gy ** 2) / (2 * yar ** 2)) * par * 70
            kare[y0:y1, x0:x1] += leke[..., None] * np.array([1.0, 0.9, 0.72], dtype=np.float32)

    # ---------------------------------------------------------------- kare
    def kare(self, oran: float, t_sn: float) -> np.ndarray:
        """oran: planın 0-1 ilerlemesi; t_sn: planın başından beri geçen saniye."""
        a = self.a
        hx, hy, hz = HAREKETLER[a.hareket]
        e = yumusat(oran) - 0.5                      # -0.5 .. 0.5: hareket ortalanır
        ox = hx * a.kayma_px * self.olcek * a.genlik * e
        oy = hy * a.kayma_px * self.olcek * a.genlik * e
        p = yumusat(oran)
        zt = abs(hz) * a.yakinlasma * a.genlik * (p if hz >= 0 else 1 - p)
        # kenarlar görünmesin diye küçük bir taban büyütme
        taban = 1.0 + (a.kayma_px * self.olcek * a.genlik) / self.w * 1.6 + abs(hz) * a.yakinlasma * a.genlik * 0.15
        d = self.d
        # yakın katman hem daha çok kayar hem daha çok büyür (dolly etkisi)
        agir = (1 - a.derinlik_farki) + a.derinlik_farki * d
        zoom = taban + zt * (0.55 + 0.9 * d)
        mx = self.cx + (self.xx - self.cx) / zoom + ox * agir
        my = self.cy + (self.yy - self.cy) / zoom + oy * agir
        # bir düzeltme turu: kayma, hedefteki değil kaynaktaki derinliğe göre olmalı
        d2 = cv2.remap(d, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
        agir2 = (1 - a.derinlik_farki) + a.derinlik_farki * d2
        zoom2 = taban + zt * (0.55 + 0.9 * d2)
        mx = self.cx + (self.xx - self.cx) / zoom2 + ox * agir2
        my = self.cy + (self.yy - self.cy) / zoom2 + oy * agir2
        kare = cv2.remap(self.gorsel, mx, my, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT).astype(np.float32)
        if self._huzme is not None:
            hk = self._huzme_kare(t_sn)
            # hüzme yakın (koyu) nesnelerin arkasında kalır
            hk = hk * (1 - 0.75 * d2)
            kare += hk[..., None] * np.array([255, 226, 170], dtype=np.float32)
        if a.toz:
            self._toz_ciz(kare, t_sn, ox, oy)
        kare *= self._vinyet
        if a.gren:
            kare += self.gren_r.normal(0, a.gren, (self.h, self.w, 1)).astype(np.float32)
        return np.clip(kare, 0, 255).astype(np.uint8)

    def kareler(self, sure: float, fps: int = 30):
        n = max(int(round(sure * fps)), 1)
        for i in range(n):
            yield self.kare(i / max(n - 1, 1), i / fps)
