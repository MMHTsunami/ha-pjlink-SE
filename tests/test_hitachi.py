"""Tests for the Hitachi network control client against a fake projector.

Run: pip install pytest pytest-asyncio && pytest tests
Real projector: python tests/test_hitachi.py HOST [PORT] [PASSWORD]
"""

from __future__ import annotations

import asyncio
import importlib
import sys
import types
from hashlib import md5
from pathlib import Path

import pytest
import pytest_asyncio

_pkg_dir = Path(__file__).parent.parent / "custom_components" / "pjlink_se"
# Stub parent package so the modules import without Home Assistant installed.
_pkg = types.ModuleType("pjlink_se")
_pkg.__path__ = [str(_pkg_dir)]
sys.modules["pjlink_se"] = _pkg
hitachi = importlib.import_module("pjlink_se.hitachi")
pjlink = importlib.import_module("pjlink_se.pjlink")

NONCE = b"a572f60c"

# Frames from the Hitachi RS-232C / network command table.
MANUAL_FRAMES = {
    "BE EF 03 06 00 BA D2 01 00 00 60 01 00": (0x01, 0x6000, 1),
    "BE EF 03 06 00 2A D3 01 00 00 60 00 00": (0x01, 0x6000, 0),
    "BE EF 03 06 00 19 D3 02 00 00 60 00 00": (0x02, 0x6000, 0),
    "BE EF 03 06 00 FE D2 01 00 00 20 00 00": (0x01, 0x2000, 0),
    "BE EF 03 06 00 3E D0 01 00 00 20 04 00": (0x01, 0x2000, 4),
    "BE EF 03 06 00 0E D2 01 00 00 20 03 00": (0x01, 0x2000, 3),
    "BE EF 03 06 00 6E D6 01 00 00 20 0D 00": (0x01, 0x2000, 0x0D),
    "BE EF 03 06 00 CD D2 02 00 00 20 00 00": (0x02, 0x2000, 0),
    "BE EF 03 06 00 6E F1 01 00 A0 20 01 00": (0x01, 0x20A0, 1),
    "BE EF 03 06 00 D6 D2 01 00 02 20 01 00": (0x01, 0x2002, 1),
}


@pytest.mark.parametrize("frame,args", MANUAL_FRAMES.items())
def test_command_frames_match_manual(frame, args):
    assert hitachi.build_command(*args) == bytes.fromhex(frame)


def test_wrapped_frame_checksum():
    wrapped = hitachi.wrap_command(hitachi.build_command(0x02, 0x6000), 7)
    assert wrapped[:2] == b"\x02\x0d" and wrapped[-1] == 7
    assert sum(wrapped[:-1]) & 0xFF == 0


class FakeHitachi:
    """Fake projector; requires the digest on every command when a password is set."""

    def __init__(self, wrapped: bool, password: str | None = None) -> None:
        self.wrapped = wrapped
        self.password = password
        self.state = {0x6000: 0, 0x2000: 3, 0x20A0: 0, 0x2002: 0}
        self.server: asyncio.AbstractServer | None = None

    async def start(self) -> int:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        return self.server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        self.server.close()
        await self.server.wait_closed()

    def _reply(self, code: int, data: bytes, cid: int) -> bytes:
        return bytes([code]) + data + (bytes([cid]) if self.wrapped else b"")

    async def _handle(self, reader, writer) -> None:
        if self.password:
            writer.write(NONCE)
            await writer.drain()
        try:
            while True:
                lead = b""
                ok = True
                if self.password:
                    lead = await reader.readexactly(1)
                    if lead in tuple(bytes([c]) for c in b"0123456789abcdef"):  # hex digest present
                        digest = lead + await reader.readexactly(31)
                        ok = digest.decode() == md5(NONCE + self.password.encode()).hexdigest()
                        lead = b""
                    else:
                        ok = False
                if self.wrapped:
                    head = lead + await reader.readexactly(2 - len(lead))
                    frame = await reader.readexactly(13)
                    tail = await reader.readexactly(2)
                    cid = tail[1]
                else:
                    frame = lead + await reader.readexactly(13 - len(lead))
                    cid = 0
                if self.password and not ok:
                    writer.write(self._reply(0x1F, b"\x04\x00", cid))
                    await writer.drain()
                    continue
                body = frame[7:]
                action, cmd_type, value = body[0], int.from_bytes(body[2:4], "little"), int.from_bytes(body[4:6], "little")
                if frame != hitachi.build_command(action, cmd_type, value) or cmd_type not in self.state:
                    writer.write(self._reply(0x15, b"", cid))
                elif action == 0x02:
                    writer.write(self._reply(0x1D, self.state[cmd_type].to_bytes(2, "little"), cid))
                else:
                    self.state[cmd_type] = value
                    writer.write(self._reply(0x06, b"", cid))
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()


@pytest_asyncio.fixture(params=[True, False], ids=["port9715", "port23"])
async def projector(request):
    fake = FakeHitachi(wrapped=request.param)
    fake.port = await fake.start()
    yield fake
    await fake.stop()


def _client(fake, password=None):
    client = hitachi.HitachiClient("127.0.0.1", fake.port, password, timeout=2)
    client._wrapped = fake.wrapped  # the fake listens on a random port, not 9715/23
    return client


@pytest.mark.asyncio
async def test_state_and_commands(projector):
    client = _client(projector)
    state = await client.get_state(with_info=True)
    assert state["power"] == "0" and state["input"] == "03" and state["mute"] == "30"
    assert state["class"] == 1 and "03" in state["sources"]

    await client.set_power(True)
    await client.set_input("0D")
    await client.set_mute("31")
    state = await client.get_state()
    assert (state["power"], state["input"], state["mute"]) == ("1", "0D", "31")

    await client.set_mute("10")
    assert (await client.get_state())["mute"] == "21"
    await client.set_mute("20")
    assert (await client.get_state())["mute"] == "30"


@pytest.mark.asyncio
@pytest.mark.parametrize("wrapped", [True, False])
async def test_authentication(wrapped):
    fake = FakeHitachi(wrapped, "secret")
    fake.port = await fake.start()
    try:
        assert (await _client(fake, "secret").get_state())["power"] == "0"
        await _client(fake, "secret").set_power(True)
        assert fake.state[0x6000] == 1
        with pytest.raises(pjlink.PJLinkAuthError):
            await _client(fake, "wrong").get_info()
        with pytest.raises(pjlink.PJLinkAuthError):
            await _client(fake, None).get_info()
    finally:
        await fake.stop()


@pytest.mark.asyncio
async def test_connection_refused():
    with pytest.raises(pjlink.PJLinkConnectionError):
        await hitachi.HitachiClient("127.0.0.1", 1, timeout=1).get_info()


async def _live(host: str, port: int, password: str | None) -> None:
    client = hitachi.HitachiClient(host, port, password)
    print("info :", await client.get_info())
    print("state:", await client.get_state(with_info=True))


if __name__ == "__main__":
    args = sys.argv[1:]
    asyncio.run(_live(args[0], int(args[1]) if len(args) > 1 else 9715, args[2] if len(args) > 2 else None))
