# Callevision

Teletext broadcasting from MQTT on a Raspberry Pi 1 with composite output.

Each teletext page corresponds to an MQTT topic — publish to a topic,
the page updates on screen.

## How it works

The bridge subscribes to `callevision/pages/+/raw` on an MQTT broker.
When a retained or live message arrives with a TTI payload, it writes
`P{page}.tti` to `runtime/pages/` and restarts VBIT2 to pick up the change.
An empty payload deletes the corresponding file.

MQTT retained messages are the source of truth. Deleting `runtime/pages/`
and restarting the bridge restores everything from the broker.

## Directory layout

| Path | Purpose |
|------|---------|
| `pages/examples/` | Git-tracked example pages — inspiration and starting points |
| `runtime/pages/` | Where VBIT2 reads; written by the bridge from MQTT (gitignored) |

## Running the bridge

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Create config

```bash
cp config/callevision.yaml.example config/callevision.yaml
$EDITOR config/callevision.yaml   # set broker host, credentials, paths
```

### 3. Bootstrap runtime pages (first run)

Publish the example pages to MQTT so the bridge populates `runtime/pages/`:

```bash
MQTT_HOST=<broker-ip> MQTT_USER=<username> MQTT_PASS=<password> \
  scripts/publish-examples.sh
```

Or publish a single page manually:

```bash
mosquitto_pub -h <broker-ip> -u <username> -P <password> \
  -t callevision/pages/110/raw -r \
  -f pages/examples/P110.tti
```

### 4. Start the bridge

```bash
scripts/run-bridge.sh
# or
PYTHONPATH=src python -m callevision.bridge
# or with an explicit config path:
PYTHONPATH=src python -m callevision.bridge /path/to/callevision.yaml
```

## Deleting a page

Send an empty retained message to remove a page:

```bash
mosquitto_pub -h <broker-ip> -u <username> -P <password> \
  -t callevision/pages/110/raw -r -n
```

## Running tests

```bash
PYTHONPATH=src python -m pytest tests/
```

## Hardware

- Raspberry Pi 1 Model B
- Composite video to TV via SCART
- Ethernet connected

## Status

Milestone 3 complete: MQTT bridge working end-to-end.
