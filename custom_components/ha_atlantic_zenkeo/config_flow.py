"""Config flow for Atlantic Zenkeo AC."""
import asyncio
import logging
from functools import partial
from typing import Any

import voluptuous as vol
from getmac import get_mac_address

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError


from .pyzenkeo import ZenkeoAC

_LOGGER = logging.getLogger(__name__)

# This is the schema that will be used to generate the form for the user.
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("host"): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    host = data["host"]
    try:
        mac_address = await hass.async_add_executor_job(
            partial(get_mac_address, ip=host)
        )
    except Exception as exc:
        _LOGGER.error("Could not get MAC address for %s", host)
        raise CannotConnect(f"Could not get MAC address for {host}") from exc

    if not mac_address:
        _LOGGER.error("Could not get MAC address for %s", host)
        raise CannotConnect(f"Could not get MAC address for {host}")

    api = ZenkeoAC(host, mac_address)

    try:
        if not await api.get_state():
            raise CannotConnect(f"Failed to get state from {host}, device may not be a Zenkeo AC")

    except asyncio.TimeoutError as exc:
        raise CannotConnect(f"Connection to {host} timed out") from exc

    except Exception as exc:
        _LOGGER.exception("Unexpected error connecting to %s", host)
        raise CannotConnect(f"Unexpected error connecting to {host}: {exc}") from exc

    # Return extra information that will be stored in the config entry.
    return {"title": f"Zenkeo ({host})", "mac": mac_address}


class ConfigFlow(config_entries.ConfigFlow):
    """Handle a config flow for Atlantic Zenkeo AC."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)

                # Set the unique ID and abort if it already exists
                await self.async_set_unique_id(info["mac"])
                self._abort_if_unique_id_configured()

                # Add the mac to the data that will be stored in the config entry
                data = {**user_input, "mac": info["mac"]}

                return self.async_create_entry(title=info["title"], data=data)

            except CannotConnect as e:
                _LOGGER.error("Connection failed: %s", e)
                errors["base"] = str(e)
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""
