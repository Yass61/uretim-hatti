"""Görselden derinlik haritası çıkarır (0 = uzak, 1 = yakın).

Asıl yol: Depth Anything V2 (küçük model, ONNX) — GitHub Actions'ta işlemciyle çalışır.
Model dosyası yoksa ya da onnxruntime kurulu değilse kaba bir tahmine düşer ve bunu söyler.
NOT: ONNX yolu bu ortamda denenemedi (model indirilemiyor); ilk Actions çalışmasında doğrulanacak.
"""
from __future__ import annotations

import os
import sys

import cv2
import numpy as np

MODEL = os.environ.get("DERINLIK_MODELI", "modeller/depth_anything_v2_vits.onnx")


def _onnx(gorsel: np.ndarray) -> np.ndarray:
    import onnxruntime as ort

    oturum = ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    h, w = gorsel.shape[:2]
    kenar = 518
    x = cv2.resize(gorsel, (kenar, kenar), interpolation=cv2.INTER_CUBIC).astype(np.float32) / 255.0
    x = (x - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array([0.229, 0.224, 0.225], dtype=np.float32)
    x = x.transpose(2, 0, 1)[None]
    cikti = oturum.run(None, {oturum.get_inputs()[0].name: x})[0]
    d = np.squeeze(cikti).astype(np.float32)      # model: büyük değer = yakın
    d = cv2.resize(d, (w, h), interpolation=cv2.INTER_CUBIC)
    return (d - d.min()) / max(float(d.max() - d.min()), 1e-6)


def kaba_tahmin(gorsel: np.ndarray) -> np.ndarray:
    """Model yokken: alttaki ve koyu olan yakın sayılır. Yalnız deneme içindir."""
    h, w = gorsel.shape[:2]
    gri = cv2.cvtColor(gorsel, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0
    koyu = 1.0 - cv2.GaussianBlur(gri, (0, 0), 6)
    dikey = np.linspace(0, 1, h, dtype=np.float32)[:, None] ** 1.5
    d = 0.65 * koyu + 0.35 * dikey
    return (d - d.min()) / max(float(d.max() - d.min()), 1e-6)


def derinlik(gorsel: np.ndarray) -> tuple[np.ndarray, str]:
    """(harita, yöntem) döner; yöntem 'model' ya da 'kaba'."""
    if os.path.exists(MODEL):
        try:
            return _onnx(gorsel), "model"
        except Exception as hata:  # model bozuksa üretim durmasın, ama sessiz de kalmasın
            print(f"UYARI: derinlik modeli çalışmadı ({hata}); kaba tahmine geçildi", file=sys.stderr)
    else:
        print(f"UYARI: {MODEL} yok; kaba derinlik tahmini kullanılıyor", file=sys.stderr)
    return kaba_tahmin(gorsel), "kaba"
