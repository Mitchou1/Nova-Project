#!/bin/bash
# Script de configuration WiFi
# Usage: sudo ./wifi_setup.sh "SSID" "PASSWORD"

SSID=$1
PASS=$2

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

wpa_cli -i wlan0 reconfigure
echo "✅ WiFi configuré"
