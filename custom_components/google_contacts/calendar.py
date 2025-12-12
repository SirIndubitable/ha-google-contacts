"""Google Contacts todo platform."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from operator import methodcaller

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .coordinator import (
    ContactEvent,
    ContactsUpdateCoordinator,
    GoogleContactsConfigEntry,
)
from .schema import Options

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: GoogleContactsConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Google Contacts platform."""

    for subentry in config_entry.subentries.values():
        async_add_entities(
            [GoogleContactsCalendarEntity(config_entry.runtime_data, subentry)],
            config_subentry_id=subentry.subentry_id,
        )


class GoogleContactsCalendarEntity(
    CoordinatorEntity[ContactsUpdateCoordinator], CalendarEntity
):
    """Calendar representation of Google Contacts."""

    _attr_has_entity_name = True
    _attr_supported_features = 0
    _options: Options

    def __init__(
        self,
        coordinator: ContactsUpdateCoordinator,
        config_entry: ConfigSubentry,
    ) -> None:
        """Initialize object."""
        super().__init__(coordinator)
        self._options = Options(config_entry.data)
        self._attr_name = self._options.name
        self._attr_unique_id = config_entry.subentry_id
        self.entity_id = self._options.entity_id

    @property
    def event(self) -> CalendarEvent | None:
        """Return the next upcoming event."""
        data = self._contact_events

        if len(data) == 0:
            return None

        today = dt_util.now().date()
        data = _order_events(data, today)

        return data[0].to_calendar_event(self._options, today)

    @property
    def _contact_events(self) -> list[ContactEvent]:
        """Return contact events filtered by group."""
        group_resource_name: str | None = None
        if self._options.group:
            lower_name = self._options.group.lower()
            possible_resource_name = f"contactGroups/{self._options.group}"
            match_group = next(
                (
                    x
                    for x in self.coordinator.groups
                    if x.resource_name == possible_resource_name
                    or x.name.lower() == lower_name
                ),
                None,
            )
            if match_group:
                group_resource_name = match_group.resource_name
            else:
                return []

        else:
            group_resource_name = "contactGroups/myContacts"

        return [
            d
            for d in self.coordinator.contacts
            if group_resource_name in d.contact_groups
        ]

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        data = self._contact_events
        events: list[CalendarEvent] = []

        cur_start_date = start_date
        while end_date > cur_start_date:
            cur_end_date = min(cur_start_date + timedelta(days=365), end_date)
            events += await self._async_get_events(data, cur_start_date, cur_end_date)
            cur_start_date = cur_end_date

        return events

    async def _async_get_events(
        self,
        data: list[ContactEvent],
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range."""
        events = [
            event.to_calendar_event(self._options, start_date.date()) for event in data
        ]
        return [
            event
            for event in events
            if start_date.date() <= event.start <= end_date.date()
        ]

    @property
    def extra_state_attributes(self):
        """Return the state attributes of the sensor."""
        data = self._contact_events
        return {"contacts": [s.to_attrs() for s in data]}


def _order_events(events: list[ContactEvent], now: date) -> list[ContactEvent]:
    """Order the events response.

    All events have a date attribute. Sort by the next occurrence of the event.
    """
    events.sort(key=methodcaller("sort_key", now))
    return events
