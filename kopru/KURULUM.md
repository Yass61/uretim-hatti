# Köprü kurulumu (Telegram düğmesi → GitHub)

Amaç: Telegram'daki **Onayla** düğmesine bastığında üretimin kendiliğinden başlaması.
Cloudflare'in ücretsiz katmanı yeter; kart bilgisi istemez.

1. **GitHub anahtarı:** github.com/settings/personal-access-tokens → *Generate new token* (fine-grained).
   - Repository access: *Only select repositories* → `uretim-hatti`
   - Permissions → Repository → **Contents: Read and write**
   - Anahtarı kopyala (bir kez gösterilir).
2. **Cloudflare:** dash.cloudflare.com'da ücretsiz hesap aç → *Workers & Pages* → *Create* → *Worker* →
   ad: `uretim-kopru` → *Deploy* → *Edit code*. Editördeki her şeyi sil, bu klasördeki `worker.js`
   dosyasının içeriğini yapıştır, *Deploy*.
3. **Gizli değerler:** Worker → *Settings* → *Variables and Secrets* → her biri için *Add* (tür: Secret):
   - `WEBHOOK_SIRRI`: kendi uyduracağın uzun bir parola (yalnız harf ve rakam)
   - `TELEGRAM_TOKEN`: bot anahtarı
   - `CHAT_ID`: Telegram Id numaran
   - `GITHUB_TOKEN`: 1. adımdaki anahtar
   - `GITHUB_DEPO`: `Yass61/uretim-hatti`
4. **Telegram'a adresi tanıt:** tarayıcıda şu adresi aç (köşeli yerleri doldur):

       https://api.telegram.org/bot[BOT_ANAHTARI]/setWebhook?url=[WORKER_ADRESI]&secret_token=[WEBHOOK_SIRRI]&allowed_updates=["callback_query","message"]

   `{"ok":true}` görmelisin. Worker adresi, Worker sayfasının üstünde `https://uretim-kopru.….workers.dev` biçiminde yazar.

Güvenlik: köprü yalnız senin sohbetinden gelen ve parolayı taşıyan istekleri kabul eder; GitHub anahtarı
yalnız bu depoya yetkilidir.
