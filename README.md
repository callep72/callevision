# Callevision

Teletext broadcasting from MQTT on a Raspberry Pi 1 with composite output.

Each teletext page corresponds to an MQTT topic — publish to a topic,
the page updates on screen.

## How it works

The bridge subscribes to `callevision/pages/+/raw` on an MQTT broker.
When a retained or live message arrives with a TTI payload, it writes
`P{page}.tti` to the pages directory and restarts VBIT2 to pick up the change.
An empty payload deletes the corresponding file.

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

### 3. Start the bridge

```bash
scripts/run-bridge.sh
# or
PYTHONPATH=src python -m callevision.bridge
# or with an explicit config path:
PYTHONPATH=src python -m callevision.bridge /path/to/callevision.yaml
```

## Publishing a page

```bash
mosquitto_pub -h 192.168.1.50 -u callevision -P changeme \
  -t callevision/pages/110/raw -r \
  -f pages/P110.tti
```

## Deleting a page

Send an empty retained message to remove a page:

```bash
mosquitto_pub -h 192.168.1.50 -u callevision -P changeme \
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

Milestone 1 complete: MQTT-to-TTI bridge (raw variant).
