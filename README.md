# HW group for Home Assistant

Local-polling integration for [HW group](https://www.hw-group.com/) devices:

- **Poseidon / Damocles sensor units**: temperature, humidity, pressure, voltage, current and
  any other measurement channel (`SenSet`), digital inputs (`BinaryInSet`), relay outputs
  (`OutputSet`). Channels that appear later on the device are added automatically.
- **HWg-SMS-GW3 GSM gateway**: signal strength/quality, network operator and status, SMS/call
  counters, SIM status, and the actions `hwgroup.send_sms` / `hwgroup.call_number`, plus an
  optional `notify` entity.

This is a rewrite of the earlier `hwgroup` integration. Entry data, `unique_id`s and the
`hwgroup.send_sms` action are compatible, so existing entities, history and statistics are kept.

## Installation (HACS)

Add the repository as a custom repository (category *Integration*), install **HW group**,
restart Home Assistant. Then *Settings → Devices & services → Add integration → HW group*.

## What changed compared to 1.x

| Problem in 1.x | Now |
|---|---|
| Text values (`network_operator` = `A1`) had `state_class: measurement` → `ValueError`, entity never created | Text sensors have no state class and no unit; numeric sensors only get one when the value is numeric |
| `UnicodeDecodeError` on gateway responses | Bytes are decoded tolerantly (UTF-8, fallback Windows-1252), control characters are stripped, parser errors are handled |
| Warnings "No switches/binary sensors found" at every start | Platforms only create what the device reports; no warning |
| Exceptions when the device is down | Entities become `unavailable`; setup retries; wrong credentials start re-authentication |
| `status.xml` failure killed everything | Only the gateway status sensors become unavailable |
| `-999.9` shown as a real value | Treated as "no sensor plugged" → `unknown` |
| mA/°F reported with wrong unit | Correct units and device classes |
| Failed SMS only logged | The action raises an error the automation can see |

## Setup, options, reauth

- **Setup:** host, optional port/credentials/name. The device type is detected from the device.
- **Options:** polling interval (default 30 s), inputs to invert, default SMS recipient (SMS gateway
  only; creates the `notify` entity "SMS").
- **Reconfigure** changes host/port/credentials without removing the entry.

## Actions

```yaml
action: hwgroup.send_sms
data:
  phone_number: "+43676123456"
  message: "Server room too hot"
  # device_id: optional config entry id or device id; default = first SMS gateway
```

`hwgroup.call_number` rings a number and hangs up. With the notify entity:

```yaml
action: notify.send_message
target:
  entity_id: notify.<gateway>_sms
data:
  message: "Hello"
```

`+` in phone numbers is passed unencoded, exactly like 1.x (the gateway's web server expects it).

## Notes

- Relay switching uses `output.xml?id=…&state=…` carried over from 1.x. It is **untested on real
  hardware** (no device with outputs available). Please report results.
- Inbound SMS contained in `status.xml` are intentionally ignored (privacy).
- Diagnostics redact host, credentials, serial, MAC and the default recipient.

## Development

```bash
pip install -r requirements_test.txt
pytest
```

Release: push a branch. CI lints, runs tests, hassfest and HACS validation, opens and squash-merges
the PR and creates a release (bump from commit messages: `feat` → minor, `BREAKING`/`!:` → major,
else patch; `[skip release]` suppresses).

## License

MIT
