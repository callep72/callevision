# Setup notes

Notes on getting Callevision running on a Raspberry Pi 1 Model B.

## Hardware

- Raspberry Pi 1 Model B (ARMv6, 512 MB RAM)
- Composite video out (yellow RCA) to TV
- Ethernet for network

## Operating system

Raspberry Pi OS Legacy (32-bit) Lite — Debian Bookworm base.
Flashed with Raspberry Pi Imager, SSH enabled, hostname `teletext`.

## /boot/firmware/config.txt changes

- Commented out: `dtoverlay=vc4-kms-v3d`
  (KMS driver conflicts with Dispmanx, which raspi-teletext requires)
- Added under `[all]`:
  - `enable_tvout=1` — composite output is disabled by default on Bookworm
  - `sdtv_mode=2` — PAL (default is NTSC)
  - `gpu_mem=64` — ensure GPU has enough memory for Dispmanx

Verify after reboot:

    vcgencmd get_config int | grep -E "sdtv|tvout"
    vcgencmd get_mem gpu

## raspi-teletext build

Low-level teletext packet generator by Alistair Buxton.
Source: https://github.com/ali1234/raspi-teletext

### Dependencies

    sudo apt install -y git build-essential libraspberrypi-dev

### VideoCore library paths

On Bookworm the VideoCore libs and headers live under
`/usr/lib/arm-linux-gnueabihf/` and `/usr/include/`, but the
raspi-teletext Makefile expects them under `/opt/vc/`. Create symlinks:

    sudo mkdir -p /opt/vc/lib /opt/vc/include
    sudo ln -sf /usr/lib/arm-linux-gnueabihf/libbcm_host.so /opt/vc/lib/libbcm_host.so
    sudo ln -sf /usr/lib/arm-linux-gnueabihf/libvcos.so /opt/vc/lib/libvcos.so
    sudo ln -sf /usr/lib/arm-linux-gnueabihf/libvchiq_arm.so /opt/vc/lib/libvchiq_arm.so
    sudo ln -sf /usr/include/bcm_host.h /opt/vc/include/bcm_host.h
    sudo ln -sf /usr/include/interface /opt/vc/include/interface
    sudo ln -sf /usr/include/vcinclude /opt/vc/include/vcinclude

### Build

    cd ~/projects
    git clone https://github.com/ali1234/raspi-teletext.git
    cd raspi-teletext
    make

Produces three binaries: `tvctl`, `teletext`, `cea608`.

## Verifying teletext output

    sudo ./tvctl on       # enables teletext mode, expect "Teletext output is now on."
    ./teletext            # runs the demo; press TEXT on the TV remote
    sudo ./tvctl off      # disables teletext mode

## Pending

- SCART-to-RCA adapter for the B&O TV
- Write first TTI page
- Build MQTT bridge
