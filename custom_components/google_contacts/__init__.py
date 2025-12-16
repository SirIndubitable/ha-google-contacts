"""The google-contacts integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.config_entry_oauth2_flow import (
    ImplementationUnavailableError,
    OAuth2Session,
    async_get_config_entry_implementation,
)

from .api import GoogleContactsApi
from .coordinator import ContactsUpdateCoordinator, GoogleContactsConfigEntry

_PLATFORMS: list[Platform] = [Platform.CALENDAR]


async def async_setup_entry(
    hass: HomeAssistant, entry: GoogleContactsConfigEntry
) -> bool:
    """Set up google-contacts from a config entry."""
    api = await _create_api_auth(hass, entry)
    coordinator = ContactsUpdateCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    entry.async_on_unload(entry.add_update_listener(options_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: GoogleContactsConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)


async def _create_api_auth(
    hass: HomeAssistant, config_entry: GoogleContactsConfigEntry
) -> GoogleContactsApi:
    """Create API auth object."""
    try:
        implementation = await async_get_config_entry_implementation(hass, config_entry)
    except ImplementationUnavailableError as err:
        raise ConfigEntryNotReady(
            "OAuth2 implementation temporarily unavailable, will retry"
        ) from err

    session = OAuth2Session(hass, config_entry, implementation)
    return GoogleContactsApi(hass, session)


async def options_update_listener(
    hass: HomeAssistant, entry: GoogleContactsConfigEntry
):
    """Handle config update."""
    await hass.config_entries.async_reload(entry.entry_id)
