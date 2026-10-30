"""Async client for HW group devices (values.xml / status.xml over HTTP)."""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import quote
from xml.sax.saxutils import escape

import aiohttp
from yarl import URL

from .const import DEFAULT_PORT, DEVICE_TYPE_SMS_GATEWAY, REQUEST_TIMEOUT
from .parser import DeviceData, HWGroupParseError, parse_status, parse_values, result_ok

_LOGGER = logging.getLogger(__name__)


class HWGroupError(Exception):
    """Base error."""


class HWGroupConnectionError(HWGroupError):
    """Device not reachable or answered with an error."""


class HWGroupAuthError(HWGroupError):
    """Credentials rejected."""


class HWGroupApi:
    """Client for one device."""

    def __init__(
        self,
        host: str,
        session: aiohttp.ClientSession,
        username: str | None = None,
        password: str | None = None,
        port: int = DEFAULT_PORT,
    ) -> None:
        """Initialize."""
        self.host = host
        self.port = port
        self._session = session
        self._auth = (
            aiohttp.BasicAuth(username, password) if username and password else None
        )
        self._timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)

    @property
    def base_url(self) -> str:
        """Base URL of the device."""
        return f"http://{self.host}:{self.port}"

    async def _get(self, path_and_query: str) -> bytes:
        """GET raw bytes. The query is passed through unchanged (see send_sms)."""
        url = URL(f"{self.base_url}/{path_and_query}", encoded=True)
        try:
            async with self._session.get(
                url, auth=self._auth, timeout=self._timeout
            ) as response:
                if response.status in (401, 403):
                    raise HWGroupAuthError("authentication failed")
                if response.status != 200:
                    raise HWGroupConnectionError(f"HTTP {response.status}")
                return await response.read()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise HWGroupConnectionError(f"{type(err).__name__}: {err}") from err

    async def async_get_data(self) -> DeviceData:
        """Fetch and parse everything the device offers."""
        try:
            data = parse_values(await self._get("values.xml"))
        except HWGroupParseError as err:
            raise HWGroupConnectionError(f"values.xml unreadable: {err}") from err

        if data.info.device_type == DEVICE_TYPE_SMS_GATEWAY:
            try:
                data.status = parse_status(await self._get("status.xml"))
            except (HWGroupConnectionError, HWGroupParseError) as err:
                # Teilausfall: Statuswerte werden "nicht verfuegbar", der Rest bleibt.
                _LOGGER.debug("status.xml of %s unavailable: %s", self.host, err)
            except HWGroupAuthError:
                raise
        return data

    async def async_set_output(self, output_id: str, on: bool) -> None:
        """Switch an output (HW group XML protocol: POST BinaryOutSet, needs Mode 0).

        Needs a user with write access to outputs if the device is secured.
        """
        body = (
            "<?xml version=\"1.0\" encoding=\"utf-8\"?><Root><BinaryOutSet><Entry>"
            f"<ID>{escape(str(output_id))}</ID><Value>{int(on)}</Value>"
            "</Entry></BinaryOutSet></Root>"
        )
        try:
            async with self._session.post(
                f"{self.base_url}/setup.xml",
                data=body.encode(),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                auth=self._auth,
                timeout=self._timeout,
            ) as response:
                if response.status in (401, 403):
                    raise HWGroupAuthError("no write access to the outputs")
                if response.status >= 400:
                    raise HWGroupConnectionError(f"HTTP {response.status}")
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise HWGroupConnectionError(f"{type(err).__name__}: {err}") from err

    async def async_read_version(self) -> str | None:
        """Firmware version straight from the device (used while it restarts)."""
        return parse_values(await self._get("values.xml")).info.version

    async def async_upload_firmware(self, payload: bytes, filename: str) -> None:
        """Upload a .hwg firmware to the web upload form; the device flashes and restarts."""
        form = aiohttp.FormData()
        form.add_field(
            "filename", payload, filename=filename, content_type="application/octet-stream"
        )
        form.add_field("Submit", "Upload")
        try:
            async with self._session.post(
                f"{self.base_url}/upload",
                data=form,
                auth=self._auth,
                timeout=aiohttp.ClientTimeout(total=240),
            ) as response:
                if response.status in (401, 403):
                    raise HWGroupAuthError("no permission to upload firmware")
                body = await response.text(errors="replace")
                if response.status != 200 or "Successfully uploaded" not in body:
                    raise HWGroupError(f"firmware upload rejected (HTTP {response.status})")
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise HWGroupConnectionError(f"{type(err).__name__}: {err}") from err

    async def _command(self, query: str) -> None:
        raw = await self._get(f"values.xml?{query}")
        if not result_ok(raw):
            raise HWGroupError("gateway did not confirm the command (no <Rslt>1</Rslt>)")

    async def async_send_sms(self, phone_number: str, message: str) -> None:
        """Queue an SMS. '+' stays unencoded exactly like the previous version."""
        await self._command(
            f"Cmd=SMS&Nmr={quote(phone_number, safe='+')}&Text={quote(message)}"
        )

    async def async_call_number(self, phone_number: str) -> None:
        """Ring a number."""
        await self._command(f"Cmd=Call&Nmr={quote(phone_number, safe='+')}")
