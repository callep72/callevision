"""MQTT-to-Teletext bridge — raw TTI variant."""

import logging
import os
import subprocess
import sys
from pathlib import Path

import paho.mqtt.client as mqtt

from . import config as cfg
from . import tti

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("callevision.bridge")

TOPIC_PREFIX = "callevision/pages/"
RAW_SUFFIX = "/raw"
PAGE_RANGE = range(100, 900)


def _page_from_topic(topic: str) -> int | None:
    """Extract page number from callevision/pages/{page}/raw."""
    if not topic.startswith(TOPIC_PREFIX) or not topic.endswith(RAW_SUFFIX):
        return None
    middle = topic[len(TOPIC_PREFIX):-len(RAW_SUFFIX)]
    try:
        page = int(middle)
    except ValueError:
        return None
    return page if page in PAGE_RANGE else None


def _reload_service(service_name: str) -> None:
    try:
        subprocess.run(
            ["sudo", "systemctl", "restart", service_name],
            check=True,
            capture_output=True,
        )
        log.info("Restarted %s", service_name)
    except subprocess.CalledProcessError as exc:
        log.error("Failed to restart %s: %s", service_name, exc.stderr.decode().strip())


def _on_connect(client: mqtt.Client, userdata: dict, flags, rc, properties=None) -> None:
    if rc != 0:
        log.error("MQTT connect failed, rc=%d", rc)
        return
    log.info("Connected to MQTT broker")
    client.subscribe("callevision/pages/+/raw")
    log.info("Subscribed to callevision/pages/+/raw")


def _on_message(client: mqtt.Client, userdata: dict, msg: mqtt.MQTTMessage) -> None:
    topic: str = msg.topic
    payload_bytes: bytes = msg.payload

    page = _page_from_topic(topic)
    if page is None:
        log.warning("Ignoring message on unexpected topic: %s", topic)
        return

    pages_dir: Path = userdata["pages_dir"]
    service_name: str = userdata["service_name"]
    dest: Path = pages_dir / f"P{page}.tti"

    if not payload_bytes:
        if dest.exists():
            dest.unlink()
            log.info("Deleted %s (empty payload)", dest.name)
            _reload_service(service_name)
        else:
            log.info("Empty payload for page %d, file already absent", page)
        return

    try:
        payload = payload_bytes.decode("utf-8")
    except UnicodeDecodeError:
        log.warning("Non-UTF-8 payload on %s, ignoring", topic)
        return

    if not tti.validate(payload):
        log.warning("Payload on %s does not look like TTI, ignoring", topic)
        return

    payload, mismatch = tti.rewrite_pn(payload, page)
    if mismatch:
        log.warning("PN mismatch on %s; rewrote to %d (topic wins)", topic, page)

    pages_dir.mkdir(parents=True, exist_ok=True)
    dest.write_text(payload, encoding="utf-8")
    log.info("Wrote %s", dest.name)
    _reload_service(service_name)


def run(config_path: str | Path) -> None:
    conf = cfg.load(config_path)

    mqtt_conf = conf["mqtt"]
    pages_dir = Path(conf["paths"]["runtime_pages"])
    service_name = conf["teletext"]["service_name"]

    userdata = {"pages_dir": pages_dir, "service_name": service_name}

    client = mqtt.Client(
        client_id=mqtt_conf["client_id"],
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        userdata=userdata,
    )
    client.on_connect = _on_connect
    client.on_message = _on_message

    if mqtt_conf.get("username"):
        client.username_pw_set(mqtt_conf["username"], mqtt_conf.get("password"))

    log.info("Connecting to %s:%d", mqtt_conf["host"], mqtt_conf["port"])
    client.connect(mqtt_conf["host"], mqtt_conf["port"], keepalive=60)
    client.loop_forever()


def main() -> None:
    config_path = Path(__file__).parent.parent.parent / "config" / "callevision.yaml"
    if len(sys.argv) > 1:
        config_path = Path(sys.argv[1])

    if not config_path.exists():
        print(f"Config not found: {config_path}", file=sys.stderr)
        print("Copy config/callevision.yaml.example to config/callevision.yaml and edit it.", file=sys.stderr)
        sys.exit(1)

    run(config_path)


if __name__ == "__main__":
    main()
