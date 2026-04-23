#!/usr/bin/env python3
"""Fetch SL bus departures from ResRobot v2.1, publish via MQTT.

Page 600:          bus index  (bus_index template)
Pages 605/609/610: per-line   (bus_departures template)

Config (callevision.yaml):
    bus_departures:
        api_key: <ResRobot v2.1 key>         # or env RESROBOT_API_KEY
        stop_id: "740098000"                 # ResRobot extId for the stop
        stop_name: "Gribbylunds centrum"     # max 25 chars
        lines: ["605", "609", "610"]

Usage:
    python scripts/fetch-bus-departures.py [--dry-run]
    python scripts/fetch-bus-departures.py --find-stop "Gribbylunds centrum"
"""

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

import paho.mqtt.client as mqtt
import yaml

RESROBOT_BASE = "https://api.resrobot.se/v2.1"
INDEX_PAGE = 600
LINE_PAGES = {"605": 605, "609": 609, "610": 610}
MQTT_CLIENT_ID = "callevision-bus-departures"

MONTH_SV = ["JAN", "FEB", "MAR", "APR", "MAJ", "JUN",
            "JUL", "AUG", "SEP", "OKT", "NOV", "DEC"]


def load_config(path=None):
    repo = Path(__file__).parent.parent
    if path is None:
        path = repo / "config" / "callevision.yaml"
        if not path.exists():
            path = repo / "config" / "callevision.yaml.example"
    with open(path) as f:
        return yaml.safe_load(f) or {}


def sv_time(dt: datetime) -> str:
    return f"{dt.day} {MONTH_SV[dt.month - 1]} {dt.strftime('%H:%M')}"


def _get(endpoint: str, api_key: str, params: dict) -> dict:
    params["accessId"] = api_key
    params["format"] = "json"
    url = f"{RESROBOT_BASE}/{endpoint}?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read())


def find_stop(api_key: str, name: str) -> None:
    """Print matching stops from ResRobot location search."""
    data = _get("location.name", api_key, {"input": name})
    stops = data.get("stopLocationOrCoordLocation", [])
    if not stops:
        print("Inga hållplatser hittades.")
        return
    for item in stops:
        sl = item.get("StopLocation", {})
        if sl:
            ext_id = sl.get("extId", sl.get("id", "?"))
            name_str = sl.get("name", "")
            place = sl.get("place", "")
            print(f"  extId: {ext_id:<15}  {name_str}  ({place})")


def fetch_departures(api_key: str, stop_id: str) -> list:
    """Fetch raw departures from ResRobot (up to 60, within 120 min)."""
    data = _get("departureBoard", api_key, {
        "id": stop_id,
        "maxJourneys": 60,
        "duration": 120,
    })
    return data.get("Departure", [])


def _line_of(dep: dict) -> str:
    """Extract line name from a departure entry."""
    products = dep.get("Product", [])
    if isinstance(products, dict):
        products = [products]
    for p in products:
        name = p.get("line") or p.get("num") or p.get("displayNumber") or ""
        if name:
            return name
    return ""


def _dep_time(dep: dict) -> str:
    """Return best departure time as 'YYYY-MM-DD HH:MM' string."""
    t = dep.get("rtTime") or dep.get("time") or ""
    d = dep.get("rtDate") or dep.get("date") or ""
    return f"{d} {t[:5]}"


def _format_dep(dep: dict, now: datetime) -> str:
    """Format one departure as a ≤36-char string: 'HH:MM  Destination'."""
    time_str = (dep.get("rtTime") or dep.get("time") or "")[:5]
    date_str = dep.get("rtDate") or dep.get("date") or ""
    direction = dep.get("direction") or dep.get("name") or ""

    try:
        dep_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        minutes = int((dep_dt - now).total_seconds() / 60)
    except (ValueError, TypeError):
        minutes = 999

    if minutes <= 0:
        time_col = "Nu   "
    elif minutes < 20:
        m = f"{minutes} min"
        time_col = f"{m:<5}"
    else:
        time_col = time_str

    # time_col (5) + "  " (2) + direction = 36 max → direction max 29
    return f"{time_col}  {direction[:29]}"


def bus_dep_payload(line: str, stop_name: str, deps: list, now: datetime) -> dict:
    fields = {
        "bus_number": line,
        "stop_name": stop_name,
        "updated": sv_time(now),
        "footer": f"Busstider - sid {INDEX_PAGE}",
    }
    for i, dep in enumerate(deps[:10], 1):
        fields[f"dep_{i}"] = _format_dep(dep, now)
    return {"v": 1, "template": "bus_departures", "fields": fields}


def bus_index_payload(stop_name: str, deps_by_line: dict, now: datetime) -> dict:
    # Merge all lines, sort by departure time, take first 5
    all_deps = [dep for deps in deps_by_line.values() for dep in deps]
    all_deps.sort(key=lambda d: _dep_time(d))
    combined = all_deps[:5]

    fields = {
        "stop_name": stop_name,
        "updated": sv_time(now),
        "page_605": "605",
        "label_605": "Alla avg. linje 605",
        "page_609": "609",
        "label_609": "Alla avg. linje 609",
        "page_610": "610",
        "label_610": "Alla avg. linje 610",
        "footer": stop_name,
    }
    for i, dep in enumerate(combined, 1):
        line = _line_of(dep)
        dep_str = _format_dep(dep, now)
        # Prepend line number (4 chars): "605  12:34  Häggvik"
        entry = f"{line:<4} {dep_str}"[:38]
        fields[f"dep_{i}"] = entry
    return {"v": 1, "template": "bus_index", "fields": fields}


def publish_all(config: dict, pages: list) -> None:
    mqtt_cfg = config.get("mqtt", {})
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=MQTT_CLIENT_ID)
    if mqtt_cfg.get("username"):
        client.username_pw_set(mqtt_cfg["username"], mqtt_cfg.get("password"))
    client.connect(mqtt_cfg.get("host", "localhost"), int(mqtt_cfg.get("port", 1883)))
    client.loop_start()
    infos = []
    for topic, payload in pages:
        info = client.publish(
            topic,
            json.dumps(payload, ensure_ascii=False),
            retain=True,
            qos=1,
        )
        infos.append((topic, info))
    for topic, info in infos:
        info.wait_for_publish(timeout=10)
        print(f"  → {topic}")
    client.loop_stop()
    client.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Publicera busstider till teletext via MQTT"
    )
    parser.add_argument("--config", help="Sökväg till callevision.yaml")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skriv ut JSON utan att publicera till MQTT")
    parser.add_argument("--find-stop", metavar="NAMN",
                        help="Sök ResRobot extId för en hållplats och avsluta")
    args = parser.parse_args()

    config = load_config(args.config)
    bus_cfg = config.get("bus_departures", {})

    api_key = bus_cfg.get("api_key") or os.environ.get("RESROBOT_API_KEY")
    if not api_key:
        print("Fel: api_key saknas i bus_departures-sektionen i callevision.yaml.", file=sys.stderr)
        print("Alternativt: sätt miljövariabeln RESROBOT_API_KEY.", file=sys.stderr)
        sys.exit(1)

    if args.find_stop:
        find_stop(api_key, args.find_stop)
        return

    stop_id = bus_cfg.get("stop_id")
    if not stop_id:
        print("Fel: stop_id saknas i bus_departures-sektionen.", file=sys.stderr)
        print("Kör --find-stop 'Gribbylunds centrum' för att hitta rätt extId.", file=sys.stderr)
        sys.exit(1)

    stop_name = bus_cfg.get("stop_name", "Hållplats")
    lines = [str(l) for l in bus_cfg.get("lines", ["605", "609", "610"])]

    print(f"Hämtar avgångar från hållplats {stop_id} ({stop_name})...")
    all_deps = fetch_departures(api_key, stop_id)
    print(f"Hittade {len(all_deps)} avgångar totalt.")

    now = datetime.now()
    deps_by_line = {}
    pages = []

    for line in lines:
        deps = [d for d in all_deps if _line_of(d) == line]
        deps_by_line[line] = deps
        print(f"  Linje {line}: {len(deps)} avgångar")
        page_num = LINE_PAGES.get(line)
        if page_num is None:
            print(f"  (ingen sida konfigurerad för linje {line}, hoppar över)", file=sys.stderr)
            continue
        pages.append((f"callevision/pages/{page_num}", bus_dep_payload(line, stop_name, deps, now)))

    pages.append((
        f"callevision/pages/{INDEX_PAGE}",
        bus_index_payload(stop_name, deps_by_line, now),
    ))

    if args.dry_run:
        print("\n--- DRY RUN (publicerar inte till MQTT) ---")
        for topic, payload in pages:
            print(f"\n{topic}:")
            print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("Publicerar till MQTT...")
        publish_all(config, pages)
        print(f"\nKlart! Sidor: {', '.join(t.split('/')[-1] for t, _ in pages)} publicerade.")


if __name__ == "__main__":
    main()
