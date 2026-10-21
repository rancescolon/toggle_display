#!/usr/bin/env python3
"""
KDE Plasma Display & LG WebOS TV Switcher Script
------------------------------------------------
Toggles display output between a Desktop Monitor and an LG WebOS TV using
kscreen-doctor. Handles Wake-on-LAN (WOL) to power on the TV and aiowebostv
to power off the TV.
"""

import asyncio
import socket
import subprocess
import sys
import time

# ==============================================================================
# CONFIGURATION (Replace with your actual device details)
# ==============================================================================
MONITOR = "DP-1"                       # Primary PC monitor output name (e.g. DP-1, DisplayPort-0)
TV = "HDMI-A-2"                        # TV display output name (e.g. HDMI-A-1, HDMI-A-2)
TV_MAC = "XX:XX:XX:XX:XX:XX"            # TV MAC address for Wake-on-LAN
TV_IP = "192.168.1.XXX"                # TV local IP address
CLIENT_KEY = "00000000000000000000000000000000"  # WebOS client key for authentication

# Display Modes (run `kscreen-doctor --outputs` to find your mode IDs)
MONITOR_MODE = "37"                   # Target resolution/refresh rate mode ID for Monitor[cite: 1]
TV_FALLBACK_MODE = "1"                # Stable initial fallback mode ID for TV[cite: 1]
TV_TARGET_MODE = "10"                 # High refresh rate mode ID (e.g. 4K @ 120Hz)[cite: 1]
# ==============================================================================


def run_kscreen(args):
    """Executes kscreen-doctor with provided arguments and suppresses console output."""
    try:
        subprocess.run(
            ["kscreen-doctor"] + args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def get_kscreen_outputs():
    """Fetches full state text output from kscreen-doctor --outputs."""
    try:
        res = subprocess.run(
            ["kscreen-doctor", "--outputs"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=True,
        )
        return res.stdout
    except Exception:
        return ""


def check_output_state(output_name, keyword):
    """
    Checks if a given output display (e.g., HDMI-A-2) currently contains
    a specific state keyword (e.g., 'enabled' or 'connected').
    """
    outputs_text = get_kscreen_outputs()
    lines = outputs_text.splitlines()
    for i, line in enumerate(lines):
        if output_name in line:
            # Check up to 2 lines following the output name match
            for j in range(i, min(i + 3, len(lines))):
                if keyword in lines[j]:
                    return True
    return False


async def power_off_tv():
    """Sends power-off payload to LG WebOS TV asynchronously."""
    try:
        from aiowebostv import WebOsClient

        client = WebOsClient(TV_IP, client_key=CLIENT_KEY)
        await client.connect()
        await client.power_off()
        await client.disconnect()
    except Exception as e:
        print(f"Error: Failed to power off TV via WebOS - {e}", file=sys.stderr)


def send_wol():
    """Sends Wake-on-LAN magic packets to turn on the TV."""
    try:
        mac_bytes = bytes.fromhex(TV_MAC.replace(":", "").replace("-", ""))
        magic = b"\xff" * 6 + mac_bytes * 16
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            # Send to specific IP and general broadcast address
            sock.sendto(magic, (TV_IP, 9))
            sock.sendto(magic, ("255.255.255.255", 9))
    except Exception as e:
        print(f"Error: Failed to send Wake-on-LAN magic packet - {e}", file=sys.stderr)


def main():
    tv_enabled = check_output_state(TV, "enabled")

    if tv_enabled:
        # --- SWITCH BACK TO DESKTOP MONITOR ---
        success = run_kscreen([
            f"output.{MONITOR}.enable",
            f"output.{MONITOR}.mode.{MONITOR_MODE}",
            f"output.{MONITOR}.primary",
            f"output.{TV}.disable",
        ])
        if not success:
            print("Error: kscreen-doctor command failed when switching to Monitor.", file=sys.stderr)

        time.sleep(1)

        if not check_output_state(MONITOR, "enabled"):
            print("Error: Verification failed. Monitor did not enable successfully.", file=sys.stderr)

        # Send turn off command to TV
        asyncio.run(power_off_tv())

    else:
        # --- SWITCH TO TV ---
        send_wol()

        # Poll for up to 30 seconds waiting for TV HDMI connection to register
        count = 0
        while not check_output_state(TV, "connected"):
            time.sleep(1)
            count += 1
            if count >= 30:
                print("Error: Timed out waiting for TV to report as connected.", file=sys.stderr)
                sys.exit(1)

        # Step 1: Switch to TV using stable base resolution/refresh mode
        success_step1 = run_kscreen([
            f"output.{TV}.enable",
            f"output.{TV}.mode.{TV_FALLBACK_MODE}",
            f"output.{TV}.primary",
            f"output.{MONITOR}.disable",
        ])

        if not success_step1:
            print("Error: Initial topology switch to TV failed.", file=sys.stderr)
        else:
            time.sleep(2)
            # Step 2: Transition to high refresh rate target mode
            success_step2 = run_kscreen([f"output.{TV}.mode.{TV_TARGET_MODE}"])
            if not success_step2:
                print("Error: Failed to set TV target refresh mode.", file=sys.stderr)

        time.sleep(1)
        if not check_output_state(TV, "enabled"):
            print("Error: Verification failed. TV display output did not enable successfully.", file=sys.stderr)


if __name__ == "__main__":
    main()
