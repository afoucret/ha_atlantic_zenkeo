"""The Atlantic Zenkeo AC integration."""
from __future__ import annotations

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Atlantic Zenkeo AC from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    # TODO: Store an API object for your platforms to access
    # hass.data[DOMAIN][entry.entry_id] = ...

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
