"""Asynchronous client for Hitachi projector network control (TCP 23 / 9715).

Exposes the same interface and state format as PJLinkClient so the entities can
use either protocol.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from hashlib import md5
import logging

from .pjlink import PJLinkAuthError, PJLinkConnectionError, PJLinkError

_LOGGER = logging.getLogger(__name__)

# Port 23 uses bare command frames; any other port (9715) wraps them in a
# 02 0D ... checksum, connection-id envelope.
UNWRAPPED_PORT = 23

GREETING_WAIT = 2.0
COMMAND_GAP = 0.05

ACTION_SET = 0x01
ACTION_GET = 0x02

TYPE_POWER = 0x6000
TYPE_INPUT = 0x2000
TYPE_VIDEO_MUTE = 0x20A0
TYPE_AUDIO_MUTE = 0x2002

REPLY_ACK = 0x06
REPLY_NAK = 0x15
REPLY_ERROR = 0x1C
REPLY_DATA = 0x1D
REPLY_BUSY = 0x1F

# Payload length that follows the reply code.
REPLY_LENGTHS = {REPLY_ACK: 0, REPLY_NAK: 0, REPLY_ERROR: 2, REPLY_DATA: 2, REPLY_BUSY: 2}

AUTH_ERROR = b"\x04\x00"

POWER_STATES = {0: "0", 1: "1", 2: "2"}

INPUTS = {
    "00": "Computer 1",
    "04": "Computer 2",
    "03": "HDMI 1",
    "0D": "HDMI 2",
    "11": "HDBaseT",
}


def _crc(data: bytes) -> bytes:
    """CRC used by the Hitachi command frame (low byte first)."""
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    value = (((crc & 0xFF) << 8) | (crc >> 8)) ^ 0xD2E5
    return bytes((value & 0xFF, value >> 8))


def build_command(action: int, cmd_type: int, value: int = 0) -> bytes:
    """Build the 13-byte BE EF command frame."""
    body = bytes((action, 0)) + cmd_type.to_bytes(2, "little") + value.to_bytes(2, "little")
    return bytes((0xBE, 0xEF, 0x03, 0x06, 0x00)) + _crc(body) + body


def wrap_command(frame: bytes, connection_id: int = 0) -> bytes:
    """Wrap a command frame for TCP 9715."""
    data = bytes((0x02, len(frame))) + frame
    return data + bytes(((-sum(data)) & 0xFF, connection_id))


class HitachiClient:
    """High level client; opens one connection per operation."""

    def __init__(self, host: str, port: int, password: str | None = None, timeout: float = 5) -> None:
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout
        self._wrapped = port != UNWRAPPED_PORT
        self._lock = asyncio.Lock()

    def _frame(self, action: int, cmd_type: int, value: int) -> bytes:
        frame = build_command(action, cmd_type, value)
        return wrap_command(frame) if self._wrapped else frame

    async def _read_reply(self, reader: asyncio.StreamReader) -> tuple[int, bytes]:
        # Skip anything that is not a reply code (e.g. an unused 8 byte challenge).
        while (code := (await reader.readexactly(1))[0]) not in REPLY_LENGTHS:
            pass
        length = REPLY_LENGTHS[code]
        trailer = await reader.readexactly(length + (1 if self._wrapped else 0))
        return code, trailer[:length]

    async def _transact(self, commands: list[tuple[int, int, int]]) -> list[tuple[int, bytes]]:
        """Send commands over one connection and return (code, data) replies."""
        async with self._lock:
            writer: asyncio.StreamWriter | None = None
            stage = "tcp connect"
            try:
                async with asyncio.timeout(self.timeout):
                    reader, writer = await asyncio.open_connection(self.host, self.port)
                stage = "authentication challenge"
                digest = b""
                if self.password:
                    try:
                        async with asyncio.timeout(GREETING_WAIT):
                            nonce = await reader.readexactly(8)
                    except TimeoutError:
                        _LOGGER.debug("No challenge from %s:%s, assuming no authentication", self.host, self.port)
                    else:
                        digest = md5(nonce + self.password.encode()).hexdigest().encode()  # noqa: S324
                replies: list[tuple[int, bytes]] = []
                for index, command in enumerate(commands):
                    stage = f"command {command[1]:#06x}"
                    if index:
                        await asyncio.sleep(COMMAND_GAP)
                    async with asyncio.timeout(self.timeout):
                        # This projector expects the digest on every command.
                        writer.write(digest + self._frame(*command))
                        await writer.drain()
                        reply = await self._read_reply(reader)
                    _LOGGER.debug("Hitachi %s:%s %s -> %r", self.host, self.port, stage, reply)
                    replies.append(reply)
                return replies
            except (OSError, TimeoutError, asyncio.IncompleteReadError) as err:
                _LOGGER.warning(
                    "Hitachi %s:%s failed during %s: %r", self.host, self.port, stage, err
                )
                raise PJLinkConnectionError(repr(err)) from err
            finally:
                if writer is not None:
                    writer.close()
                    with suppress(OSError):
                        await writer.wait_closed()

    @staticmethod
    def _check(reply: tuple[int, bytes]) -> tuple[int, bytes]:
        """Raise for authentication, busy and error replies."""
        code, data = reply
        if code == REPLY_BUSY:
            if data == AUTH_ERROR:
                raise PJLinkAuthError("Authentication error")
            raise PJLinkError("Projector busy")
        if code == REPLY_NAK:
            raise PJLinkError("Command not understood")
        if code == REPLY_ERROR:
            raise PJLinkError(f"Command cannot be executed ({data.hex()})")
        return reply

    @classmethod
    def _value(cls, reply: tuple[int, bytes]) -> int | None:
        """Return the value of a Get reply, None if the projector refused it."""
        try:
            code, data = cls._check(reply)
        except PJLinkAuthError:
            raise
        except PJLinkError:
            return None
        return int.from_bytes(data, "little") if code == REPLY_DATA else None

    async def get_info(self) -> dict:
        """Verify connectivity and credentials and return static information."""
        self._check((await self._transact([(ACTION_GET, TYPE_POWER, 0)]))[0])
        return {"class": 1, "name": None, "manufacturer": "Hitachi", "model": None}

    async def get_state(self, with_info: bool = False) -> dict:
        """Poll the projector."""
        replies = await self._transact(
            [
                (ACTION_GET, TYPE_POWER, 0),
                (ACTION_GET, TYPE_INPUT, 0),
                (ACTION_GET, TYPE_VIDEO_MUTE, 0),
                (ACTION_GET, TYPE_AUDIO_MUTE, 0),
            ]
        )
        power, source, video, audio = (self._value(r) for r in replies)
        data: dict = {
            "class": 1,
            "power": POWER_STATES.get(power),
            "input": None if source is None else f"{source:02X}",
            "mute": None,
        }
        if video is not None or audio is not None:
            data["mute"] = {(0, 0): "30", (1, 0): "11", (0, 1): "21", (1, 1): "31"}[
                (1 if video else 0, 1 if audio else 0)
            ]
        if with_info:
            data.update(
                {
                    "name": None,
                    "manufacturer": "Hitachi",
                    "model": None,
                    "sources": dict(INPUTS),
                }
            )
        return data

    async def _set(self, commands: list[tuple[int, int, int]]) -> None:
        for reply in await self._transact(commands):
            code, _ = self._check(reply)
            if code != REPLY_ACK:
                raise PJLinkError(f"Unexpected reply {code:#04x}")

    async def set_power(self, on: bool) -> None:
        await self._set([(ACTION_SET, TYPE_POWER, 1 if on else 0)])

    async def set_input(self, code: str) -> None:
        await self._set([(ACTION_SET, TYPE_INPUT, int(code, 16))])

    async def set_mute(self, code: str) -> None:
        """Handle PJLink style codes: 10/11 video, 20/21 audio, 30/31 both."""
        value = 1 if code[1:] == "1" else 0
        types = {
            "1": [TYPE_VIDEO_MUTE],
            "2": [TYPE_AUDIO_MUTE],
            "3": [TYPE_VIDEO_MUTE, TYPE_AUDIO_MUTE],
        }[code[:1]]
        await self._set([(ACTION_SET, t, value) for t in types])

    async def volume(self, up: bool) -> None:
        raise PJLinkError("Volume control is not supported")
