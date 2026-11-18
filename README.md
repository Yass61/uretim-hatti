# Üretim hattı

Tasavvufi kısa video projesinin üretim kodu: bir bölüm dosyasından Telegram'daki onaya kadar.
Kaynak metinler ayrı depoda durur (`Yass61/kaynak-kutuphanesi`). Senin yapacakların: [KURULUM.md](KURULUM.md).

## Akış

    bolum.json ─► denetim ─► ses ─► görsel ─► kurgu ─► kalite denetimi ─► Telegram onayı
                  (bolum.py) (ses.py) (gorsel.py) (kurgu.py)  (denetim.py)      (telegram.py)

1. **Senaryo** (`bolumler/<ad>/bolum.json`): cümleler, her cümlenin kaynağı, planlar ve görsel istemleri.
2. **Denetim:** kaynağı olmayan cümle, kırık plan ya da kırmızı çizgi varsa üretim başlamaz, para harcanmaz.
3. **Ses:** her cümle ayrı üretilir, süreler ölçülür. Motora metnin okunuşu gider (`okunus.py`), altyazı değişmez.
4. **Görsel:** her plan için iki aday üretilir, denetlenir, iyisi seçilir. Görüntü modeli yazı üretmez.
5. **Kurgu:** görsele kodla derinlikli kamera hareketi, ışık ve toz verilir; altyazı, ayet kartı ve kaynak rozeti bindirilir.
6. **Kalite denetimi:** yazı sığıyor mu, ses düzeyi doğru mu, karelerde yüz, uydurma yazı ya da dönem dışı nesne var mı.
7. **Telegram:** video denetim raporuyla gelir; onay, ret ya da düzeltme notu.

Bütün ücretli çağrılar tek kapıdan geçer (`kapi.py`): aynı istek ikinci kez ödenmez, bölüm bütçesi
aşılmaz, her harcama deftere yazılır. Yarıda kesilen iş yeniden çalıştırılınca kaldığı yerden sürer.

## Çalıştırma

    pip install -r requirements.txt
    python3 test_uretim.py
    python3 hat.py bolumler/ebu-talha/bolum.json --tahmin              # maliyet; para harcamaz
    python3 hat.py bolumler/ebu-talha/bolum.json --gonderme            # üret, Telegram'a gönderme

Anahtarı olmayan adım atlanır ve raporda söylenir. Hiç anahtar yokken pilot bölüm yer tutucu görsellerle
ve sessiz kurulur; iki çekirdekte 74 saniyelik video yaklaşık 5,5 dakika sürer.

## Dosyalar

| Dosya | Ne yapar | Durum |
| --- | --- | --- |
| `hat.py` | Adımları sırayla çalıştırır, durumu ve harcamayı yazar | Uçtan uca denendi (anahtarsız) |
| `bolum.py` | Senaryo denetimi: kaynak, plan, kırmızı çizgi, süre | Testli |
| `okunus.py` | Türkçe okunuş: sayılar, tarihler, Hz., s.a.v., r.a. | Testli |
| `kapi.py` | Önbellek, bütçe tavanı, harcama defteri, yeniden deneme | Testli |
| `ses.py` | Cümle cümle anlatım, ölçülmüş zamanlar, tilavet yerleştirme | Sahte motorla testli; gerçek motor denenmedi |
| `gorsel.py` | fal (Recraft V4) ile aday görseller | Sahte çağrıyla testli; gerçek çağrı denenmedi |
| `derinlik.py` | Derinlik haritası (Depth Anything V2) | Kaba tahmin denendi; model Actions'ta indirilir |
| `hareket.py` | Görsel + derinlikten hareketli kareler | Denendi |
| `kurgu.py` | Videoyu kurar: altyazı, ayet kartı, rozet, geçişler, ses düzeyi | Denendi |
| `denetim.py` | Ölçümler ve görme modeliyle kare denetimi | Ölçümler denendi; görme çağrısı denenmedi |
| `telegram.py`, `onay.py` | Onay mesajları ve gelen kararın işlenmesi | Saf işlevler testli; ağ denenmedi |
| `kopru/` | Telegram düğmesini GitHub'a bağlayan küçük servis | Yazıldı; senin kurman gerekiyor |
| `ses_provasi.py` | Kör ses provası (10 aday) | Motor çağrıları denenmedi |

"Denenmedi" yazan her şey anahtar gerektirdiği içindir; ilk gerçek çalışmada hata çıkabilir.
Hata veren adım diğerlerini bozmaz ve Telegram'a ne olduğunu yazar.

## Kırmızı çizgiler (kodda zorunlu)

- Kaynağı olmayan cümle üretime girmez. Kaynaksız olabilenler yalnız `kanca`, `köprü`, `tefekkür`.
- Ayet metni ve meal dosyadan okunur (`kuran/`), elle yazılmaz.
- Görsellerde yüz, önden figür, hale, uydurma yazı, kubbe, minare ve modern nesne istenmez; denetimde aranır.
- “Bursevî der ki” denmez, “Rûhu'l-Beyân'da şöyle geçer” denir. Fetva ve mezhep dili uyarı verir.

## Açık konular

- Ses seçimi (kör prova bekliyor), tilavet kaydı ve lisansı, müzik kararı.
- Düzeltme notundan sonra senaryonun yeniden yazılması şimdilik elle (Claude oturumunda) yapılır.
- Yayın adımı (Instagram, YouTube, TikTok'a gönderim) henüz yok; onaylanan video hazır bekler.
- Görseller yaklaşık 768×1344 gelir ve 1080×1920'ye büyütülür; gerekirse büyütme modeli eklenecek.
- Kod çizimli sahne araçları (HyperFrames, OpenFilm) ile karşılaştırma yapılmadı.

Teşekkür: Türkçe okuma kuralları ve kare denetim listesi fikri AI Video Factory'den (MIT, Ersin Koç) esinlenmiştir.
