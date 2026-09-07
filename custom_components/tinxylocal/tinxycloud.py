"""Minimal client for ephemeral cloud-assisted device onboarding."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import aiohttp


@dataclass
class TinxyHostConfiguration:
    """Tinxy cloud host configuration."""

    api_token: str
    api_url: str


class TinxyCloud:
    """Client to query Tinxy cloud for device catalog during setup."""

    def __init__(
        self,
        host_config: TinxyHostConfiguration,
        web_session: aiohttp.ClientSession,
    ) -> None:
        """Initialize cloud client."""
        self.host_config = host_config
        self.web_session = web_session

    async def get_device_list(self) -> list[dict[str, Any]]:
        """Fetch list of devices associated with account."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.host_config.api_token}",
        }
        url = f"{self.host_config.api_url.rstrip('/')}/devices"
        async with self.web_session.get(url, headers=headers, timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                if isinstance(data, list):
                    return data
                if isinstance(data, dict) and "devices" in data:
                    return data["devices"]
            return []
