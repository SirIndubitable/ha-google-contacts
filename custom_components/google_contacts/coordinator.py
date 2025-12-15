"""Coordinator for fetching data from Google Contacts API."""

import asyncio
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from datetime import date, timedelta
import logging
from typing import Any, Final

from homeassistant.components.calendar import CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import (
    Contact,
    ContactGroup,
    ContactsResponse,
    Event,
    GoogleContactsApi,
    GoogleContactsApiError,
    GroupsResponse,
)
from .const import DOMAIN
from .schema import Options

type GoogleContactsConfigEntry = ConfigEntry[ContactsUpdateCoordinator]

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL: Final = timedelta(minutes=30)
TIMEOUT = 10
STORAGE_VERSION = 1


def ordinal(n: int):
    """Convert an integer into its ordinal representation."""
    # Source - https://stackoverflow.com/a
    # Posted by Ben Davis, modified by community. See post 'Timeline' for change history
    # Retrieved 2025-11-24, License - CC BY-SA 4.0
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = ["th", "st", "nd", "rd", "th"][min(n % 10, 4)]  # codespell:ignore nd
    return str(n) + suffix


class ContactEvent:
    """Representation of a Contact Event."""

    names: dict[str, str]
    year: int
    month: int
    day: int
    type: str
    contact_groups: list[str]

    def __init__(self, contact: Contact, event: Event) -> None:
        """Initialize ContactEvent."""
        self.names = contact.names

        self.year = event.date.year
        self.month = event.date.month
        self.day = event.date.day

        self.type = event.type
        self.contact_groups = contact.memberships.copy()

    def to_attrs(self) -> dict[str, Any]:
        """Return attributes dictionary."""
        date_str = f"{self.month}/{self.day}"
        if self.year != 0:
            date_str = f"{self.year}/{date_str}"
        return {
            "name": self.names.get("displayName", "Unknown"),
            "type": self.type,
            "daye": date_str,
        }

    def next_date(self, now: date) -> date:
        """Return the next occurrence date."""
        event_date = date(
            now.year,
            self.month,
            self.day,
        )

        # If the event has already occurred this year, set it for next year
        if event_date < now:
            event_date = date(
                event_date.year + 1,
                event_date.month,
                event_date.day,
            )

        return event_date

    def to_calendar_event(self, options: Options, now: date) -> CalendarEvent:
        """Convert to CalendarEvent."""
        event_date = self.next_date(now)

        for key in options.display_names:
            name = self.names.get(key)
            if name is not None:
                break

        if options.show_year and self.year != 0:
            anniversery_age = event_date.year - self.year
            summary = f"{name}'s {ordinal(anniversery_age)} {self.type}"
        else:
            summary = f"{name}'s {self.type}"

        return CalendarEvent(
            start=event_date,
            end=event_date + timedelta(days=1),
            summary=summary,
        )

    def sort_key(self, now: date) -> tuple[date, str, str]:
        """Return a tuple to use as a sort key."""
        return (
            self.next_date(now),
            self.type,
            self.names.get("displayName", "Unknown"),
        )


class DataContextManager:
    """Class to write data to storage."""

    data_updated: bool = False

    def __init__(self, store: "ContactsStore") -> None:
        """Initialize DataContextManager."""
        self.store = store
        assert self.store._contacts is not None  # noqa: SLF001

    @property
    def _contacts(self) -> ContactsResponse:
        """Return the contacts response."""
        return self.store._contacts  # type: ignore  # noqa: PGH003, SLF001

    @property
    def _groups(self) -> GroupsResponse:
        """Return the contacts response."""
        return self.store._groups  # type: ignore  # noqa: PGH003, SLF001

    @property
    def contacts_sync_token(self) -> str | None:
        """Return the sync token."""
        return self._contacts.sync_token

    @contacts_sync_token.setter
    def contacts_sync_token(self, value: str | None) -> None:
        """Set the sync token."""
        if self.contacts_sync_token == value:
            return
        self.data_updated = True
        self._contacts.sync_token = value

    @property
    def groups_sync_token(self) -> str | None:
        """Return the sync token."""
        return self._groups.sync_token

    @groups_sync_token.setter
    def groups_sync_token(self, value: str | None) -> None:
        """Set the sync token."""
        if self.groups_sync_token == value:
            return
        self.data_updated = True
        self._groups.sync_token = value

    @property
    def all_contacts(self) -> Sequence[Contact]:
        """Return all contacts."""
        return list(self._contacts.contacts.values())

    @property
    def all_groups(self) -> Sequence[ContactGroup]:
        """Return all contacts."""
        return list(self._groups.groups.values())

    def replace(self, data: ContactsResponse | GroupsResponse) -> None:
        """Replace all contacts."""
        self.data_updated = True
        if isinstance(data, ContactsResponse):
            self.store._contacts = data  # type: ignore  # noqa: PGH003, SLF001
        elif isinstance(data, GroupsResponse):
            self.store._groups = data  # type: ignore  # noqa: PGH003, SLF001
        else:
            raise TypeError("Invalid data type")

    def get_contact(self, resource_name: str) -> Contact | None:
        """Return a contact by resource name."""
        return self._contacts.contacts.get(resource_name)

    def get_group(self, resource_name: str) -> ContactGroup | None:
        """Return a contact by resource name."""
        return self._groups.groups.get(resource_name)

    def add_or_update(self, data: Contact | ContactGroup) -> None:
        """Add or update a contact."""
        self.data_updated = True
        if isinstance(data, Contact):
            self._contacts.contacts[data.resource_name] = data
        elif isinstance(data, ContactGroup):
            self._groups.groups[data.resource_name] = data
        else:
            raise TypeError("Invalid data type")

    def remove_contact(self, resource_name: str) -> None:
        """Remove a contact by resource name."""
        if resource_name not in self._contacts.contacts:
            return
        self.data_updated = True
        del self._contacts.contacts[resource_name]

    def remove_group(self, resource_name: str) -> None:
        """Remove a contact by resource name."""
        if resource_name not in self._groups.groups:
            return
        self.data_updated = True
        del self._groups.groups[resource_name]

    async def __aenter__(self) -> "DataContextManager":
        """Enter context manager."""
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        """Exit context manager."""
        if self.data_updated:
            await self.store._async_save_contacts()  # noqa: SLF001


class ContactsStore(Store[dict[str, Any]]):
    """Store for Google Contacts data."""

    _contacts: ContactsResponse | None = None
    _groups: GroupsResponse | None = None

    async def _async_load_contacts(self) -> None:
        """Load contacts data from storage."""
        if self._contacts is not None:
            return

        data = await self.async_load()
        if data is None:
            data = {}

        self._groups = GroupsResponse.from_dict(data.get("groups", {}))
        self._contacts = ContactsResponse.from_dict(data.get("contacts", {}))

    async def _async_save_contacts(self) -> None:
        """Save contacts data to storage."""
        if self._contacts is None:
            return

        await self.async_save(
            {
                "groups": self._groups,
                "contacts": self._contacts,
            }
        )

    @asynccontextmanager
    async def async_data_access(self) -> AsyncGenerator[DataContextManager]:
        """Return data to write to storage."""
        await self._async_load_contacts()
        async with DataContextManager(self) as context:
            yield context


class ContactsUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for fetching Google Contacts for a Contacts List form the API."""

    config_entry: GoogleContactsConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: GoogleContactsConfigEntry,
        api: GoogleContactsApi,
    ) -> None:
        """Initialize ContactsUpdateCoordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name="Google Contacts",
            update_interval=UPDATE_INTERVAL,
        )
        self.api: GoogleContactsApi = api
        self._store: ContactsStore = ContactsStore(
            hass, STORAGE_VERSION, f"{DOMAIN}/{config_entry.entry_id}"
        )

    @property
    def groups(self) -> list[ContactGroup]:
        """Return the groups response."""
        return self.data.get("groups", [])

    @property
    def contacts(self) -> list[ContactEvent]:
        """Return the groups response."""
        return self.data.get("contacts", [])

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch contacts from API endpoint."""
        store: DataContextManager
        contacts: Sequence[Contact]
        groups: Sequence[ContactGroup]
        async with self._store.async_data_access() as store:
            if not store.contacts_sync_token:
                await self._async_request_get_contacts(store)
            else:
                await self._async_request_synchronize_contacts(store)

            contacts = store.all_contacts

            if not store.groups_sync_token:
                await self._async_request_get_groups(store)
            else:
                await self._async_request_synchronize_groups(store)

            groups = store.all_groups

        return {
            "groups": list(groups),
            "contacts": [
                ContactEvent(contact, event)
                for contact in contacts
                for event in contact.events
            ],
        }

    async def _async_request_get_contacts(self, store: DataContextManager):
        """Initial data request to populate store."""
        _LOGGER.info("Synchronizing contacts (Full): %s", self.config_entry.entry_id)
        contacts: ContactsResponse
        async with asyncio.timeout(TIMEOUT):
            contacts = await self.api.list_contacts()

        store.replace(contacts)

    async def _async_request_synchronize_contacts(
        self, store: DataContextManager
    ) -> None:
        """Initial data request to populate store."""
        _LOGGER.info("Synchronizing contacts (Delta): %s", self.config_entry.entry_id)
        contacts: ContactsResponse
        try:
            async with asyncio.timeout(TIMEOUT):
                contacts = await self.api.list_contacts(store.contacts_sync_token)

        except GoogleContactsApiError as error:
            # TODO figure out if we can catch only "EXPIRED_SYNC_TOKEN"
            _LOGGER.error(
                "Error synchronizing contacts: %s. Performing full resync",
                error,
            )
            await self._async_request_get_contacts(store)
            return

        for contact in contacts.contacts.values():
            if contact.deleted:
                _LOGGER.info("Removing contact: %s", contact.resource_name)
                store.remove_contact(contact.resource_name)
            else:
                _LOGGER.info("Updating contact: %s", contact.resource_name)
                store.add_or_update(contact)

        store.contacts_sync_token = contacts.sync_token

    async def _async_request_get_groups(self, store: DataContextManager):
        """Initial data request to populate store."""
        _LOGGER.info("Synchronizing groups (Full): %s", self.config_entry.entry_id)
        groups: GroupsResponse
        async with asyncio.timeout(TIMEOUT):
            groups = await self.api.list_groups()

        store.replace(groups)

    async def _async_request_synchronize_groups(
        self, store: DataContextManager
    ) -> None:
        """Initial data request to populate store."""
        _LOGGER.info("Synchronizing groups (Delta): %s", self.config_entry.entry_id)
        groups: GroupsResponse
        try:
            async with asyncio.timeout(TIMEOUT):
                groups = await self.api.list_groups(store.groups_sync_token)

        except GoogleContactsApiError as error:
            # TODO figure out if we can catch only "EXPIRED_SYNC_TOKEN"
            _LOGGER.error(
                "Error synchronizing groups: %s. Performing full resync",
                error,
            )
            await self._async_request_get_groups(store)
            return

        for group in groups.groups.values():
            if group.deleted:
                _LOGGER.info("Removing group: %s", group.resource_name)
                store.remove_group(group.resource_name)
            else:
                _LOGGER.info("Updating group: %s", group.resource_name)
                store.add_or_update(group)

        store.groups_sync_token = groups.sync_token
