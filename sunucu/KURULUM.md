# Zâviye sunucu botu

Telegram onay düğmelerini GitHub'a iletir, haftalık üretimi başlatır, üretim başlamaz ya da hata verirse tek mesajla haber verir.
Webhook yok, port açılmaz. Yalnız Python standart kütüphanesi kullanılır. Claude kullanılmaz.

Ayrı kullanıcı (`zaviye`), ayrı klasör (`/opt/zaviye`, `/var/lib/zaviye`), gizli değerler `/etc/zaviye/ortam` (0600, root).
Servis `nice 15` ve en çok 150 MB bellekle çalışır. Diğer servislere ve tmux oturumlarına dokunmaz.

    cd /tmp && rm -rf zaviye-kurulum && mkdir zaviye-kurulum && cd zaviye-kurulum
    curl -fsSLO https://raw.githubusercontent.com/Yass61/uretim-hatti/main/sunucu/zaviye_bot.py
    curl -fsSLO https://raw.githubusercontent.com/Yass61/uretim-hatti/main/sunucu/kurulum.sh
    sudo bash kurulum.sh
    sudo nano /etc/zaviye/ortam
    sudo systemctl enable --now zaviye-bot && sudo journalctl -u zaviye-bot -n 20

Program: sunucuda `/etc/zaviye/program.json` boşsa depodaki `sunucu/program.json` okunur; takvim değişikliği için sunucuya girmek gerekmez.

Güncelleme: ilk iki `curl` satırı ve `sudo bash kurulum.sh` yeniden çalıştırılır, ardından `sudo systemctl restart zaviye-bot`.
Durdurma: `sudo systemctl disable --now zaviye-bot`.
