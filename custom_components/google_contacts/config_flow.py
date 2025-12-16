"""Config flow for Google Contacts."""

from collections.abc import Mapping
import logging
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import HttpRequest

from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigEntry,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_ACCESS_TOKEN, CONF_NAME, CONF_TOKEN, Platform
from homeassistant.core import callback
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.helpers.entity import async_generate_entity_id

from .const import DOMAIN, LOGGER_NAME, OAUTH2_SCOPES
from .schema import OPTIONS_SCHEMA as CONFIG_SCHEMA

ENTITY_ID_FORMAT = Platform.CALENDAR + ".{}"


class OAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN
):
    """Config flow to handle Google Contacts OAuth2 authentication."""

    DOMAIN = DOMAIN

    @property
    def logger(self) -> logging.Logger:
        """Return logger."""
        return logging.getLogger(LOGGER_NAME)

    @property
    def extra_authorize_data(self) -> dict[str, Any]:
        """Extra data that needs to be appended to the authorize url."""
        return {
            "scope": " ".join(OAUTH2_SCOPES),
            # Add params to ensure we get back a refresh token
            "access_type": "offline",
            "prompt": "consent",
        }

    async def async_oauth_create_entry(self, data: dict[str, Any]) -> ConfigFlowResult:
        """Create an entry for the flow."""
        credentials = Credentials(token=data[CONF_TOKEN][CONF_ACCESS_TOKEN])
        try:
            user_resource = build(
                "oauth2",
                "v2",
                credentials=credentials,
            )
            user_resource_cmd: HttpRequest = user_resource.userinfo().get()
            user_resource_info = await self.hass.async_add_executor_job(
                user_resource_cmd.execute
            )

            contacts_resource = build(
                "people",
                "v1",
                credentials=credentials,
            )
            contacts_resource_cmd: HttpRequest = (
                contacts_resource.people()
                .connections()
                .list(resourceName="people/me", personFields="names")
            )
            await self.hass.async_add_executor_job(contacts_resource_cmd.execute)

        except HttpError as ex:
            error = ex.reason
            self.logger.error("HTTP error during OAuth flow: %s", error)
            return self.async_abort(
                reason="access_not_configured",
                description_placeholders={"message": error},
            )
        except Exception:
            self.logger.exception("Unknown error occurred")
            return self.async_abort(reason="unknown")

        user_id = user_resource_info["id"]
        await self.async_set_unique_id(user_id)

        if self.source != SOURCE_REAUTH:
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"{user_resource_info["name"]} Contacts",
                data=data,
            )

        reauth_entry = self._get_reauth_entry()
        if reauth_entry.unique_id:
            self._abort_if_unique_id_mismatch(reason="wrong_account")

        return self.async_update_reload_and_abort(
            reauth_entry, unique_id=user_id, data=data
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Perform reauth upon an API authentication error."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm reauth dialog."""
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")
        return await self.async_step_user()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentries supported by this integration."""
        return {"calendar": CalendarSubentryFlowHandler}


class CalendarSubentryFlowHandler(ConfigSubentryFlow):
    """Handle subentry flow for adding and modifying a location."""

    options: dict[str, Any]

    @property
    def _is_new(self) -> bool:
        """Return if this is a new subentry."""
        return self.source == "user"

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """User flow to modify a new configuration."""
        self.options = {}
        return await self.async_step_configure()

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """User flow to modify an existing configuration."""
        self.options = self._get_reconfigure_subentry().data.copy()
        return await self.async_step_configure()

    async def async_step_configure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Set initial options."""
        if user_input is not None:
            self.options.update(user_input)
            return await self._create_the_thing()

        schema = self.add_suggested_values_to_schema(CONFIG_SCHEMA, self.options)
        return self.async_show_form(
            step_id="configure",
            data_schema=schema,
        )

    async def _create_the_thing(self) -> SubentryFlowResult:
        """Finish config flow."""
        self.options["entity_id"] = self.options.get(
            "entity_id"
        ) or async_generate_entity_id(
            ENTITY_ID_FORMAT, self.options.get(CONF_NAME), hass=self.hass
        )
        if self._is_new:
            return self.async_create_entry(
                title=self.options[CONF_NAME], data=self.options
            )

        return self.async_update_and_abort(
            self._get_entry(),
            self._get_reconfigure_subentry(),
            data=self.options,
        )
