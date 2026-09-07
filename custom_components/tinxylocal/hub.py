"""Module for interacting with Tinxy devices locally via pure-async HTTP."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
import logging
import time
from typing import Any

import aiohttp

from .const import DEFAULT_RATE_LIMIT_DELAY, DEFAULT_REQUEST_TIMEOUT
from .crypto import encrypt_tinxy_payload

_LOGGER = logging.getLogger(__name__)
HEADERS = {"Content-Type": "application/json", "Connection": "close"}


class TinxyConnectionException(Exception):
    """Exception for connection errors with Tinxy devices."""


class TinxyLocalException(Exception):
    """General exception for Tinxy local device errors."""


@dataclass
class QueuedCommand:
    """Represents a queued command for a Tinxy device."""

    command_type: str  # 'toggle' or 'brightness'
    relay_number: int
    action: int | None = None
    brightness: int | None = None
    future: asyncio.Future | None = None
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            self.timestamp = time.time()


class TinxyLocalHub:
    """Hub for controlling a Tinxy device over local LAN."""

    def __init__(
        self,
        hass: Any,
        host: str,
        request_timeout: int = DEFAULT_REQUEST_TIMEOUT,
    ) -> None:
        """Initialize with Home Assistant instance and the device host IP."""
        self.hass = hass
        self.host = f"http://{host}"
        self.ip_address = host
        self.request_timeout = request_timeout

        # Rate-limiting & command queue (prevents crashing single-threaded ESP web server)
        self.command_timeout = 15.0
        self.queue_limit = 30
        self.rate_limit_delay = DEFAULT_RATE_LIMIT_DELAY

        self.device_queue: deque[QueuedCommand] = deque()
        self.device_worker_task: asyncio.Task | None = None
        self.last_command_time = 0.0
        self.last_command_timestamp = 0
        self._shutdown = False

    async def validate_ip(
        self, web_session: aiohttp.ClientSession, chip_id: str | None = None
    ) -> str:
        """Validate local API availability via GET /info."""
        try:
            data = await self._send_request("GET", "/info", web_session=web_session)
            if data is not None and isinstance(data, dict):
                if chip_id and data.get("chip_id") and data["chip_id"] != chip_id:
                    return "wrong_chip_id"
                return "ok"
            return "api_not_available"
        except TinxyConnectionException:
            return "connection_error"
        except Exception:
            return "connection_error"

    async def fetch_device_data(
        self, node: dict[str, Any], web_session: aiohttp.ClientSession
    ) -> dict[str, Any] | None:
        """Fetch status directly from device GET /info."""
        try:
            data = await self._send_request("GET", "/info", web_session=web_session)
            if not data or not isinstance(data, dict):
                return None
            return self._decode_device_data(data, node)
        except TinxyConnectionException as err:
            _LOGGER.debug(
                "Connection timeout/error updating node %s: %s",
                node.get("name", self.ip_address),
                err,
            )
            raise TinxyLocalException(f"Connection error: {err}") from err
        except Exception as err:
            _LOGGER.debug(
                "Error updating node %s: %s", node.get("name", self.ip_address), err
            )
            raise TinxyLocalException(f"Unexpected error: {err}") from err

    @staticmethod
    def _decode_device_data(
        data: dict[str, Any], node: dict[str, Any]
    ) -> dict[str, Any]:
        """Decode raw device status JSON."""
        decoded_data: dict[str, Any] = {
            "rssi": data.get("rssi"),
            "status": data.get("status"),
            "ssid": data.get("ssid"),
            "ip": data.get("ip", node.get("ip_address")),
            "chip_id": data.get("chip_id"),
            "firmware": data.get("firmware"),
            "version": data.get("version"),
            "model": node.get("model", "Tinxy Smart Device"),
            "door": data.get("door"),
        }

        # Parse relay state bitmask (e.g. "01" or "0011")
        state_str = str(data.get("state", ""))
        bright_str = str(data.get("bright", ""))

        for i, sub_dev in enumerate(node.get("devices", [])):
            dev_name = sub_dev.get("name", f"Relay {i}")
            dev_type = sub_dev.get("type", "Switch")
            dev_key = f"{dev_name}_{i}"

            is_on = state_str[i] == "1" if i < len(state_str) else False

            # Brightness in increments of 3 digits (e.g. 100100100100)
            brightness = 0
            if len(bright_str) >= (i + 1) * 3:
                try:
                    brightness = int(bright_str[i * 3 : (i + 1) * 3])
                except ValueError:
                    brightness = 0

            decoded_data[dev_key] = {
                "state": is_on,
                "brightness": brightness,
                "type": dev_type,
                "relay_number": i,
            }

        return decoded_data

    async def queue_command(
        self,
        command: QueuedCommand,
        mqtt_pass: str,
        web_session: aiohttp.ClientSession,
    ) -> bool:
        """Queue a command for sequential rate-limited execution."""
        if self._shutdown:
            return False

        # Ensure worker task is running
        if self.device_worker_task is None or self.device_worker_task.done():
            self.device_worker_task = asyncio.create_task(
                self._device_worker(mqtt_pass, web_session)
            )

        # Queue limit protection
        if len(self.device_queue) >= self.queue_limit:
            _LOGGER.warning("Command queue full for %s", self.ip_address)
            raise TinxyLocalException("Command queue full")

        # Deduplicate pending commands for the same relay
        new_queue: deque[QueuedCommand] = deque()
        for cmd in self.device_queue:
            if cmd.relay_number == command.relay_number:
                if cmd.future and not cmd.future.done():
                    cmd.future.set_exception(
                        TinxyLocalException("Superseded by newer command")
                    )
            else:
                new_queue.append(cmd)

        self.device_queue = new_queue

        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        command.future = future
        self.device_queue.append(command)

        return await future

    async def _device_worker(
        self, mqtt_pass: str, web_session: aiohttp.ClientSession
    ) -> None:
        """Worker executing commands sequentially with rate-limit spacing."""
        while not self._shutdown:
            try:
                if not self.device_queue:
                    await asyncio.sleep(0.05)
                    continue

                # Rate limiting spacing
                time_since_last = time.time() - self.last_command_time
                if time_since_last < self.rate_limit_delay:
                    await asyncio.sleep(self.rate_limit_delay - time_since_last)

                command = self.device_queue.popleft()

                # Timeout check
                if time.time() - command.timestamp > self.command_timeout:
                    if command.future and not command.future.done():
                        command.future.set_exception(
                            TinxyLocalException("Command timed out in queue")
                        )
                    continue

                # Execute
                try:
                    result = await self._execute_http_command(
                        command, mqtt_pass, web_session
                    )
                    self.last_command_time = time.time()
                    if command.future and not command.future.done():
                        command.future.set_result(result)
                except Exception as err:
                    _LOGGER.error(
                        "Error sending command to %s: %s", self.ip_address, err
                    )
                    if command.future and not command.future.done():
                        command.future.set_exception(err)

            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.error("Worker error for %s: %s", self.ip_address, err)
                await asyncio.sleep(0.5)

    async def _execute_http_command(
        self,
        command: QueuedCommand,
        mqtt_pass: str,
        web_session: aiohttp.ClientSession,
    ) -> bool:
        """Send authenticated POST /toggle to the device via pure aiohttp."""
        # Enforce strictly monotonic timestamp to prevent ESP hardware replay rejection (HTTP 400)
        now_ts = int(time.time())
        if now_ts <= self.last_command_timestamp:
            now_ts = self.last_command_timestamp + 1
        self.last_command_timestamp = now_ts

        encrypted_token = encrypt_tinxy_payload(mqtt_pass, timestamp=now_ts)
        action_val = str(command.action if command.action is not None else 1)

        payload: dict[str, Any] = {
            "password": encrypted_token,
            "action": action_val,
            "relayNumber": command.relay_number + 1,  # Hardware wire protocol is 1-indexed (1..N)
        }

        if command.brightness is not None and command.brightness >= 0:
            payload["brightness"] = command.brightness

        response = await self._send_request(
            "POST", "/toggle", payload=payload, web_session=web_session
        )
        return response is not None

    async def _send_request(
        self,
        method: str,
        endpoint: str,
        payload: dict[str, Any] | None = None,
        web_session: aiohttp.ClientSession | None = None,
    ) -> dict[str, Any] | None:
        """Send HTTP request with timeout handling."""
        if web_session is None:
            raise TinxyConnectionException("No web_session provided")

        url = f"{self.host}{endpoint}"
        try:
            async with web_session.request(
                method,
                url=url,
                json=payload if method == "POST" else None,
                headers=HEADERS,
                timeout=aiohttp.ClientTimeout(total=self.request_timeout),
            ) as response:
                if response.status == 200:
                    return await response.json(content_type=None)
                raise TinxyConnectionException(
                    f"Request failed with status {response.status}"
                )
        except (TimeoutError, asyncio.TimeoutError) as err:
            raise TinxyConnectionException(f"Request to {url} timed out") from err
        except aiohttp.ClientError as err:
            raise TinxyConnectionException(f"Client error for {url}: {err}") from err

    async def shutdown(self) -> None:
        """Cancel worker tasks on unload."""
        self._shutdown = True
        if self.device_worker_task and not self.device_worker_task.done():
            self.device_worker_task.cancel()
