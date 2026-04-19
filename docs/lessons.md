# Lessons learned

## Raspi-teletext is sensitive to TTI control codes

When rendering TTI files with binary control codes for colors, 
double-height, and background colors, raspi-teletext can crash with:

    teletext: render.c:36: render_thread_func: Assertion 'update' failed.

Symptoms:
- VBIT2 process runs, teletext process missing
- Clock on TV stops updating (entire broadcast halts)
- Pages with just PN, PS, SC and plain text work fine
- edit.tf-generated pages (P111, P120) work

Workarounds:
- Keep templates plain text initially
- Add control codes one at a time and verify
- Check with `ps aux | grep teletext` that process is alive

## Service auto-restart trap

The bridge restarts callevision-teletext on every page update. If many 
MQTT messages arrive in quick succession, systemd's "restart too often" 
protection triggers and refuses to start the service further. Manual 
fix: `sudo systemctl reset-failed callevision-teletext`.

Proper fix: implement debounce in the bridge so rapid messages collapse 
into a single restart after a short delay.

## VideoCore teletext state can get stuck

After many `tvctl on` without corresponding `tvctl off`, the VideoCore 
registers can get into a state where the teletext process crashes 
immediately on start. Fix: `sudo reboot`.

## Raw TTI wins over JSON

When both `pages/{N}/raw` and `pages/{N}` (JSON) exist as retained 
messages, the bridge prefers raw. This can silently hide JSON updates. 
Check with `mosquitto_sub -v -t 'callevision/pages/100/raw'`.
