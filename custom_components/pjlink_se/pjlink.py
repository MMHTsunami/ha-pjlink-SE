"""Minimal asynchronous PJLink (class 1 and class 2) client."""

from __future__ import annotations

import asyncio
import logging
from hashlib import md5

_LOGGER = logging.getLogger(__name__)

INPUT_TYPES = {"1": "RGB", "2": "Video", "3": "Digital", "4": "Storage", "5": "Network", "6": "Internal"}

ERRORS = {
    "ERR1": "Undefined command",
    "ERR2": "Out-of-parameter",
    "ERR3": "Unavailable time",
    "ERR4": "Projector/display failure",
    "ERRA": "Authentication error",
}


class PJLinkError(Exception):
    """Generic PJLink error."""


class PJLinkAuthError(PJLinkError):
    """Authentication failed."""


class PJLinkConnectionError(PJLinkError):
    """Cannot connect to the projector."""


def default_input_name(code: str) -> str:
    """Return a generic name for an input code such as '31'."""
    kind = INPUT_TYPES.get(code[:1], "Input")
    return f"{kind} {code[1:]}"


class PJLinkSession:
    """A single TCP session; use as an async context manager."""

    def __init__(self, host: str, port: int, password: str | None, timeout: float) -> None:
        self._host = host
        self._port = port
        self._password = password or ""
        self._timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._prefix = ""
        self.pjlink_class = 1

    async def __aenter__(self) -> "PJLinkSession":
        try:
            async with asyncio.timeout(self._timeout):
                self._reader, self._writer = await asyncio.open_connection(
                    self._host, self._port
                )
                line = (await self._reader.readuntil(b"\r")).decode(
                    "ascii", "ignore"
                ).strip()
        except (OSError, TimeoutError, asyncio.IncompleteReadError) as err:
            await self.close()
            _LOGGER.warning(
                "PJLink connect/greeting to %s:%s failed: %r", self._host, self._port, err
            )
            raise PJLinkConnectionError(repr(err)) from err
        _LOGGER.debug("PJLink greeting from %s:%s: %r", self._host, self._port, line)
        parts = line.split()
        if line.upper().startswith("PJLINK ERRA"):
            await self.close()
            raise PJLinkAuthError("Authentication error")
        if len(parts) < 2 or parts[0].upper() != "PJLINK":
            await self.close()
            raise PJLinkConnectionError(f"Unexpected greeting: {line!r}")
        if parts[1] == "1":
            if not self._password:
                await self.close()
                raise PJLinkAuthError("Password required")
            if len(parts) < 3:
                await self.close()
                raise PJLinkConnectionError("Malformed authentication greeting")
            self._prefix = md5(  # noqa: S324 - mandated by the PJLink protocol
                (parts[2] + self._password).encode()
            ).hexdigest()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the connection."""
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except OSError:
                pass
            self._writer = None

    async def command(self, name: str, param: str = "?", pjclass: int | None = None) -> str:
        """Send a command and return the response body."""
        assert self._reader is not None and self._writer is not None
        cls = pjclass or self.pjlink_class
        data = f"{self._prefix}%{cls}{name} {param}\r"
        # Authentication digest is only required on the first command.
        self._prefix = ""
        try:
            async with asyncio.timeout(self._timeout):
                self._writer.write(data.encode())
                await self._writer.drain()
                line = (await self._reader.readuntil(b"\r")).decode(
                    "ascii", "ignore"
                ).strip()
        except (OSError, TimeoutError, asyncio.IncompleteReadError) as err:
            _LOGGER.warning("PJLink command %s to %s failed: %r", name, self._host, err)
            raise PJLinkConnectionError(repr(err)) from err
        _LOGGER.debug("PJLink %s -> %r", data.strip(), line)
        if line.upper().startswith("PJLINK ERRA"):
            raise PJLinkAuthError("Authentication error")
        head = f"%{cls}{name}="
        if not line.upper().startswith(head):
            raise PJLinkError(f"Unexpected response {line!r}")
        body = line[len(head):]
        if body in ERRORS:
            if body == "ERRA":
                raise PJLinkAuthError(ERRORS[body])
            raise PJLinkError(f"{name}: {ERRORS[body]}")
        return body


class PJLinkClient:
    """High level client; opens one session per operation."""

    def __init__(self, host: str, port: int, password: str | None = None, timeout: float = 5) -> None:
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout

    def _session(self) -> PJLinkSession:
        return PJLinkSession(self.host, self.port, self.password, self.timeout)

    @staticmethod
    async def _optional(session: PJLinkSession, name: str, param: str = "?", pjclass: int | None = None) -> str | None:
        try:
            return await session.command(name, param, pjclass)
        except PJLinkConnectionError:
            raise
        except PJLinkAuthError:
            raise
        except PJLinkError:
            return None

    async def _detect_class(self, session: PJLinkSession) -> int:
        body = await self._optional(session, "CLSS", "?", 1)
        try:
            session.pjlink_class = 2 if body and int(body[:1]) >= 2 else 1
        except ValueError:
            session.pjlink_class = 1
        return session.pjlink_class

    async def get_info(self) -> dict:
        """Return static information (used by the config flow and setup)."""
        async with self._session() as s:
            cls = await self._detect_class(s)
            return {
                "class": cls,
                "name": await self._optional(s, "NAME"),
                "manufacturer": await self._optional(s, "INF1"),
                "model": await self._optional(s, "INF2"),
            }

    async def get_state(self, with_info: bool = False) -> dict:
        """Poll the projector."""
        async with self._session() as s:
            cls = await self._detect_class(s)
            data: dict = {"class": cls}
            data["power"] = await self._optional(s, "POWR")
            data["input"] = await self._optional(s, "INPT")
            data["mute"] = await self._optional(s, "AVMT")
            if with_info:
                data["name"] = await self._optional(s, "NAME")
                data["manufacturer"] = await self._optional(s, "INF1")
                data["model"] = await self._optional(s, "INF2")
                inst = await self._optional(s, "INST") or ""
                codes = inst.split()
                sources = {c: default_input_name(c) for c in codes}
                if cls >= 2:
                    for code in codes:
                        name = await self._optional(s, "INNM", code, 2)
                        if name:
                            sources[code] = name
                data["sources"] = sources
            return data

    async def _set(self, name: str, param: str) -> None:
        async with self._session() as s:
            await self._detect_class(s)
            await s.command(name, param)

    async def set_power(self, on: bool) -> None:
        await self._set("POWR", "1" if on else "0")

    async def set_input(self, code: str) -> None:
        await self._set("INPT", code)

    async def set_mute(self, code: str) -> None:
        """Send an AVMT code: 10/11 video, 20/21 audio, 30/31 both."""
        await self._set("AVMT", code)

    async def volume(self, up: bool) -> None:
        """Adjust speaker volume (class 2 only)."""
        async with self._session() as s:
            await self._detect_class(s)
            await s.command("SVOL", "1" if up else "0", 2)
