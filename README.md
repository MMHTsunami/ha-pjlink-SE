# ha-pjlink-SE
pjlink integration for Home Assistant that creates device with associated entities in home assistant for control and status feedback.

## Installation
Copy `custom_components/pjlink_se` into your Home Assistant `config/custom_components` folder (or add this repository to HACS as a custom repository) and restart.

## Setup
Settings → Devices & Services → Add Integration → **PJLink SE**, then pick the control protocol:

- **PJLink** – enter the projector IP, port (default `4352`) and password (only if the projector requires one).
- **Hitachi network control** – for Hitachi projectors, using *Network Control Port 2* (TCP `9715`, default) or *Port 1* (TCP `23`). Enter the authentication password if authentication is enabled on that port in the projector's web page.

Repeat for each projector; each becomes a device.

Hitachi control is useful when another controller (for example Bitfocus Companion) already holds the projector's single PJLink session. It supports power, source (Computer 1/2, HDMI 1/2, HDBaseT), and audio/video mute; volume buttons are not available.

## Entities
| Entity | Platform | Notes |
|---|---|---|
| Power | switch | on while warming up |
| Source | select | names from `INNM` on class 2, generic names on class 1 |
| Audio mute / Video mute | switch | via `AVMT` |
| Volume up / down | button | `SVOL`, PJLink class 2 only |

Both PJLink class 1 and class 2 projectors are supported (class is auto-detected).

## Testing without Home Assistant
`pip install pytest pytest-asyncio && pytest tests` runs both clients against fake projectors. To check a real projector: `python tests/test_pjlink.py HOST [PORT] [PASSWORD]` or `python tests/test_hitachi.py HOST [PORT] [PASSWORD]`.
