#!/bin/bash
# Zâviye botu kurulumu. Yalnız kendi kullanıcısı, kendi klasörü ve kendi servisini oluşturur.
# Kara Sicil ve MarketMind klasörlerine, kullanıcılarına ve tmux oturumuna dokunmaz.
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "root olarak çalıştır"; exit 1; }
lsb_release -a 2>/dev/null || true
id zaviye >/dev/null 2>&1 || useradd --system --home /opt/zaviye --shell /usr/sbin/nologin zaviye
install -d -o zaviye -g zaviye /opt/zaviye /var/lib/zaviye
install -d -m 0750 -o root -g zaviye /etc/zaviye
install -m 0644 -o zaviye -g zaviye "$(dirname "$0")/zaviye_bot.py" /opt/zaviye/zaviye_bot.py
[ -f /etc/zaviye/program.json ] || echo '[]' > /etc/zaviye/program.json
[ -f /etc/zaviye/ortam ] || {
  printf 'TELEGRAM_BOT_TOKEN=\nTELEGRAM_CHAT_ID=\nGITHUB_TOKEN=\nGITHUB_DEPO=Yass61/uretim-hatti\n' > /etc/zaviye/ortam
  echo ">>> /etc/zaviye/ortam dosyasını doldur: nano /etc/zaviye/ortam"
}
# ortam: yalnız root okur (systemd servisi başlatırken root olarak okuyup aktarır).
chown root:root /etc/zaviye/ortam; chmod 0600 /etc/zaviye/ortam
# program: botun kendisi okur.
chown root:zaviye /etc/zaviye/program.json; chmod 0640 /etc/zaviye/program.json
cat > /etc/systemd/system/zaviye-bot.service <<'S'
[Unit]
Description=Zaviye Telegram botu
After=network-online.target
Wants=network-online.target

[Service]
User=zaviye
Group=zaviye
EnvironmentFile=/etc/zaviye/ortam
Environment=TZ=Europe/Istanbul
ExecStart=/usr/bin/python3 /opt/zaviye/zaviye_bot.py
Restart=always
RestartSec=10
Nice=15
MemoryMax=150M
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=/var/lib/zaviye

[Install]
WantedBy=multi-user.target
S
systemctl daemon-reload
echo "Kuruldu. Ortam dosyasını doldurduktan sonra: systemctl enable --now zaviye-bot && journalctl -u zaviye-bot -n 20"
