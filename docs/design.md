# Callevision Design

Teletext broadcasting from MQTT on Raspberry Pi.

## Core principle

Each teletext page is an MQTT topic. Publish to a topic, the page updates.
The MQTT broker is the source of truth. The Pi is a consumer.

## Topic structure

    callevision/pages/{page}          → JSON (smart bridge, default)
    callevision/pages/{page}/raw      → TTI (dumb bridge, override)
    callevision/pages/{page}/fastext  → FastText links, overridable
    callevision/state/current_page    → Pi publishes currently shown page
    callevision/control/set_page      → HA/others publish to change page

All pages use retained messages. The broker holds the full teletext state.

## Page numbering

- Valid range: 100–899
- Outside range: ignored with warning
- Subpage defaults to 1; carousels via /{page}/{subpage}
- Convention (not enforced):
  - 100-199: news / index
  - 200-299: sport
  - 300-399: weather / economy
  - 400-499: TV schedule
  - 500-599: culture
  - 600-699: local
  - 700-799: misc

## JSON schema (v1)

    {
      "v": 1,
      "title": "Weather",
      "header_color": "yellow",
      "body": [
        {"text": "It is raining", "color": "white"},
        {"text": "Temp: 8°C", "color": "cyan", "size": "double"}
      ],
      "fastext": {
        "red":    {"title": "Forecast", "page": 401},
        "green":  {"title": "Index",    "page": 100}
      }
    }

Missing fields use sensible defaults. Body is an array to allow per-line
styling. Plain strings also accepted as shorthand:

    {"v": 1, "body": ["Just text", "Another line"]}

## Raw vs JSON precedence

For each page number, bridge resolves content as follows:

1. If `pages/{page}/raw` exists with non-empty payload → use RAW (TTI)
2. Else if `pages/{page}` exists with non-empty payload → parse JSON, generate TTI
3. Else → page does not exist

When both exist, RAW wins but a warning is logged. The index page
shows `[R]` or `[J]` marker per page.

Empty payload = page removed (MQTT retained message deletion).

## System pages (generated, not writable)

- **Page 100** — Index. Auto-generated list of all published pages.
- **Page 199** — Status. Pi uptime, MQTT connection, page count.

Publisher attempts to write these are ignored with warning.

## Bridge architecture

    MQTT broker
        ↓ subscribe callevision/pages/#
    callevision bridge (Python)
        ↓ writes TTI files, signals reload
    VBIT2 (running as service)
        ↓ T42 stream
    raspi-teletext
        ↓ composite out
    TV (via SCART)

## Open questions

- How does bridge signal VBIT2 to reload? (SIGHUP? IPC? File watch?)
- Carousel timing: per-subpage delay, where configured?
- Authentication: MQTT ACL or trust all? (v1: trust all)
- Logging: journald? File? Both?
