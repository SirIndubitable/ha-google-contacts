"""API for google-contacts bound to Home Assistant OAuth."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum
from functools import partial
from typing import Any, Final, Generic, TypeVar

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError
from googleapiclient.http import BatchHttpRequest, HttpRequest
from httplib2 import ServerNotFoundError

from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_entry_oauth2_flow

from .schema import DisplayNameOption


class GoogleContactsApiError(HomeAssistantError):
    """Error talking to the Google Contacts API."""


class PersonFields(StrEnum):
    """Person fields for Google Contacts API."""

    METADATA = "metadata"
    NAMES = "names"
    NICKNAMES = "nicknames"
    BIRTHDAYS = "birthdays"
    EVENTS = "events"
    RELATIONS = "relations"
    MEMBERSHIPS = "memberships"


class GroupFields(StrEnum):
    """Group fields for Google Contacts API."""

    METADATA = "metadata"
    NAME = "name"


@dataclass
class Date:
    """Date object from Google Contacts API."""

    year: int
    month: int
    day: int

    @classmethod
    def from_dict(cls, dict: dict[str, Any]) -> "Date":
        """Initialize Date."""
        return cls(
            dict.get("year", 0),
            dict.get("month", 0),
            dict.get("day", 0),
        )

    @classmethod
    def from_api(cls, response: dict[str, Any]) -> "Date":
        """Create Date."""
        return cls(
            response.get("year", 0),
            response.get("month", 0),
            response.get("day", 0),
        )


@dataclass
class Event:
    """Event object from Google Contacts API."""

    date: Date
    type: str

    @classmethod
    def from_dict(cls, dict: dict[str, Any]) -> "Event":
        """Initialize Event."""
        return cls(
            Date.from_dict(dict.get("date", {})),
            dict.get("type", ""),
        )

    @classmethod
    def from_api(cls, response: dict[str, Any], type: str | None = None) -> "Event":
        """Create Event."""
        return cls(
            Date.from_api(response.get("date", {})),
            type if type is not None else response.get("formattedType", "Other"),
        )


@dataclass
class Relation:
    """Relation object from Google Contacts API."""

    person: str
    type: str

    @classmethod
    def from_dict(cls, dict: dict[str, Any]) -> "Relation":
        """Initialize Relation."""
        return cls(
            dict.get("person", ""),
            dict.get("type", ""),
        )

    @classmethod
    def from_api(cls, response: dict[str, Any]) -> "Relation":
        """Create Relation."""
        return cls(
            response.get("person", ""),
            response.get("type", ""),
        )


@dataclass
class ContactGroup:
    """Contact Group object from Google Contacts API."""

    resource_name: str
    name: str
    deleted: bool

    @classmethod
    def from_dict(cls, dict: dict[str, Any]) -> "ContactGroup":
        """Initialize ContactGroup."""
        return cls(
            dict.get("resource_name", ""),
            dict.get("name", ""),
            dict.get("deleted", False),
        )

    @classmethod
    def from_api(cls, response: dict[str, Any]) -> "ContactGroup":
        """Initialize ContactGroup."""
        return cls(
            response.get("resourceName", ""),
            response.get(GroupFields.NAME, ""),
            response.get(PersonFields.METADATA, {}).get("deleted", False),
        )


@dataclass
class Contact:
    """Contact object from Google Contacts API."""

    names: dict[str, str]
    resource_name: str
    events: list[Event]
    relations: list[Relation]
    memberships: list[str]
    deleted: bool

    @classmethod
    def from_dict(cls, dict: dict[str, Any]) -> "Contact":
        """Initialize Contact."""
        return cls(
            dict.get("names", {}),
            dict.get("resource_name", ""),
            [Event.from_dict(e) for e in dict.get("events", [])],
            [Relation.from_dict(e) for e in dict.get("relations", [])],
            dict.get("memberships", []),
            dict.get("deleted", False),
        )

    @classmethod
    def from_api(cls, response: dict[str, Any]) -> "Contact":
        """Create Contact."""
        names = response.get(PersonFields.NAMES, [{}])[0]
        names.pop(PersonFields.METADATA, None)
        for nickname_data in response.get(PersonFields.NICKNAMES, []):
            nickname = nickname_data.get("value")
            if nickname is None:
                continue
            names[DisplayNameOption.NICKNAME] = nickname

        events = [
            *[
                Event.from_api(b, "Birthday")
                for b in response.get(PersonFields.BIRTHDAYS, [])
            ],
            *[Event.from_api(e) for e in response.get(PersonFields.EVENTS, [])],
        ]
        events = [e for e in events if e.date.month != 0 and e.date.day != 0]

        group_memberships = [
            e.get("contactGroupMembership", None).get("contactGroupResourceName", "")
            for e in response.get(PersonFields.MEMBERSHIPS, [])
            if "contactGroupMembership" in e
        ]

        return cls(
            names,
            response.get("resourceName", ""),
            events,
            [Relation.from_api(r) for r in response.get(PersonFields.RELATIONS, [])],
            group_memberships,
            response.get(PersonFields.METADATA, {}).get("deleted", False),
        )


@dataclass
class GroupsResponse:
    """Groups response from Google Contacts API."""

    sync_token: str | None
    groups: dict[str, ContactGroup]

    @classmethod
    def from_dict(cls, dict: dict[str, Any]) -> "GroupsResponse":
        """Initialize GroupsResponse."""
        return cls(
            dict.get("sync_token"),
            {k: ContactGroup.from_dict(v) for k, v in dict.get("groups", {}).items()},
        )

    @classmethod
    def from_api(
        cls, contact_groups: list[dict[str, Any]], sync_token: str
    ) -> "GroupsResponse":
        """Initialize GroupsResponse."""
        groups = [ContactGroup.from_api(group) for group in contact_groups]

        return cls(
            sync_token,
            {group.resource_name: group for group in groups},
        )


@dataclass
class ContactsResponse:
    """Contact response from Google Contacts API."""

    sync_token: str | None
    contacts: dict[str, Contact]

    @classmethod
    def from_dict(cls, dict: dict[str, Any]) -> "ContactsResponse":
        """Initialize ContactRespose."""
        return cls(
            dict.get("sync_token"),
            {k: Contact.from_dict(v) for k, v in dict.get("contacts", {}).items()},
        )

    @classmethod
    def from_api(
        cls, connections: list[dict[str, Any]], sync_token: str
    ) -> "ContactsResponse":
        """Initialize ContactRespose."""
        contacts = [
            c
            for c in [Contact.from_api(connection) for connection in connections]
            if len(c.events) > 0
        ]

        return cls(
            sync_token,
            {contact.resource_name: contact for contact in contacts},
        )


_DataT = TypeVar("_DataT", default=dict[str, Any])


class PeopleRequestTemplate(ABC, Generic[_DataT]):
    """Template for People API requests."""

    SYNC_TOKEN: Final = "syncToken"
    PAGE_TOKEN: Final = "pageToken"

    NEXT_SYNC_TOKEN: Final = "nextSyncToken"
    NEXT_PAGE_TOKEN: Final = "nextPageToken"

    hass: HomeAssistant
    _resource: Resource | None = None

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize PeopleRequestTemplate."""
        self.hass = hass

    @property
    @abstractmethod
    def resource_key(self) -> str:
        """Return resource key."""

    @abstractmethod
    def create_request_args(self) -> dict[str, Any]:
        """Build the request arguments."""

    @abstractmethod
    def build_request(self, args: dict[str, Any]) -> HttpRequest:
        """Build the request."""

    @abstractmethod
    def build_response(self, data: list[dict[str, Any]], sync_token: str) -> _DataT:
        """Build the response."""

    async def async_initialize(self, token: str) -> None:
        """Initialize PeopleRequestTemplate."""
        self._resource = await self.hass.async_add_executor_job(
            partial(build, "people", "v1", credentials=Credentials(token=token))
        )

    async def async_list(
        self, sync_token: str | None = None, page_token: str | None = None
    ) -> _DataT:
        """List resources."""
        cmd: HttpRequest = await self._build_request(sync_token=sync_token)

        results = await self._execute(cmd)
        items = results.get(self.resource_key, [])
        sync_token = results.get(PeopleRequestTemplate.NEXT_SYNC_TOKEN)

        if page_token := results.get(PeopleRequestTemplate.NEXT_PAGE_TOKEN):
            while page_token:
                cmd = await self._build_request(
                    sync_token=sync_token, page_token=page_token
                )
                next_page = await self._execute(cmd)
                items.extend(next_page.get(self.resource_key, []))
                page_token = next_page.get(PeopleRequestTemplate.NEXT_PAGE_TOKEN)
                sync_token = sync_token or next_page.get(
                    PeopleRequestTemplate.NEXT_SYNC_TOKEN
                )

        return self.build_response(items, sync_token or "")

    async def _build_request(
        self, sync_token: str | None = None, page_token: str | None = None
    ) -> HttpRequest:
        """Build the request."""
        args = self.create_request_args()
        if sync_token:
            args[PeopleRequestTemplate.SYNC_TOKEN] = sync_token

        if page_token:
            args[PeopleRequestTemplate.PAGE_TOKEN] = page_token

        return self.build_request(args)

    async def _execute(self, request: HttpRequest | BatchHttpRequest) -> Any:
        try:
            response = await self.hass.async_add_executor_job(request.execute)
        except HttpError as err:
            raise GoogleContactsApiError(
                f"Google Contacts API responded with: {err.reason or err.status_code})"
            ) from err
        except ServerNotFoundError as err:
            raise GoogleContactsApiError(
                "Google Contacts API responded with: ServerNotFound"
            ) from err

        if not isinstance(response, dict):
            raise GoogleContactsApiError(
                f"Google Contacts API replied with unexpected response: {response}"
            )
        if error := response.get("error"):
            message = error.get("message", "Unknown Error")
            raise GoogleContactsApiError(f"Google Contacts API response: {message}")

        return response


class ContactsRequest(PeopleRequestTemplate[ContactsResponse]):
    """Contacts request for People API."""

    RESOURCE_NAME: Final = "resourceName"
    CONNECTIONS: Final = "connections"
    REQUEST_SYNC_TOKEN: Final = "requestSyncToken"
    FIELDS: Final = "personFields"

    @property
    def resource_key(self) -> str:
        """Return resource key."""
        return ContactsRequest.CONNECTIONS

    def create_request_args(self) -> dict[str, Any]:
        """Build the request arguments."""
        return {
            ContactsRequest.RESOURCE_NAME: "people/me",
            ContactsRequest.REQUEST_SYNC_TOKEN: True,
            ContactsRequest.FIELDS: ",".join(value for value in PersonFields),
        }

    def build_request(self, args: dict[str, Any]) -> HttpRequest:
        """Build the request."""
        assert self._resource is not None
        return (
            self._resource.people()  # pyright: ignore[reportAttributeAccessIssue]
            .connections()
            .list(**args)
        )

    def build_response(
        self, data: list[dict[str, Any]], sync_token: str
    ) -> ContactsResponse:
        """Build the response."""
        return ContactsResponse.from_api(data, sync_token)


class GroupsRequest(PeopleRequestTemplate[GroupsResponse]):
    """Contacts request for People API."""

    CONTACT_GROUPS: Final = "contactGroups"
    FIELDS: Final = "groupFields"

    @property
    def resource_key(self) -> str:
        """Return resource key."""
        return GroupsRequest.CONTACT_GROUPS

    def create_request_args(self) -> dict[str, Any]:
        """Build the request arguments."""
        return {
            GroupsRequest.FIELDS: ",".join(value for value in GroupFields),
        }

    def build_request(self, args: dict[str, Any]) -> HttpRequest:
        """Build the request."""
        assert self._resource is not None
        contactGroups = self._resource.contactGroups()  # pyright: ignore[reportAttributeAccessIssue]

        return contactGroups.list(**args)

    def build_response(
        self, data: list[dict[str, Any]], sync_token: str
    ) -> GroupsResponse:
        """Build the response."""
        return GroupsResponse.from_api(data, sync_token)


class GoogleContactsApi:
    """Provide google-contacts authentication tied to an OAuth2 based config entry."""

    def __init__(
        self,
        hass: HomeAssistant,
        oauth_session: config_entry_oauth2_flow.OAuth2Session,
    ) -> None:
        """Initialize google-contacts auth."""
        self._hass = hass
        self._oauth_session = oauth_session

    async def async_get_access_token(self) -> str:
        """Return a valid access token."""
        await self._oauth_session.async_ensure_token_valid()
        return self._oauth_session.token[CONF_ACCESS_TOKEN]

    async def list_contacts(self, sync_token: str | None = None) -> ContactsResponse:
        """Get all Contacts resources."""
        request = ContactsRequest(self._hass)
        await request.async_initialize(await self.async_get_access_token())
        return await request.async_list(sync_token=sync_token)

    async def list_groups(self, sync_token: str | None = None) -> GroupsResponse:
        """Get all Group resources."""
        request = GroupsRequest(self._hass)
        await request.async_initialize(await self.async_get_access_token())
        return await request.async_list(sync_token=sync_token)
