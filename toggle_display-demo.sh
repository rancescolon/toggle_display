# ==========================================
# CONFIGURATION
# ==========================================
MONITOR="DP-0"                          # Your primary monitor's output name
TV="HDMI-0"                             # Your TV's output name
TV_MAC="XX:XX:XX:XX:XX:XX"              # Your TV's MAC address
TV_IP="192.168.X.X"                     # Your TV's local IP address
CLIENT_KEY="YOUR_CLIENT_KEY_HERE"       # Your webOS client key
BROADCAST_IP="192.168.X.255"            # Your network's broadcast address
# ==========================================

CURRENT_PRIMARY=$(xrandr | grep " primary " | awk '{print $1}')

if [ "$CURRENT_PRIMARY" = "$TV" ]; then
    # Switch to Monitor and power off TV via webOS API
    xrandr --output "$MONITOR" --mode 1920x1080 --rate 144 --primary --output "$TV" --off

    python3 -c "import asyncio
from aiowebostv import WebOsClient

async def main():
    try:
        client = WebOsClient('$TV_IP', client_key='$CLIENT_KEY')
        await client.connect()
        await client.power_off()
        await client.disconnect()
    except Exception:
        pass

asyncio.run(main())" &

else
    # Wake TV via Magic Packet
    python3 -c "import socket
mac_bytes = bytes.fromhex('$TV_MAC'.replace(':', ''))
magic = b'\xff' * 6 + mac_bytes * 16
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
sock.sendto(magic, ('$TV_IP', 9))
sock.sendto(magic, ('$BROADCAST_IP', 9))
sock.close()" &

    # Wait for the TV to be detected by the system (max 30s)
    count=0
    while ! xrandr | grep -q "^$TV connected"; do
        sleep 1
        count=$((count+1))
        [ "$count" -ge 30 ] && exit 1
    done

    # Wait for the EDID modes to load (max 15s)
    count=0
    while ! xrandr | grep -A 2 "^$TV connected" | grep -q "3840x2160"; do
        sleep 1
        count=$((count+1))
        [ "$count" -ge 15 ] && break
    done

    # Execute the final switch to the TV
    xrandr --output "$TV" --mode 3840x2160 --rate 119.88 --primary --output "$MONITOR" --off
fi
