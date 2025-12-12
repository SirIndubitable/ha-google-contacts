"""Schema and config options for Google Contacts Calendar."""

from enum import StrEnum
from types import MappingProxyType
from typing import Any

# from stringcase import camelcase
import voluptuous as vol

from homeassistant.const import CONF_ENTITY_ID, CONF_NAME
from homeassistant.helpers import selector
import homeassistant.helpers.config_validation as cv

CONF_EVENT_DISPLAY_NAME = "event_display_name"
CONF_GROUP = "group"
CONF_SHOW_YEAR = "show_year"


# Display name options taken from a combination of:
# - https://developers.google.com/people/api/rest/v1/people#name
# - https://developers.google.com/people/api/rest/v1/people#Person.Nickname
class DisplayNameOption(StrEnum):
    """Display name option."""

    # Name types
    DISPLAY_NAME = "displayName"
    DISPLAY_NAME_LAST_FIRST = "displayNameLastFirst"
    GIVEN_NAME = "givenName"

    # Nickname
    NICKNAME = "nickname"


DEFAULT_DISPLAY_NAME = [
    {"key": DisplayNameOption.NICKNAME},
    {"key": DisplayNameOption.DISPLAY_NAME},
]

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Optional(
            CONF_EVENT_DISPLAY_NAME, default=DEFAULT_DISPLAY_NAME
        ): selector.ObjectSelector(
            selector.ObjectSelectorConfig(
                fields={
                    "key": selector.ObjectSelectorField(
                        label="Name Type",
                        required=False,
                        selector={
                            "select": {
                                "options": [
                                    option.value for option in DisplayNameOption
                                ]
                            }
                        },
                    )
                },
                multiple=True,
            )
        ),
        vol.Optional(CONF_SHOW_YEAR, default=True): cv.boolean,
        vol.Optional(CONF_GROUP, default=""): cv.string,
    }
)


class Options:
    """Options for Google Contacts Calendar."""

    _options: MappingProxyType[str, Any]
    _group: str | None = None

    def __init__(self, options: MappingProxyType[str, Any]) -> None:
        """Initialize Options."""
        self._options = options

    @property
    def name(self) -> str:
        """Return name option."""
        return self._options[CONF_NAME]

    @property
    def entity_id(self) -> str:
        """Return entity_id option. This is not user configuratble."""
        return self._options[CONF_ENTITY_ID]

    @property
    def group(self) -> str:
        """Return group option."""
        return self._options.get(CONF_GROUP, "")

    @property
    def show_year(self) -> str:
        """Return show_year option."""
        return self._options.get(CONF_SHOW_YEAR, True)

    @property
    def display_names(self) -> list[str]:
        """Return display_name option."""
        display_name_option = self._options.get(
            CONF_EVENT_DISPLAY_NAME, DEFAULT_DISPLAY_NAME
        )
        return [item["key"] for item in display_name_option]
