"""Constants for the google-contacts integration."""

DOMAIN = "google_contacts"

OAUTH2_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
OAUTH2_TOKEN = "https://oauth2.googleapis.com/token"
OAUTH2_SCOPES = [
    "https://www.googleapis.com/auth/contacts.readonly",
    "https://www.googleapis.com/auth/userinfo.profile",
]

LOGGER_NAME = DOMAIN
