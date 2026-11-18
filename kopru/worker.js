// Telegram → GitHub köprüsü (Cloudflare Worker, ücretsiz katman).
// Telegram'daki onay düğmesine basılınca bu küçük servis GitHub'daki "Bölüm üret" iş akışını başlatır.
// Böylece iş akışı cevabı beklerken boşuna çalışmaz; onay saniyeler içinde işlenir.
//
// Gerekli gizli değerler (Worker → Settings → Variables and Secrets):
//   WEBHOOK_SIRRI   : kendi uydurduğun uzun bir parola; Telegram her istekte bunu gönderir
//   TELEGRAM_TOKEN  : bot anahtarı (düğmedeki bekleme işaretini kapatmak ve cevap yazmak için)
//   CHAT_ID         : yalnız bu sohbetten gelen karar kabul edilir
//   GITHUB_TOKEN    : yalnız uretim-hatti deposuna yetkili ince ayarlı anahtar (Contents: Read and write)
//   GITHUB_DEPO     : "Yass61/uretim-hatti"

const KIMLIK = /^[sv]:[a-z0-9][a-z0-9-]{0,60}$/;

async function telegram(env, yontem, govde) {
  return fetch(`https://api.telegram.org/bot${env.TELEGRAM_TOKEN}/${yontem}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(govde),
  });
}

async function githubaIlet(env, yuk) {
  const r = await fetch(`https://api.github.com/repos/${env.GITHUB_DEPO}/dispatches`, {
    method: "POST",
    headers: {
      authorization: `Bearer ${env.GITHUB_TOKEN}`,
      accept: "application/vnd.github+json",
      "user-agent": "uretim-hatti-kopru",
    },
    body: JSON.stringify({ event_type: "telegram-onay", client_payload: yuk }),
  });
  return r.status === 204;
}

export default {
  async fetch(istek, env) {
    if (istek.method !== "POST") return new Response("ok");
    if (istek.headers.get("x-telegram-bot-api-secret-token") !== env.WEBHOOK_SIRRI) {
      return new Response("yetkisiz", { status: 401 });
    }
    const g = await istek.json().catch(() => null);
    if (!g) return new Response("ok");

    // 1) Düğme: onay ya da ret hemen iletilir; "düzeltme yazacağım" ise not beklenir.
    const cq = g.callback_query;
    if (cq) {
      const sohbet = String(cq.message?.chat?.id ?? "");
      const [kimlik, karar] = String(cq.data ?? "").split("|");
      if (sohbet !== String(env.CHAT_ID) || !KIMLIK.test(kimlik) || !["onay", "red", "not"].includes(karar)) {
        return new Response("ok");
      }
      if (karar === "not") {
        await telegram(env, "answerCallbackQuery", { callback_query_id: cq.id });
        // Cevabın hangi bölüme ait olduğu, bu mesaja verilen yanıttan anlaşılır.
        await telegram(env, "sendMessage", {
          chat_id: sohbet,
          text: `Düzeltme notunu bu mesajı yanıtlayarak yaz.\n#${kimlik}`,
          reply_markup: { force_reply: true },
        });
        return new Response("ok");
      }
      const tamam = await githubaIlet(env, { kimlik, karar, not: "" });
      await telegram(env, "answerCallbackQuery", {
        callback_query_id: cq.id,
        text: tamam ? "Karar alındı." : "GitHub'a iletilemedi; biraz sonra yeniden dene.",
        show_alert: !tamam,
      });
      return new Response("ok");
    }

    // 2) Not: "Düzeltme notunu … yaz. #s:bolum" mesajına verilen yanıt.
    const m = g.message;
    const asil = m?.reply_to_message?.text ?? "";
    const es = asil.match(/#([sv]:[a-z0-9-]+)\s*$/);
    if (m?.text && es && String(m.chat?.id) === String(env.CHAT_ID) && KIMLIK.test(es[1])) {
      const tamam = await githubaIlet(env, { kimlik: es[1], karar: "not", not: m.text.slice(0, 2000) });
      if (!tamam) await telegram(env, "sendMessage", { chat_id: m.chat.id, text: "Not GitHub'a iletilemedi." });
    }
    return new Response("ok");
  },
};
