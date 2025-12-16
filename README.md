
# Google Contacts Integration

![maintained](https://img.shields.io/maintenance/yes/2026.svg)
<img alt="GitHub last commit" src="https://img.shields.io/github/last-commit/SirIndubitable/ha-google-contacts">
[![hacs_badge](https://img.shields.io/badge/hacs-custom-yellow.svg)](https://github.com/custom-components/hacs)
[![ha_version](https://img.shields.io/badge/home%20assistant-2025.12.0%2B-green.svg)](https://www.home-assistant.io)
![version](https://img.shields.io/badge/version-0.1.0-yellow.svg)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/mit)

<a href="https://www.buymeacoffee.com/sirindubitable" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-violet.png" alt="Buy Me A Coffee" style="height: 40px !important;width: 145px !important;" ></a>

## Overview
Home Assistant integration for Google Contacts.  Allows creating calendars with significant events tied to your contacts, such as birthdays.

## Disclaimer
This project is not affiliated with or supported by Home Assistant or Google. It is community maintained.


## Installation

You can install this card by following one of the guides below:

### With HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=SirIndubitable&repository=ha-google-contacts&category=integration)


1. Click on the three dots in the top right corner of the HACS overview menu.
2. Select **Custom repositories**.
3. Add the repository URL: `https://github.com/SirIndubitable/ha-google-contacts`.
4. Set the type to **Integration**.
5. Click the **Add** button.
6. Search for **Google Contacts** in HACS and click the **Download** button.

## Configuration

[![Add the integration to my home assistant .](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start?domain=google-contacts)

Google Contacts integration uses configuration subentries for configuring the sensors.
1. Setup the configuration once per user you want contact information from
2. Create one or multiple configuration subentries using the users contacts

### Calendar Subentry
___
The calendar subentry creates a calendar with dates relevant to your contacts (ie. Birthdays and/or Anniversaries)<br/>
This is similar to the builtin google birthdays calendar, but gives a little more flexibility in filtering and how it is displayed

#### Configuration options:
| Option             | Description                                        |
|--------------------|----------------------------------------------------|
| Name               | The name of the entity within Home Assistant |
| Event display name | The contact name used for the calendar event<br/>If the first option doesn't exist (ie. Nickname) then it tries the second option and so on. |
| Contact group      | Also know as tag in Google Contacts<br/>This will filter the calendar to contacts that are in this group/tag |
| Show Year          | If the birthday/anniversary year is shown in the event.  ("Matt's 26th Birthday" vs "Matt's Birthday")
