"""The Plant Management integration."""
from __future__ import annotations

import logging
import re
from datetime import datetime, time as dt_time
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_change

from .const import (
    ACTION_SNOOZE_BOTH,
    ACTION_SNOOZE_FERTILIZE,
    ACTION_SNOOZE_WATER,
    ACTION_WATER,
    ACTION_WATER_FERTILIZE,
    ATTR_DAYS,
    ATTR_DEVICE_ID,
    ATTR_NOTE,
    ATTR_PHOTO,
    ATTR_PLANT_ID,
    CONF_CHECK_TIME,
    CONF_NOTIFY_SERVICE,
    DEFAULT_CHECK_TIME,
    DOMAIN,
    EVENT_NOTIFICATION_ACTION,
    PLATFORMS,
    SERVICE_ADD_NOTE,
    SERVICE_ADD_PLANT,
    SERVICE_IMPORT_SEED,
    SERVICE_MARK_FERTILIZED,
    SERVICE_MARK_WATERED,
    SERVICE_MARK_WATERED_AND_FERTILIZED,
    SERVICE_REMOVE_BY_NAME,
    SERVICE_REMOVE_PLANT,
    SERVICE_REPOT,
    SERVICE_SET_PHOTO,
    SERVICE_SNOOZE_FERTILIZING,
    SERVICE_SNOOZE_WATERING,
    SERVICE_UPDATE_PLANT,
    SIGNAL_PLANT_ADDED,
    SIGNAL_PLANT_REMOVED,
    SIGNAL_PLANT_UPDATED,
)
from .coordinator import PlantStore
from .photo_storage import PHOTOS_URL_PATH, async_register_photo_path, async_save_uploaded_photo

_LOGGER = logging.getLogger(__name__)

ACTION_RE = re.compile(
    r"^PM_(WATER_FERTILIZE|WATER|FERTILIZE|SNOOZE_WATER_(\d+)|SNOOZE_FERTILIZE_(\d+)|SNOOZE_BOTH_(\d+))::(?P<plant_id>p_[0-9a-f]+)$"
)

PLANT_FIELDS_SCHEMA = {
    vol.Optional("name"): cv.string,
    vol.Optional("species"): cv.string,
    vol.Optional("zone"): cv.string,
    vol.Optional("light_zone"): cv.string,
    vol.Optional("watering_interval_days"): vol.Coerce(int),
    vol.Optional("fertilizing_interval_days"): vol.Coerce(int),
    vol.Optional("light_notes"): cv.string,
    vol.Optional("watering_notes"): cv.string,
    vol.Optional("fertilizing_notes"): cv.string,
    vol.Optional("care_notes"): cv.string,
    vol.Optional("photo"): cv.string,
    vol.Optional("last_watered"): cv.string,
    vol.Optional("next_watering"): cv.string,
    vol.Optional("last_fertilized"): cv.string,
    vol.Optional("next_fertilizing"): cv.string,
    vol.Optional("last_repotted"): cv.string,
    vol.Optional("trello_url"): cv.string,
}

ADD_PLANT_SCHEMA = vol.Schema({vol.Required("name"): cv.string, **PLANT_FIELDS_SCHEMA})
UPDATE_PLANT_SCHEMA = vol.Schema({vol.Required(ATTR_PLANT_ID): cv.string, **PLANT_FIELDS_SCHEMA})
PLANT_ID_SCHEMA = vol.Schema({vol.Required(ATTR_PLANT_ID): cv.string})
REMOVE_BY_NAME_SCHEMA = vol.Schema({vol.Required("name"): cv.string})
SET_PHOTO_SCHEMA = vol.Schema(
    {vol.Required(ATTR_DEVICE_ID): cv.string, vol.Required(ATTR_PHOTO): cv.string}
)


def _plant_id_from_device(hass: HomeAssistant, device_id: str) -> str | None:
    device = dr.async_get(hass).async_get(device_id)
    if not device:
        return None
    for domain, identifier in device.identifiers:
        if domain == DOMAIN:
            return identifier
    return None
MARK_WATERED_SCHEMA = vol.Schema(
    {vol.Required(ATTR_PLANT_ID): cv.string, vol.Optional(ATTR_NOTE): cv.string}
)
SNOOZE_SCHEMA = vol.Schema(
    {vol.Required(ATTR_PLANT_ID): cv.string, vol.Required(ATTR_DAYS): vol.Coerce(int)}
)
REPOT_SCHEMA = vol.Schema(
    {vol.Required(ATTR_PLANT_ID): cv.string, vol.Optional(ATTR_NOTE): cv.string}
)
ADD_NOTE_SCHEMA = vol.Schema(
    {vol.Required(ATTR_PLANT_ID): cv.string, vol.Required(ATTR_NOTE): cv.string}
)
IMPORT_SEED_SCHEMA = vol.Schema({vol.Required("plants"): vol.All(cv.ensure_list, [dict])})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    domain_data = hass.data.setdefault(DOMAIN, {})

    if not domain_data.get("_photo_path_registered"):
        await async_register_photo_path(hass)
        domain_data["_photo_path_registered"] = True

    store = PlantStore(hass)
    await store.async_load()
    hass.data[DOMAIN][entry.entry_id] = {"store": store}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _async_register_services(hass, store)

    unsub_time = _async_schedule_daily_check(hass, entry, store)
    unsub_event = hass.bus.async_listen(EVENT_NOTIFICATION_ACTION, _make_action_handler(hass, store))
    unsub_options = entry.add_update_listener(_async_reload_schedule)

    hass.data[DOMAIN][entry.entry_id]["unsub_time"] = unsub_time
    hass.data[DOMAIN][entry.entry_id]["unsub_event"] = unsub_event
    hass.data[DOMAIN][entry.entry_id]["unsub_options"] = unsub_options

    return True


async def _async_reload_schedule(hass: HomeAssistant, entry: ConfigEntry) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    if data.get("unsub_time"):
        data["unsub_time"]()
    data["unsub_time"] = _async_schedule_daily_check(hass, entry, data["store"])


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        for key in ("unsub_time", "unsub_event", "unsub_options"):
            if data.get(key):
                data[key]()
    return ok


def _async_schedule_daily_check(hass: HomeAssistant, entry: ConfigEntry, store: PlantStore):
    check_time_str = entry.options.get(CONF_CHECK_TIME, DEFAULT_CHECK_TIME)
    try:
        parsed: dt_time = datetime.strptime(check_time_str, "%H:%M:%S").time()
    except ValueError:
        parsed = datetime.strptime(DEFAULT_CHECK_TIME, "%H:%M:%S").time()

    async def _check(_now: Any) -> None:
        await _async_run_notification_check(hass, entry, store)

    return async_track_time_change(
        hass, _check, hour=parsed.hour, minute=parsed.minute, second=parsed.second
    )


async def _async_run_notification_check(hass: HomeAssistant, entry: ConfigEntry, store: PlantStore) -> None:
    notify_service = entry.options.get(CONF_NOTIFY_SERVICE)
    due = store.plants_due_for_notification()
    if not due:
        return
    if not notify_service:
        _LOGGER.warning(
            "%d plant(s) need attention but no notify_service is configured in options", len(due)
        )
        return

    for plant_id, plant, water_due, fert_due in due:
        actions: list[dict[str, str]] = []
        note_lines = []
        if water_due and plant.get("watering_notes"):
            note_lines.append(f"💧 {plant['watering_notes']}")
        if fert_due and plant.get("fertilizing_notes"):
            note_lines.append(f"🌱 {plant['fertilizing_notes']}")
        message_body = "\n".join(note_lines)

        if water_due and fert_due:
            title = f"🌿 {plant['name']}: podlej i nawieź"
            actions.append({"action": f"PM_{ACTION_WATER}::{plant_id}", "title": "💧 Podlano"})
            actions.append(
                {"action": f"PM_{ACTION_WATER_FERTILIZE}::{plant_id}", "title": "💧🌱 Podlano+Nawóz"}
            )
            for d in (1, 3, 5):
                actions.append(
                    {"action": f"PM_{ACTION_SNOOZE_BOTH}_{d}::{plant_id}", "title": f"⏭ +{d}d"}
                )
        elif water_due:
            title = f"💧 {plant['name']}: czas podlać"
            actions.append({"action": f"PM_{ACTION_WATER}::{plant_id}", "title": "💧 Podlano"})
            actions.append(
                {"action": f"PM_{ACTION_WATER_FERTILIZE}::{plant_id}", "title": "💧🌱 Podlano+Nawóz"}
            )
            for d in (1, 3, 5):
                actions.append(
                    {"action": f"PM_{ACTION_SNOOZE_WATER}_{d}::{plant_id}", "title": f"⏭ +{d}d"}
                )
        else:
            title = f"🌱 {plant['name']}: czas nawieźć"
            actions.append({"action": f"PM_FERTILIZE::{plant_id}", "title": "🌱 Nawiezione"})
            actions.append(
                {"action": f"PM_{ACTION_WATER_FERTILIZE}::{plant_id}", "title": "💧🌱 Podlano+Nawóz"}
            )
            for d in (1, 3, 5):
                actions.append(
                    {"action": f"PM_{ACTION_SNOOZE_FERTILIZE}_{d}::{plant_id}", "title": f"⏭ +{d}d"}
                )

        message = f"{title}\n{message_body}" if message_body else title
        notification_data: dict[str, Any] = {"actions": actions, "tag": f"plant_management_{plant_id}"}
        if plant.get("photo"):
            notification_data["image"] = f"{PHOTOS_URL_PATH}/{plant['photo']}"
        service_data = {"message": message, "data": notification_data}
        try:
            await hass.services.async_call("notify", notify_service, service_data, blocking=True)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Failed to send plant notification for %s", plant_id)
            continue
        store.mark_notified(plant_id, water_due, fert_due)

    await store.async_save()


def _make_action_handler(hass: HomeAssistant, store: PlantStore):
    async def _handler(event: Event) -> None:
        action = event.data.get("action", "")
        match = ACTION_RE.match(action)
        if not match:
            return
        plant_id = match.group("plant_id")
        if plant_id not in store.plants:
            return

        if action.startswith(f"PM_{ACTION_WATER_FERTILIZE}::"):
            store.mark_watered(plant_id, also_fertilize=True)
        elif action.startswith(f"PM_{ACTION_WATER}::"):
            store.mark_watered(plant_id)
        elif action.startswith("PM_FERTILIZE::"):
            store.mark_fertilized(plant_id)
        elif match.group(2):
            store.snooze_watering(plant_id, int(match.group(2)))
        elif match.group(3):
            store.snooze_fertilizing(plant_id, int(match.group(3)))
        elif match.group(4):
            days = int(match.group(4))
            store.snooze_watering(plant_id, days)
            store.snooze_fertilizing(plant_id, days)
        else:
            return

        await store.async_save()
        async_dispatcher_send(hass, SIGNAL_PLANT_UPDATED, plant_id)

    return _handler


def _async_register_services(hass: HomeAssistant, store: PlantStore) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_ADD_PLANT):
        return

    async def _save_and_notify(plant_id: str, signal: str) -> None:
        await store.async_save()
        async_dispatcher_send(hass, signal, plant_id)

    async def add_plant(call: ServiceCall) -> None:
        plant_id = store.add_plant(**call.data)
        await _save_and_notify(plant_id, SIGNAL_PLANT_ADDED)

    async def update_plant(call: ServiceCall) -> None:
        data = dict(call.data)
        plant_id = data.pop(ATTR_PLANT_ID)
        store.update_plant(plant_id, **data)
        await _save_and_notify(plant_id, SIGNAL_PLANT_UPDATED)

    async def remove_plant(call: ServiceCall) -> None:
        plant_id = call.data[ATTR_PLANT_ID]
        store.remove_plant(plant_id)
        await store.async_save()
        async_dispatcher_send(hass, SIGNAL_PLANT_REMOVED, plant_id)

    async def remove_by_name(call: ServiceCall) -> None:
        plant_id = store.remove_by_name(call.data["name"])
        if not plant_id:
            return
        await store.async_save()
        async_dispatcher_send(hass, SIGNAL_PLANT_REMOVED, plant_id)

    async def mark_watered(call: ServiceCall) -> None:
        plant_id = call.data[ATTR_PLANT_ID]
        store.mark_watered(plant_id, note=call.data.get(ATTR_NOTE))
        await _save_and_notify(plant_id, SIGNAL_PLANT_UPDATED)

    async def mark_fertilized(call: ServiceCall) -> None:
        plant_id = call.data[ATTR_PLANT_ID]
        store.mark_fertilized(plant_id, note=call.data.get(ATTR_NOTE))
        await _save_and_notify(plant_id, SIGNAL_PLANT_UPDATED)

    async def mark_watered_and_fertilized(call: ServiceCall) -> None:
        plant_id = call.data[ATTR_PLANT_ID]
        store.mark_watered(plant_id, also_fertilize=True, note=call.data.get(ATTR_NOTE))
        await _save_and_notify(plant_id, SIGNAL_PLANT_UPDATED)

    async def snooze_watering(call: ServiceCall) -> None:
        plant_id = call.data[ATTR_PLANT_ID]
        store.snooze_watering(plant_id, call.data[ATTR_DAYS])
        await _save_and_notify(plant_id, SIGNAL_PLANT_UPDATED)

    async def snooze_fertilizing(call: ServiceCall) -> None:
        plant_id = call.data[ATTR_PLANT_ID]
        store.snooze_fertilizing(plant_id, call.data[ATTR_DAYS])
        await _save_and_notify(plant_id, SIGNAL_PLANT_UPDATED)

    async def repot(call: ServiceCall) -> None:
        plant_id = call.data[ATTR_PLANT_ID]
        store.repot(plant_id, note=call.data.get(ATTR_NOTE))
        await _save_and_notify(plant_id, SIGNAL_PLANT_UPDATED)

    async def add_note(call: ServiceCall) -> None:
        plant_id = call.data[ATTR_PLANT_ID]
        store.add_note(plant_id, call.data[ATTR_NOTE])
        await _save_and_notify(plant_id, SIGNAL_PLANT_UPDATED)

    async def set_photo(call: ServiceCall) -> None:
        plant_id = _plant_id_from_device(hass, call.data[ATTR_DEVICE_ID])
        if not plant_id or not store.get_plant(plant_id):
            _LOGGER.error(
                "set_photo: device_id %s does not match a Plant Management plant",
                call.data[ATTR_DEVICE_ID],
            )
            return
        filename = await async_save_uploaded_photo(hass, plant_id, call.data[ATTR_PHOTO])
        store.set_photo(plant_id, filename)
        await _save_and_notify(plant_id, SIGNAL_PLANT_UPDATED)

    async def import_seed(call: ServiceCall) -> None:
        for plant_fields in call.data["plants"]:
            name = plant_fields.get("name")
            existing_id = store.find_by_name(name) if name else None
            if existing_id:
                store.update_plant(existing_id, **plant_fields)
                async_dispatcher_send(hass, SIGNAL_PLANT_UPDATED, existing_id)
            else:
                plant_id = store.add_plant(**plant_fields)
                async_dispatcher_send(hass, SIGNAL_PLANT_ADDED, plant_id)
        await store.async_save()

    hass.services.async_register(DOMAIN, SERVICE_ADD_PLANT, add_plant, schema=ADD_PLANT_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_UPDATE_PLANT, update_plant, schema=UPDATE_PLANT_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_REMOVE_PLANT, remove_plant, schema=PLANT_ID_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_REMOVE_BY_NAME, remove_by_name, schema=REMOVE_BY_NAME_SCHEMA
    )
    hass.services.async_register(DOMAIN, SERVICE_MARK_WATERED, mark_watered, schema=MARK_WATERED_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_MARK_FERTILIZED, mark_fertilized, schema=MARK_WATERED_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_MARK_WATERED_AND_FERTILIZED,
        mark_watered_and_fertilized,
        schema=MARK_WATERED_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SNOOZE_WATERING, snooze_watering, schema=SNOOZE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SNOOZE_FERTILIZING, snooze_fertilizing, schema=SNOOZE_SCHEMA
    )
    hass.services.async_register(DOMAIN, SERVICE_REPOT, repot, schema=REPOT_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_ADD_NOTE, add_note, schema=ADD_NOTE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SET_PHOTO, set_photo, schema=SET_PHOTO_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_IMPORT_SEED, import_seed, schema=IMPORT_SEED_SCHEMA)
