# Kurulum: senin yapacakların

Kod hazır. Hattın gerçek ses, gerçek görsel ve Telegram onayıyla çalışması için aşağıdaki anahtarlar gerekiyor.
Anahtarları sohbete yazma; yalnız GitHub'daki gizli kutulara gir.

Gizli kutuların yeri: **github.com/Yass61/uretim-hatti → Settings → Secrets and variables → Actions → New repository secret**

## 1. Telegram botu (10 dakika) — onay için şart

1. Telegram'da **@BotFather**'a yaz: `/newbot`. Bir ad ve `_bot` ile biten bir kullanıcı adı ver.
2. Verdiği anahtarı `TELEGRAM_BOT_TOKEN` adıyla gizli kutuya gir.
3. Yeni botuna Telegram'dan bir kez "merhaba" yaz (bot sana ancak sen yazdıktan sonra mesaj atabilir).
4. Telegram'da **@userinfobot**'a yaz; verdiği sayıyı (Id) `TELEGRAM_CHAT_ID` adıyla gizli kutuya gir.

## 2. Ses provası — ses seçimi için

1. Denemek istediğin servislerin anahtarını gir. Hepsi şart değil; anahtarı olmayan atlanır.
   - `ELEVENLABS_API_KEY` (10 adaydan 7'si burada)
   - `GOOGLE_TTS_API_KEY` (ayda 1 milyon harf ücretsiz)
   - `AZURE_SPEECH_KEY` ve `AZURE_SPEECH_REGION`
2. **Actions → Kör ses provası → Run workflow**. Sesler Telegram'a yalnız numarayla gelir.
3. Beğendiğin numaraları bana yaz. Seçilen sesi `ayar.json` dosyasına ben işlerim.

## 3. Görsel üretimi

1. fal.ai hesabı aç, 10 USD yükle (yaklaşık 10 bölüme yeter).
2. Anahtarı `FAL_KEY` adıyla gir.

## 4. Kare denetimi (isteğe bağlı ama önerilir)

`GEMINI_API_KEY` adıyla bir Gemini anahtarı gir. Kütüphanedeki anahtarın aynısı olabilir; ama OCR o
anahtarın günlük ücretsiz hakkını bitiriyor. OCR bitene kadar (yaklaşık bir hafta) ayrı bir Google
projesinden ikinci bir anahtar almak daha sağlıklı.

## 5. Telegram'dan tek dokunuşla onay (köprü)

Bu adım olmadan da hat çalışır: video Telegram'a gelir, sen bana "onay" yazarsın. Köprü kurulunca
düğmeye basman yeter. Kurulumu `kopru/KURULUM.md` anlatıyor (Cloudflare'de ücretsiz, 15 dakika).

## Bir bölüm nasıl üretilir?

**Actions → Bölüm üret → Run workflow**
- `tahmin`: ne kadar tutacağını söyler, para harcamaz.
- `senaryo`: senaryoyu denetler, kaynaklarıyla Telegram'a onaya gönderir.
- `uret`: sesi ve görselleri üretir, videoyu kurar, denetler, Telegram'a onaya gönderir.

Bölüm başına bütçe tavanı 1,50 USD'dir (`ayar.json`). Tavan aşılacaksa hat çağrı yapmadan durur.
