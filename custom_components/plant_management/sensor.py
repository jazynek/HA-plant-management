"""Sensor entities for Plant Management."""
from __future__ import annotations

from datetime import date
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    SIGNAL_PLANT_ADDED,
    SIGNAL_PLANT_REMOVED,
    SIGNAL_PLANT_UPDATED,
    STATUS_BOTH_DUE,
    STATUS_FERTILIZE_DUE,
    STATUS_OK,
    STATUS_WATER_DUE,
)
from .coordinator import PlantStore

STATUS_ICONS = {
    STATUS_OK: "mdi:flower",
    STATUS_WATER_DUE: "mdi:water-alert",
    STATUS_FERTILIZE_DUE: "mdi:watering-can-alert",
    STATUS_BOTH_DUE: "mdi:alert-decagram",
}


def _device_info(plant_id: str, plant: dict[str, Any]) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, plant_id)},
        name=plant.get("name"),
        manufacturer="Plant Management",
        model=plant.get("species") or "Roślina",
    )


class _PlantBaseEntity(SensorEntity):
    _attr_should_poll = False

    def __init__(self, store: PlantStore, plant_id: str) -> None:
        self._store = store
        self._plant_id = plant_id
        self._attr_device_info = _device_info(plant_id, store.get_plant(plant_id) or {})

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_PLANT_UPDATED, self._handle_signal)
        )
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_PLANT_REMOVED, self._handle_removed)
        )

    @callback
    def _handle_signal(self, plant_id: str) -> None:
        if plant_id == self._plant_id:
            self.async_write_ha_state()

    @callback
    def _handle_removed(self, plant_id: str) -> None:
        if plant_id == self._plant_id:
            self.hass.async_create_task(self.async_remove(force_remove=True))

    @property
    def _plant(self) -> dict[str, Any]:
        return self._store.get_plant(self._plant_id) or {}

    @property
    def available(self) -> bool:
        return self._store.get_plant(self._plant_id) is not None


class PlantStatusSensor(_PlantBaseEntity):
    _attr_translation_key = "plant_status"

    def __init__(self, store: PlantStore, plant_id: str) -> None:
        super().__init__(store, plant_id)
        self._attr_unique_id = f"{DOMAIN}_{plant_id}_status"
        self._attr_name = f"{store.get_plant(plant_id)['name']} status"

    @property
    def native_value(self) -> str:
        return self._store.status(self._plant_id)

    @property
    def icon(self) -> str:
        return STATUS_ICONS.get(self.native_value, "mdi:flower")

    @property
    def entity_picture(self) -> str | None:
        photo = self._plant.get("photo")
        if photo:
            return f"/local/plant_management/{photo}"
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        plant = self._plant
        return {
            "species": plant.get("species"),
            "zone": plant.get("zone"),
            "light_zone": plant.get("light_zone"),
            "watering_interval_days": plant.get("watering_interval_days"),
            "fertilizing_interval_days": plant.get("fertilizing_interval_days"),
            "light_notes": plant.get("light_notes"),
            "watering_notes": plant.get("watering_notes"),
            "fertilizing_notes": plant.get("fertilizing_notes"),
            "care_notes": plant.get("care_notes"),
            "last_watered": plant.get("last_watered"),
            "next_watering": plant.get("next_watering"),
            "last_fertilized": plant.get("last_fertilized"),
            "next_fertilizing": plant.get("next_fertilizing"),
            "last_repotted": plant.get("last_repotted"),
            "trello_url": plant.get("trello_url"),
            "history": plant.get("history", [])[:20],
        }


class _PlantDateSensor(_PlantBaseEntity):
    _attr_device_class = SensorDeviceClass.DATE

    def __init__(self, store: PlantStore, plant_id: str, field: str, name_suffix: str, unique_suffix: str) -> None:
        super().__init__(store, plant_id)
        self._field = field
        self._attr_unique_id = f"{DOMAIN}_{plant_id}_{unique_suffix}"
        self._attr_name = f"{store.get_plant(plant_id)['name']} {name_suffix}"

    @property
    def native_value(self) -> date | None:
        value = self._plant.get(self._field)
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None


class PlantNextWateringSensor(_PlantDateSensor):
    def __init__(self, store: PlantStore, plant_id: str) -> None:
        super().__init__(store, plant_id, "next_watering", "kolejne podlewanie", "next_watering")


class PlantNextFertilizingSensor(_PlantDateSensor):
    def __init__(self, store: PlantStore, plant_id: str) -> None:
        super().__init__(store, plant_id, "next_fertilizing", "kolejne nawożenie", "next_fertilizing")


class PlantLastWateredSensor(_PlantDateSensor):
    def __init__(self, store: PlantStore, plant_id: str) -> None:
        super().__init__(store, plant_id, "last_watered", "ostatnie podlewanie", "last_watered")


class PlantLastFertilizedSensor(_PlantDateSensor):
    def __init__(self, store: PlantStore, plant_id: str) -> None:
        super().__init__(store, plant_id, "last_fertilized", "ostatnie nawożenie", "last_fertilized")


def _entities_for_plant(store: PlantStore, plant_id: str) -> list[SensorEntity]:
    return [
        PlantStatusSensor(store, plant_id),
        PlantNextWateringSensor(store, plant_id),
        PlantNextFertilizingSensor(store, plant_id),
        PlantLastWateredSensor(store, plant_id),
        PlantLastFertilizedSensor(store, plant_id),
    ]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    store: PlantStore = hass.data[DOMAIN][entry.entry_id]["store"]

    async_add_entities(
        [entity for plant_id in store.all_plants() for entity in _entities_for_plant(store, plant_id)]
    )

    @callback
    def _handle_added(plant_id: str) -> None:
        async_add_entities(_entities_for_plant(store, plant_id))

    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_PLANT_ADDED, _handle_added))
