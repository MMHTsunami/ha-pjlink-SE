# ha-pjlink-SE
pjlink integration for Home Assistant that creates device with associated entities in home assistant for control and status feedback.

## Installation
Copy `custom_components/pjlink_se` into your Home Assistant `config/custom_components` folder (or add this repository to HACS as a custom repository) and restart.

## Setup
Settings → Devices & Services → Add Integration → **PJLink SE**. Enter the projector IP, port (default `4352`) and password (only if the projector requires one). Repeat for each projector; each becomes a device.

## Entities
| Entity | Platform | Notes |
|---|---|---|
| Power | switch | on while warming up |
| Source | select | names from `INNM` on class 2, generic names on class 1 |
| Audio mute / Video mute | switch | via `AVMT` |
| Volume up / down | button | `SVOL`, PJLink class 2 only |

Both PJLink class 1 and class 2 projectors are supported (class is auto-detected).
