#!/bin/bash
# Configuration WiFi du Raspberry Pi
# Usage : sudo ./config/wifi_setup.sh "SSID" "MOT_DE_PASSE"

set -e

SSID="$1"
PASS="$2"

if [ -z "$SSID" ] || [ -z "$PASS" ]; then
    echo "Usage : sudo $0 \"SSID\" \"MOT_DE_PASSE\""
    exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
    echo "Ce script doit etre lance avec sudo."
    exit 1
fi

cat > /etc/wpa_supplicant/wpa_supplicant.conf <<EOF
country=TN
ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev
update_config=1

network={
    ssid="$SSID"
    psk="$PASS"
    key_mgmt=WPA-PSK
}
EOF

chmod 600 /etc/wpa_supplicant/wpa_supplicant.conf
wpa_cli -i wlan0 reconfigure || true
echo "WiFi configure pour le reseau : $SSID"
