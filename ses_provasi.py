"""Kör ses provası: aynı metni farklı motor ve seslerle üretir, Telegram'a yalnız numarayla yollar.

Kullanım:  python3 ses_provasi.py ses_adaylari.json cikti_klasoru [--gonderme]
Hangi numaranın hangi ses olduğu cikti_klasoru/anahtar.json dosyasında kalır; Telegram'a gitmez.
Anahtarı olmayan motor atlanır ve raporda belirtilir.
NOT: Ağ çağrıları bu ortamda denenemedi. Model ve ses kimlikleri ses_adaylari.json'dan gelir;
     ilk çalışmada hata veren kimlik rapora yazılır, diğerleri etkilenmez.
"""
from __future__ import annotations

import base64
import json
import os
import random
import sys


def elevenlabs(metin: str, aday: dict) -> bytes:
    import requests

    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{aday['ses']}",
        headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]},
        params={"output_format": "mp3_44100_128"},
        json={k: v for k, v in {
            "text": metin, "model_id": aday.get("model") or "eleven_multilingual_v2", "language_code": "tr",
            "previous_text": aday.get("onceki") or None, "next_text": aday.get("sonraki") or None,
            "voice_settings": {"stability": 0.6, "similarity_boost": 0.75, "style": 0.15,
                               "speed": aday.get("hiz") or 0.92}}.items() if v is not None},
        timeout=180)
    if r.status_code == 400 and "language_code" in r.text:     # eski modeller dil kodunu kabul etmez
        r = requests.post(r.request.url, headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"]},
                          json={"text": metin, "model_id": aday.get("model") or "eleven_multilingual_v2"}, timeout=180)
    r.raise_for_status()
    return r.content


def google(metin: str, aday: dict) -> bytes:
    import requests

    r = requests.post(
        "https://texttospeech.googleapis.com/v1/text:synthesize",
        params={"key": os.environ["GOOGLE_TTS_API_KEY"]},
        json={"input": {"text": metin}, "voice": {"languageCode": "tr-TR", "name": aday["ses"]},
              "audioConfig": {"audioEncoding": "MP3", "speakingRate": aday.get("hiz", 0.92)}},
        timeout=180)
    r.raise_for_status()
    return base64.b64decode(r.json()["audioContent"])

STIL_VARSAYILAN = ("Aşağıdaki metni Türkçe, ağırbaşlı ve sıcak bir sesle, bir hikâye anlatıcısı gibi oku. "
                   "Acele etme; virgüllerde kısa, noktalarda belirgin dur. Önemli kelimeleri hafifçe vurgula, "
                   "duygulu ama abartısız ol. Arapça kökenli adları ve terimleri doğru telaffuz et.")


def gemini(metin: str, aday: dict) -> bytes:
    """Gemini TTS: üslup doğal dille verilir. Çıktı 24 kHz PCM; ffmpeg ile mp3'e çevrilir."""
    import subprocess
    import tempfile

    import requests

    anahtar = os.environ.get("GEMINI_GORSEL_API_KEY") or os.environ["GEMINI_API_KEY"]
    model = aday.get("model") or "gemini-3.1-flash-tts-preview"
    istem = f"{aday.get('stil') or STIL_VARSAYILAN}\n\n{metin}"
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        params={"key": anahtar},
        json={"contents": [{"parts": [{"text": istem}]}],
              "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {
                  "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": aday["ses"]}}}}},
        timeout=300)
    if r.status_code >= 400:
        raise RuntimeError(f"{r.status_code} {r.text[:300]}")
    pcm = base64.b64decode(r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "a.pcm"), "wb").write(pcm)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", "24000", "-ac", "1",
                        "-i", os.path.join(d, "a.pcm"), "-b:a", "128k", os.path.join(d, "a.mp3")], check=True)
        return open(os.path.join(d, "a.mp3"), "rb").read()


def azure(metin: str, aday: dict) -> bytes:
    import requests
    from xml.sax.saxutils import escape

    ssml = (f"<speak version='1.0' xml:lang='tr-TR' xmlns:mstts='https://www.w3.org/2001/mstts'>"
            f"<voice name='{aday['ses']}'><prosody rate='-8%'>{escape(metin)}</prosody></voice></speak>")
    r = requests.post(
        f"https://{os.environ['AZURE_SPEECH_REGION']}.tts.speech.microsoft.com/cognitiveservices/v1",
        headers={"Ocp-Apim-Subscription-Key": os.environ["AZURE_SPEECH_KEY"],
                 "Content-Type": "application/ssml+xml",
                 "X-Microsoft-OutputFormat": "audio-24khz-96kbitrate-mono-mp3"},
        data=ssml.encode("utf-8"), timeout=180)
    r.raise_for_status()
    return r.content


MOTORLAR = {
    "elevenlabs": (elevenlabs, ["ELEVENLABS_API_KEY"]),
    "google": (google, ["GOOGLE_TTS_API_KEY"]),
    "azure": (azure, ["AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION"]),
    "gemini": (gemini, ["GEMINI_GORSEL_API_KEY"]),
}


def numarala(adaylar: list[dict], tohum: int) -> list[tuple[int, dict]]:
    """Adayları karıştırıp 1'den numaralar; aynı tohum aynı sırayı verir."""
    sira = list(adaylar)
    random.Random(tohum).shuffle(sira)
    return list(enumerate(sira, start=1))


def main() -> None:
    ayar = json.load(open(sys.argv[1], encoding="utf-8"))
    cikti = sys.argv[2]
    os.makedirs(cikti, exist_ok=True)
    gonder = "--gonderme" not in sys.argv
    anahtar, rapor = {}, []
    for no, aday in numarala(ayar["adaylar"], ayar.get("tohum", 2026)):
        islev, sirlar = MOTORLAR[aday["motor"]]
        eksik = [s for s in sirlar if not os.environ.get(s)]
        if eksik:
            rapor.append(f"{no}: atlandı ({aday['motor']} anahtarı yok)")
            continue
        try:
            veri = islev(ayar["metin"], aday)
        except Exception as hata:                      # bir aday düşerse prova durmaz
            rapor.append(f"{no}: hata ({aday['motor']} {aday['ses']}): {hata}")
            continue
        yol = os.path.join(cikti, f"ses_{no:02d}.mp3")
        open(yol, "wb").write(veri)
        anahtar[no] = aday
        rapor.append(f"{no}: üretildi")
        if gonder:
            import telegram
            telegram.ses(yol, f"Ses {no}")
    json.dump(anahtar, open(os.path.join(cikti, "anahtar.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("\n".join(rapor))
    if gonder and anahtar:
        import telegram
        telegram.mesaj(f"Ses provası: {len(anahtar)} kayıt gönderildi. Beğendiklerinin numarasını yaz (örnek: 3, 7).")
    if not anahtar:
        raise SystemExit("hiç ses üretilemedi")


if __name__ == "__main__":
    main()
