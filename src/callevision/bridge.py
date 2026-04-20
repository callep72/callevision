"""MQTT-to-Teletext bridge — raw TTI and JSON template variant."""

import json
import logging
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

import paho.mqtt.client as mqtt

from . import config as cfg
from . import templates
from . import tti

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("callevision.bridge")

TOPIC_PREFIX = "callevision/pages/"
RAW_SUFFIX = "/raw"
PAGE_RANGE = range(100, 900)


def _parse_topic(topic: str) -> tuple[int, bool] | None:
    """Return (page, is_raw) or None if topic doesn't match expected patterns."""
    if not topic.startswith(TOPIC_PREFIX):
        return None
    rest = topic[len(TOPIC_PREFIX):]

    if rest.endswith(RAW_SUFFIX):
        middle = rest[: -len(RAW_SUFFIX)]
        is_raw = True
    else:
        middle = rest
        is_raw = False

    try:
        page = int(middle)
    except ValueError:
        return None

    return (page, is_raw) if page in PAGE_RANGE else None


def _restart_service(service_name: str) -> None:
    try:
        subprocess.run(
            ["sudo", "systemctl", "restart", service_name],
            check=True,
            capture_output=True,
        )
        log.info("Restarted %s", service_name)
    except subprocess.CalledProcessError as exc:
        log.error("Failed to restart %s: %s", service_name, exc.stderr.decode().strip())


class _ServiceReloader:
    def __init__(
        self,
        service_name: str,
        debounce_ms: int,
        restart_func: Callable[[str], None] = _restart_service,
        timer_factory: Callable[[float, Callable[[], None]], threading.Timer] = threading.Timer,
    ) -> None:
        self.service_name = service_name
        self.debounce_seconds = max(0, debounce_ms) / 1000
        self.restart_func = restart_func
        self.timer_factory = timer_factory
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    def request(self) -> None:
        if self.debounce_seconds <= 0:
            self._restart_now()
            return

        with self._lock:
            if self._timer is not None:
                self._timer.cancel()

            timer = self.timer_factory(self.debounce_seconds, self._restart_from_timer)
            if hasattr(timer, "daemon"):
                timer.daemon = True
            self._timer = timer
            timer.start()

        log.info("Scheduled restart of %s in %dms", self.service_name, int(self.debounce_seconds * 1000))

    def close(self) -> None:
        with self._lock:
            timer = self._timer
            self._timer = None
        if timer is not None:
            timer.cancel()

    def _restart_from_timer(self) -> None:
        with self._lock:
            self._timer = None
        self._restart_now()

    def _restart_now(self) -> None:
        self.restart_func(self.service_name)


def _handle_raw(page: int, payload: str, topic: str, dest: Path, userdata: dict) -> None:
    if not tti.validate(payload):
        log.warning("Payload on %s does not look like TTI, ignoring", topic)
        return

    payload, mismatch = tti.rewrite_pn(payload, page)
    if mismatch:
        log.warning("PN mismatch on %s; rewrote to %d (topic wins)", topic, page)

    userdata["raw_pages"].add(page)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(payload, encoding="utf-8")
    log.info("Wrote %s (raw)", dest.name)
    userdata["reloader"].request()


def _handle_json(page: int, payload: str, topic: str, dest: Path, userdata: dict) -> None:
    if page in userdata["raw_pages"]:
        log.warning("Page %d has raw content; ignoring JSON on %s", page, topic)
        return

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        log.warning("Invalid JSON on %s: %s", topic, exc)
        return

    for key in ("v", "template", "fields"):
        if key not in data:
            log.warning("JSON on %s missing required key '%s', ignoring", topic, key)
            return

    if data["v"] != 1:
        log.warning("Unsupported JSON version %r on %s, ignoring", data["v"], topic)
        return

    rendered = templates.render(userdata["templates_dir"], data["template"], page, data["fields"])
    if rendered is None:
        return

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(rendered.encode("utf-8"))
    log.info("Wrote %s (json template=%s)", dest.name, data["template"])
    userdata["reloader"].request()


def _on_connect(client: mqtt.Client, userdata: dict, flags, rc, properties=None) -> None:
    if rc != 0:
        log.error("MQTT connect failed, rc=%d", rc)
        return
    log.info("Connected to MQTT broker")
    client.subscribe("callevision/pages/+/raw")
    client.subscribe("callevision/pages/+")
    log.info("Subscribed to callevision/pages/+/raw and callevision/pages/+")


def _on_message(client: mqtt.Client, userdata: dict, msg: mqtt.MQTTMessage) -> None:
    topic: str = msg.topic
    payload_bytes: bytes = msg.payload

    parsed = _parse_topic(topic)
    if parsed is None:
        log.warning("Ignoring message on unexpected topic: %s", topic)
        return

    page, is_raw = parsed
    pages_dir: Path = userdata["pages_dir"]
    dest: Path = pages_dir / f"P{page}.tti"

    if not payload_bytes:
        if is_raw:
            userdata["raw_pages"].discard(page)
        if dest.exists():
            dest.unlink()
            log.info("Deleted %s (empty payload)", dest.name)
            userdata["reloader"].request()
        else:
            log.info("Empty payload for page %d, file already absent", page)
        return

    try:
        payload = payload_bytes.decode("utf-8")
    except UnicodeDecodeError:
        log.warning("Non-UTF-8 payload on %s, ignoring", topic)
        return

    if is_raw:
        _handle_raw(page, payload, topic, dest, userdata)
    else:
        _handle_json(page, payload, topic, dest, userdata)


def run(config_path: str | Path) -> None:
    conf = cfg.load(config_path)

    mqtt_conf = conf["mqtt"]
    pages_dir = Path(conf["paths"]["runtime_pages"])
    templates_dir = Path(conf["paths"]["templates"])
    service_name = conf["teletext"]["service_name"]
    reload_debounce_ms = int(conf["teletext"]["reload_debounce_ms"])
    reloader = _ServiceReloader(service_name, reload_debounce_ms)

    userdata = {
        "pages_dir": pages_dir,
        "templates_dir": templates_dir,
        "reloader": reloader,
        "raw_pages": set(),
    }

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
    try:
        client.loop_forever()
    finally:
        reloader.close()


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
