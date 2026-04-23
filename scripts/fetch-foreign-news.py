#!/usr/bin/env python3
"""Fetch international news via Claude web search, publish via MQTT.

Page 200:      news index (news_index template)
Pages 201-210: individual news stories (news_story template)

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python scripts/fetch-foreign-news.py [--dry-run] [--config path/to/callevision.yaml]
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import paho.mqtt.client as mqtt
import yaml

INDEX_PAGE = 200
STORY_PAGES = list(range(201, 211))  # 201–210, ten pages
SECTION = "UTRIKES"
MQTT_CLIENT_ID = "callevision-news-fetcher-utrikes"

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


def sv_date(dt: datetime) -> str:
    return f"{dt.day} {MONTH_SV[dt.month - 1]} {dt.strftime('%H:%M')}"


def fetch_and_format(client: anthropic.Anthropic, model: str) -> list:
    """Ask Claude to search for international news and format it for teletext."""

    system = (
        "Du är ett verktyg som söker internationella nyheter och formaterar dem för "
        "teletextvisning. Du returnerar alltid ett JSON-svar som ditt sista meddelande, "
        "ingenting annat efter JSON-listan. "
        "Använd bara vanliga svenska tecken: a-z A-Z 0-9 åäöÅÄÖ och vanlig interpunktion."
    )

    user = """Sök efter de 10 viktigaste internationella nyheterna från de senaste 24 timmarna.

Gör flera sökningar för att täcka in olika delar av världen och olika ämnen. Välj nyheter
från seriösa, välrenommerade källor som BBC, Reuters, AP, AFP, DW, Guardian, NYT, Le Monde
eller liknande internationella medier. Undvik källor med politisk agenda, statlig
desinformation eller propaganda (t.ex. RT, Sputnik, PressTV).

När du har samlat ihop 10 nyheter, returnera en JSON-lista med ett objekt per nyhet med fälten:
- "title": max 36 tecken, rubriken på svenska (förkorta vid ordgräns vid behov)
- "subhead": max 40 tecken, kort underrubrik på svenska
- "body": lista av strängar, varje sträng max 40 tecken, max 12 element,
  brödtexten på svenska radbruten vid mellanslag
- "index_headline": max 34 tecken, kort kärnfull rubrik för indexsidan
- "source": källans namn, t.ex. "BBC", "Reuters", "AP"

Regler:
- Skriv ALL text på svenska
- Överskrid ALDRIG teckengränserna — hellre kortare än för lång
- Radbryt BARA vid mellanslag (aldrig mitt i ett ord)
- Returnera ENBART JSON-listan som ditt sista svar, ingen annan text"""

    messages = [{"role": "user", "content": user}]
    tools = [{"type": "web_search_20250305", "name": "web_search"}]

    for _ in range(5):
        response = client.messages.create(
            model=model,
            max_tokens=8192,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            tools=tools,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            break

        if response.stop_reason == "pause_turn":
            # Server-side tool loop hit iteration limit — continue where it left off
            messages = [
                {"role": "user", "content": user},
                {"role": "assistant", "content": response.content},
            ]
            continue

        break

    print(f"  (tokens: {response.usage.input_tokens} in, {response.usage.output_tokens} out)")

    text = next((b.text for b in reversed(response.content) if b.type == "text"), "")

    if not text:
        print("  Svar saknar textblock. Innehåll i svaret:", file=sys.stderr)
        for block in response.content:
            print(f"    {block.type}", file=sys.stderr)
        raise ValueError("Claude returnerade inget textblock")

    # Try markdown code blocks first
    if "```" in text:
        for part in text.split("```")[1::2]:
            part = part.strip().lstrip("json").strip()
            try:
                return json.loads(part)
            except json.JSONDecodeError:
                continue

    # Try to find a bare JSON array anywhere in the text
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    print("  Råsvar från Claude:", file=sys.stderr)
    print(text[:500], file=sys.stderr)
    raise ValueError("Kunde inte hitta JSON i svaret")


def story_payload(formatted: dict, now: datetime) -> dict:
    source = formatted.get("source", "")
    footer = f"{source} - sid {INDEX_PAGE}" if source else f"Utrikesnyheter - sid {INDEX_PAGE}"
    fields = {
        "section": SECTION,
        "title": formatted["title"],
        "updated": sv_date(now),
        "subhead": formatted.get("subhead", ""),
        "footer": footer[:37],
    }
    for i, line in enumerate(formatted.get("body", [])[:12], 1):
        fields[f"body_{i}"] = line
    return {"v": 1, "template": "news_story", "fields": fields}


def index_payload(formatted_list: list, now: datetime) -> dict:
    fields = {
        "title": SECTION,
        "updated": sv_date(now),
        "strapline": "Internationella nyheter",
        "footer": "BBC Reuters AP AFP DW",
    }
    for i, formatted in enumerate(formatted_list, 1):
        fields[f"lead_{i}_page"] = str(STORY_PAGES[i - 1])
        fields[f"lead_{i}_headline"] = formatted["index_headline"]
    return {"v": 1, "template": "news_index", "fields": fields}


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
        description="Publicera utrikesnyheter till teletext via MQTT"
    )
    parser.add_argument("--config", help="Sökväg till callevision.yaml")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skriv ut JSON utan att publicera till MQTT")
    parser.add_argument(
        "--model",
        default=os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5"),
        help="Claude-modell (standard: claude-haiku-4-5, eller CLAUDE_MODEL-miljövariabeln)"
    )
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Fel: miljövariabeln ANTHROPIC_API_KEY är inte satt.", file=sys.stderr)
        sys.exit(1)

    config = load_config(args.config)
    client = anthropic.Anthropic(api_key=api_key)

    print(f"Söker internationella nyheter med Claude ({args.model})...")
    formatted_list = fetch_and_format(client, args.model)
    print(f"Hittade {len(formatted_list)} nyheter.")

    now = datetime.now(timezone.utc)
    pages = []
    for i, formatted in enumerate(formatted_list):
        page_num = STORY_PAGES[i]
        pages.append((f"callevision/pages/{page_num}", story_payload(formatted, now)))
        print(f"  Sida {page_num}: {formatted['title']}")

    pages.append((
        f"callevision/pages/{INDEX_PAGE}",
        index_payload(formatted_list, now),
    ))

    if args.dry_run:
        print("\n--- DRY RUN (publicerar inte till MQTT) ---")
        for topic, payload in pages:
            print(f"\n{topic}:")
            print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("Publicerar till MQTT...")
        publish_all(config, pages)
        print(f"\nKlart! {len(formatted_list)} nyhetssida(or) + indexsida {INDEX_PAGE} publicerade.")


if __name__ == "__main__":
    main()
