# Üretim hattı

Tasavvufi içerik projesinin video üretim kodu. Kaynak metinler ayrı depoda durur:
`Yass61/kaynak-kutuphanesi`. Bu depo yalnız senaryodan videoya giden hattı ve Telegram onayını taşır.

Deneme: `deneme/` klasöründe örnek plan (`bolum.json`) ve hareket denemesi var; görseller ve videolar
depoya konmaz (`.gitignore`).

## Akış

1. Senaryo ve plan listesi (`bolum.json`) yazılır, kaynakla denetlenir. Telegram'da senaryo onayı.
2. Ses üretilir; plan süreleri sesten çıkar.
3. Her plan için durağan görsel üretilir (`gorsel.py`, fal üzerinden).
4. Görselin derinlik haritası çıkarılır (`derinlik.py`) ve kodla hareket verilir (`hareket.py`):
   katmanlı kamera hareketi, ışık hüzmesi, toz, gren. Video modeli kullanılmaz.
5. `kurgu.py` altyazı, ayet kartı ve kaynak rozetini bindirip videoyu kurar.
6. Telegram'da video onayı; onaydan sonra yayın.

Görüntü modeli asla yazı üretmez. Ayet metni ve meal `kuran/kuran.jsonl.gz` dosyasından okunur.

## Dosyalar

| Dosya | Ne yapar | Durum |
| --- | --- | --- |
| `hareket.py` | Görsel + derinlikten hareketli kareler | Denendi (deneme sahnesi) |
| `kurgu.py` | Bölüm dosyasından videoyu kurar | Denendi (yer tutucu görsellerle, sessiz) |
| `derinlik.py` | Derinlik haritası | Kaba tahmin denendi; ONNX model yolu denenmedi |
| `telegram.py` | Onay mesajları ve cevap bekleme | Saf işlevler testli; ağ çağrıları denenmedi |
| `ses_provasi.py` | Kör ses provası | Numaralama testli; motor çağrıları denenmedi |
| `gorsel.py` | fal ile görsel üretimi | Denenmedi; model kimliği doğrulanacak |
| `test_uretim.py` | Anahtar gerektirmeyen sınamalar | Geçiyor |
| `deneme/` | Ebû Talha pilotu: bölüm dosyası ve yer tutucu görseller | |

"Denenmedi" yazan her şey, bu kodun yazıldığı ortamda dış ağa ve anahtarlara erişim olmadığı
içindir. İlk Actions çalışmasında hata çıkması beklenir; hata veren parça diğerlerini durdurmaz.

## Çalıştırma

    pip install -r requirements.txt
    python3 test_uretim.py
    KURAN_VERISI=../kuran/kuran.jsonl.gz python3 kurgu.py deneme/bolum.json cikti.mp4
    KURAN_VERISI=../kuran/kuran.jsonl.gz python3 kurgu.py deneme/bolum.json cikti.mp4 --onizleme 2 20 40

60 saniyelik video iki çekirdekte yaklaşık 5-6 dakikada kurulur.

## Gerekli sırlar (yeni depoda Settings → Secrets and variables → Actions)

| Sır | Ne için | Zorunlu mu |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | BotFather'dan alınan bot anahtarı | Evet |
| `TELEGRAM_CHAT_ID` | Yalnız bu sohbetten gelen onay kabul edilir | Evet |
| `ELEVENLABS_API_KEY` | Ses provasındaki 7 aday | Prova için önerilir |
| `GOOGLE_TTS_API_KEY` | Chirp 3 HD sesleri | İsteğe bağlı |
| `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION` | Azure sesi | İsteğe bağlı |
| `FAL_KEY` | Görsel üretimi | Üçüncü pilot için |

Anahtarı olmayan motor provada atlanır.

## Açık konular

- Derinlik modeli dosyası (`modeller/depth_anything_v2_vits.onnx`) Actions'ta indirilecek; adım henüz yazılmadı.
- Onay bekleme: iş akışı Telegram'ı yoklayarak bekler ve beklerken Actions dakikası harcar.
  Kalıcı çözüm, Telegram'dan gelen cevabı GitHub'a ileten küçük bir ara servistir (ör. Cloudflare Worker).
- Ses ile tilavetin karıştırılması, ses zaman damgalarından `bolum.json` üretimi ve görme modeliyle
  kare denetimi henüz yazılmadı.
- Fish Audio ve Gemini TTS provaya eklenmedi.
- Keskin kenarlı siluetlerde hareket sırasında kenar bozulması görülebilir; gerçek görsellerde yeniden bakılacak.
