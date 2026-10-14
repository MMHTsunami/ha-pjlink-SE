"""Tests for the PJLink client against a fake projector (no Home Assistant needed).

Run: pip install pytest pytest-asyncio && pytest tests
Real projector: python tests/test_pjlink.py HOST [PORT] [PASSWORD]
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from hashlib import md5
from pathlib import Path

import pytest

_path = Path(__file__).parent.parent / "custom_components" / "pjlink_se" / "pjlink.py"
_spec = importlib.util.spec_from_file_location("pjlink", _path)
pjlink = importlib.util.module_from_spec(_spec)
sys.modules["pjlink"] = pjlink
_spec.loader.exec_module(pjlink)

NONCE = "498e4a67"


class FakeProjector:
    """Minimal PJLink class 2 server."""

    def __init__(self, password: str | None = None) -> None:
        self.password = password
        self.power = "0"
        self.input = "11"
        self.mute = "30"
        self.received: list[str] = []
        self.server: asyncio.AbstractServer | None = None

    async def start(self) -> int:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        return self.server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        self.server.close()
        await self.server.wait_closed()

    async def _handle(self, reader, writer) -> None:
        writer.write((f"PJLINK 1 {NONCE}\r" if self.password else "PJLINK 0\r").encode())
        await writer.drain()
        first = True
        try:
            while line := (await reader.readuntil(b"\r")).decode():
                line = line.strip()
                if self.password and first:
                    digest, line = line[:32], line[32:]
                    if digest != md5((NONCE + self.password).encode()).hexdigest():
                        writer.write(b"PJLINK ERRA\r")
                        await writer.drain()
                        break
                first = False
                self.received.append(line)
                writer.write((self._reply(line) + "\r").encode())
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()

    def _reply(self, line: str) -> str:
        cmd, _, param = line.partition(" ")
        head = cmd[:6]
        if cmd[1] == "2" and cmd[2:6] == "CLSS" or cmd[2:6] == "CLSS":
            return f"{cmd[:2]}CLSS=2"
        name = cmd[2:6]
        if param == "?":
            values = {
                "POWR": self.power, "INPT": self.input, "AVMT": self.mute,
                "NAME": "Test", "INF1": "ACME", "INF2": "P1", "INST": "11 31",
            }
            if name == "INNM":
                return f"{head}=Input {param}"
            return f"{head}={values.get(name, 'ERR1')}" if name in values else f"{head}=ERR1"
        if name == "POWR":
            self.power = param
        elif name == "INPT":
            self.input = param
        elif name == "AVMT":
            self.mute = param
        elif name == "INNM":
            return f"{head}=Named"
        return f"{head}=OK"


@pytest.fixture
async def projector():
    fake = FakeProjector()
    port = await fake.start()
    fake.port = port
    yield fake
    await fake.stop()


@pytest.mark.asyncio
async def test_info_and_state(projector):
    client = pjlink.PJLinkClient("127.0.0.1", projector.port)
    info = await client.get_info()
    assert info == {"class": 2, "name": "Test", "manufacturer": "ACME", "model": "P1"}
    state = await client.get_state(with_info=True)
    assert state["power"] == "0"
    assert set(state["sources"]) == {"11", "31"}


@pytest.mark.asyncio
async def test_set_commands(projector):
    client = pjlink.PJLinkClient("127.0.0.1", projector.port)
    await client.set_power(True)
    await client.set_input("31")
    await client.set_mute("31")
    assert (projector.power, projector.input, projector.mute) == ("1", "31", "31")


@pytest.mark.asyncio
async def test_authentication():
    fake = FakeProjector(password="secret")
    port = await fake.start()
    try:
        ok = await pjlink.PJLinkClient("127.0.0.1", port, "secret").get_info()
        assert ok["class"] == 2
        with pytest.raises(pjlink.PJLinkAuthError):
            await pjlink.PJLinkClient("127.0.0.1", port, "wrong").get_info()
        with pytest.raises(pjlink.PJLinkAuthError):
            await pjlink.PJLinkClient("127.0.0.1", port, None).get_info()
    finally:
        await fake.stop()


@pytest.mark.asyncio
async def test_connection_refused():
    with pytest.raises(pjlink.PJLinkConnectionError):
        await pjlink.PJLinkClient("127.0.0.1", 1, timeout=1).get_info()


async def _live(host: str, port: int, password: str | None) -> None:
    client = pjlink.PJLinkClient(host, port, password)
    print("info :", await client.get_info())
    print("state:", await client.get_state(with_info=True))


if __name__ == "__main__":
    args = sys.argv[1:]
    asyncio.run(_live(args[0], int(args[1]) if len(args) > 1 else 4352, args[2] if len(args) > 2 else None))
