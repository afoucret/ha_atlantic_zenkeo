"""Climate platform for Atlantic Zenkeo AC."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .pyzenkeo import FanSpeed, ZenkeoAC, Mode

_LOGGER = logging.getLogger(__name__)

# Map Home Assistant HVAC modes to the modes of the AC unit
HA_TO_AC_MODE = {
    HVACMode.COOL: Mode.COOL,
    HVACMode.HEAT: Mode.HEAT,
    HVACMode.FAN_ONLY: Mode.FAN,
    HVACMode.DRY: Mode.DRY,
    HVACMode.OFF: None,  # Off is handled by the power state
}
AC_TO_HA_MODE = {v: k for k, v in HA_TO_AC_MODE.items() if v is not None}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the climate platform."""
    # Get the host and mac from the config entry
    host = entry.data["host"]
    mac = entry.data["mac"]

    # Create the API client
    api = ZenkeoAC(host, mac)

    # Create the climate entity
    climate_entity = ZenkeoClimate(api, f"Zenkeo AC ({host})")

    async_add_entities([climate_entity])


class ZenkeoClimate(ClimateEntity):
    """Representation of an Atlantic Zenkeo AC unit."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 16
    _attr_max_temp = 30
    _attr_hvac_modes = [
        HVACMode.OFF,
        HVACMode.COOL,
        HVACMode.HEAT,
        HVACMode.FAN_ONLY,
        HVACMode.DRY,
    ]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE
    )
    _attr_fan_modes = [f.name for f in FanSpeed]

    def __init__(self, api: ZenkeoAC, unique_id: str) -> None:
        """Initialize the climate entity."""
        self._api = api
        self._attr_unique_id = unique_id
        self._attr_target_temperature = 21
        self._attr_current_temperature = 21
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_previous_hvac_mode = HVACMode.COOL
        self._attr_fan_mode = FanSpeed.AUTO.name

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added."""
        await super().async_added_to_hass()
        await self.async_update()

    async def async_update(self) -> None:
        """Update the state of the entity."""
        state = await self._api.get_state()
        if state:
            self._update_state(state)
        else:
            _LOGGER.warning("Could not retrieve state from AC unit")

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            self._attr_target_temperature = int(temperature)
            await self._send_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        self._attr_hvac_mode = hvac_mode
        if hvac_mode != HVACMode.OFF:
            self._attr_previous_hvac_mode = hvac_mode
        await self._send_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new target fan mode."""
        self._attr_fan_mode = fan_mode
        await self._send_state()

    async def async_turn_on(self) -> None:
        """Turn the entity on."""
        self._attr_hvac_mode = HVACMode.COOL
        await self._send_state()

    async def async_turn_off(self) -> None:
        """Turn the entity off."""
        self.async_set_hvac_mode(HVACMode.OFF)
        await self._send_state()

    async def _send_state(self) -> None:
        """Send the current state to the AC unit."""
        if self._attr_hvac_mode == HVACMode.OFF:
            state = await self._api.set_state(
                power=False,
                mode=HA_TO_AC_MODE[self._attr_previous_hvac_mode],
                fan_speed=FanSpeed[self._attr_fan_mode],
                target_temp=self._attr_target_temperature,
            )
            self._update_state(state)
        else:
            state = await self._api.set_state(
                power=True,
                mode=HA_TO_AC_MODE[self._attr_hvac_mode],
                fan_speed=FanSpeed[self._attr_fan_mode],
                target_temp=self._attr_target_temperature,
            )
            self._update_state(state)

    def _update_state(self, state):
        self._attr_current_temperature = state.current_temperature
        self._attr_target_temperature = state.target_temperature
        self._attr_fan_mode = state.fan_speed.name
        if state.power:
            self._attr_hvac_mode = AC_TO_HA_MODE.get(state.mode)
            self._attr_previous_hvac_mode = self._attr_hvac_mode
        else:
            self._attr_hvac_mode = HVACMode.OFF
