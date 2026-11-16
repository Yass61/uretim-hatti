"""Hareket motorunu, katmanları bilinen bir deneme sahnesiyle sınar (derinlik modeli gerekmez)."""
import subprocess, sys, time
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
sys.path.insert(0, "/home/claude/pilot-video")
import scenes as S
from hareket import Hareket, Ayar

W, H = S.W, S.H

def sahne():
    img = S.vgrad([(0, S.SKY_TOP), (0.30, S.SKY_MID), (0.55, S.SKY_BOT), (0.7, S.MID), (1, S.GROUND)])
    img = S.with_glow(img, (760, 760), 520, (255, 212, 148), 0.9)
    dep = Image.new("RGB", (W, H), (0, 0, 0))
    d, dd = ImageDraw.Draw(img), ImageDraw.Draw(dep)
    g = lambda v: (int(v * 255),) * 3
    S.hills(d, 1240, 20, S.FAR, 4); S.hills(dd, 1240, 20, g(0.18), 4)
    img = img.filter(ImageFilter.GaussianBlur(3)); d = ImageDraw.Draw(img)
    for i, (x, hgt, lean) in enumerate([(210, 760, 30), (470, 860, -40), (880, 800, 50), (700, 680, -20)]):
        S.palm(d, x, 1380 + (i % 2) * 40, hgt, lean, S.MID, seed=20 + i)
        S.palm(dd, x, 1380 + (i % 2) * 40, hgt, lean, g(0.5), seed=20 + i)
    S.hills(d, 1480, 14, S.NEAR, 5); S.hills(dd, 1480, 14, g(0.75), 5)
    S.palm(d, 330, 1620, 1240, 120, S.NEAR, seed=31); S.palm(dd, 330, 1620, 1240, 120, g(1.0), seed=31)
    S.palm(d, 990, 1640, 1150, -150, S.NEAR, seed=32); S.palm(dd, 990, 1640, 1150, -150, g(0.95), seed=32)
    return np.asarray(img), np.asarray(dep)[..., 0].astype(np.float32) / 255

def main():
    gorsel, derinlik = sahne()
    cikti = sys.argv[1]
    planlar = [("yaklas", 4.0), ("saga", 4.0), ("yuksel", 4.0)]
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", "30",
           "-i", "-", "-c:v", "libx264", "-crf", "18", "-preset", "veryfast", "-pix_fmt", "yuv420p", cikti]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    t0 = time.time(); n = 0
    for ad, sure in planlar:
        h = Hareket(gorsel, derinlik, Ayar(hareket=ad, hüzme=0.22, isik_x=0.70, isik_y=0.40))
        for k in h.kareler(sure):
            p.stdin.write(k.tobytes()); n += 1
    p.stdin.close(); assert p.wait() == 0
    print("kare", n, "sn/kare %.3f" % ((time.time() - t0) / n))

main()
