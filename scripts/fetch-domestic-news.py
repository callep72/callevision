#!/usr/bin/env python3
"""Fetch domestic news from SVT RSS, format with Claude, publish via MQTT.

Pages 104-113: individual news stories (news_story template)
Page 101:      news index (news_index template)

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python scripts/fetch-domestic-news.py [--dry-run] [--hours 24] [--config path/to/callevision.yaml]
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import anthropic
import feedparser
import paho.mqtt.client as mqtt
import yaml

RSS_URL = "https://www.svt.se/nyheter/inrikes/rss.xml"
INDEX_PAGE = 101
STORY_PAGES = list(range(104, 114))  # 104–113, ten pages
SECTION = "INRIKES"
MQTT_CLIENT_ID = "callevision-news-fetcher"

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


def fetch_articles(hours: int) -> list:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    feed = feedparser.parse(RSS_URL)
    articles = []
    for entry in feed.entries:
        tp = entry.get("published_parsed")
        if tp is None:
            continue
        published = datetime(*tp[:6], tzinfo=timezone.utc)
        if published < cutoff:
            continue
        articles.append({
            "title": entry.get("title", "").strip(),
            "summary": entry.get("summary", "").strip(),
            "published": published,
        })
    articles.sort(key=lambda a: a["published"], reverse=True)
    return articles[:len(STORY_PAGES)]


def sv_date(dt: datetime) -> str:
    return f"{dt.day} {MONTH_SV[dt.month - 1]} {dt.strftime('%H:%M')}"


def format_with_claude(client: anthropic.Anthropic, articles: list, model: str) -> list:
    """Single Claude call to format all articles for teletext."""
    articles_json = json.dumps(
        [{"title": a["title"], "summary": a["summary"]} for a in articles],
        ensure_ascii=False,
    )

    system = (
        "Du är ett verktyg som formaterar svenska nyhetsartiklar för teletextvisning. "
        "Du returnerar alltid ett JSON-svar och ingenting annat. "
        "Använd bara vanliga svenska tecken: a-z A-Z 0-9 åäöÅÄÖ och vanlig interpunktion."
    )

    user = f"""Formatera dessa nyhetsartiklar för teletext. Strikta teckengränser måste följas.

Artiklar (JSON):
{articles_json}

Returnera en JSON-lista med ett objekt per artikel, i samma ordning, med fälten:
- "title": max 36 tecken, rubriken (förkorta vid ordgräns om nödvändigt)
- "subhead": max 40 tecken, kort sammanfattande underrubrik
- "body": lista av strängar, varje sträng max 40 tecken, max 12 element, texten radbruten vid mellanslag
- "index_headline": max 34 tecken, kort punchig rubrik för indexsidan

Regler:
- Skriv på svenska
- Överskrid ALDRIG teckengränserna — hellre kortare än för lång
- Radbryt BARA vid mellanslag
- index_headline ska vara kortare och mer kärnfull än title

Returnera ENBART JSON-listan, ingen förklarande text."""

    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=[{
            "type": "text",
            "text": system,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": user}],
    )

    text = next(b.text for b in response.content if b.type == "text")
    result = json.loads(text)
    print(f"  (tokens: {response.usage.input_tokens} in, {response.usage.output_tokens} out"
          f", cache_read: {response.usage.cache_read_input_tokens})")
    return result


def story_payload(article: dict, formatted: dict) -> dict:
    fields = {
        "section": SECTION,
        "title": formatted["title"],
        "updated": sv_date(article["published"]),
        "subhead": formatted.get("subhead", ""),
        "footer": f"Inrikesnyheter - sid {INDEX_PAGE}",
    }
    for i, line in enumerate(formatted.get("body", [])[:12], 1):
        fields[f"body_{i}"] = line
    return {"v": 1, "template": "news_story", "fields": fields}


def index_payload(articles: list, formatted_list: list, now: datetime) -> dict:
    fields = {
        "title": SECTION,
        "updated": sv_date(now),
        "strapline": "Senaste dygnets inrikesnyheter",
        "footer": "SVT Nyheter Inrikes",
    }
    for i, (article, formatted) in enumerate(zip(articles, formatted_list), 1):
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
        description="Publicera inrikesnyheter till teletext via MQTT"
    )
    parser.add_argument("--config", help="Sökväg till callevision.yaml")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Skriv ut JSON utan att publicera till MQTT"
    )
    parser.add_argument(
        "--hours", type=int, default=24,
        help="Antal timmar bakåt att hämta nyheter (standard: 24)"
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("CLAUDE_MODEL", "claude-opus-4-7"),
        help="Claude-modell (standard: claude-opus-4-7, eller CLAUDE_MODEL-miljövariabeln)"
    )
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Fel: miljövariabeln ANTHROPIC_API_KEY är inte satt.", file=sys.stderr)
        sys.exit(1)

    config = load_config(args.config)
    client = anthropic.Anthropic(api_key=api_key)

    print(f"Hämtar SVT Nyheter Inrikes (senaste {args.hours} timmarna)...")
    articles = fetch_articles(args.hours)
    if not articles:
        print("Inga artiklar hittades inom tidsramen.")
        sys.exit(0)
    print(f"Hittade {len(articles)} artikel(ar).")

    print(f"Formaterar med Claude ({args.model})...")
    formatted_list = format_with_claude(client, articles, args.model)

    now = datetime.now(timezone.utc)
    pages = []
    for i, (article, formatted) in enumerate(zip(articles, formatted_list)):
        page_num = STORY_PAGES[i]
        pages.append((f"callevision/pages/{page_num}", story_payload(article, formatted)))
        print(f"  Sida {page_num}: {formatted['title']}")

    pages.append((
        f"callevision/pages/{INDEX_PAGE}",
        index_payload(articles, formatted_list, now),
    ))

    if args.dry_run:
        print("\n--- DRY RUN (publicerar inte till MQTT) ---")
        for topic, payload in pages:
            print(f"\n{topic}:")
            print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("Publicerar till MQTT...")
        publish_all(config, pages)
        print(f"\nKlart! {len(articles)} nyhetssida(or) + indexsida {INDEX_PAGE} publicerade.")


if __name__ == "__main__":
    main()
