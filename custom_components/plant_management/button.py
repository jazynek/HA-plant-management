"""Button entities for Plant Management."""
from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SIGNAL_PLANT_ADDED, SIGNAL_PLANT_REMOVED, SIGNAL_PLANT_UPDATED
from .coordinator import PlantStore


def _device_info(plant_id: str, plant: dict[str, Any]) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, plant_id)},
        name=plant.get("name"),
        manufacturer="Plant Management",
        model=plant.get("species") or "Roślina",
    )


class _PlantButtonBase(ButtonEntity):
    _attr_should_poll = False

    def __init__(self, store: PlantStore, plant_id: str, name_suffix: str, unique_suffix: str, icon: str) -> None:
        self._store = store
        self._plant_id = plant_id
        self._attr_device_info = _device_info(plant_id, store.get_plant(plant_id) or {})
        self._attr_unique_id = f"{DOMAIN}_{plant_id}_{unique_suffix}"
        self._attr_name = f"{store.get_plant(plant_id)['name']} {name_suffix}"
        self._attr_icon = icon

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_PLANT_REMOVED, self._handle_removed)
        )

    @callback
    def _handle_removed(self, plant_id: str) -> None:
        if plant_id == self._plant_id:
            self.hass.async_create_task(self.async_remove(force_remove=True))

    @property
    def available(self) -> bool:
        return self._store.get_plant(self._plant_id) is not None

    async def _finish(self) -> None:
        await self._store.async_save()
        async_dispatcher_send(self.hass, SIGNAL_PLANT_UPDATED, self._plant_id)


class PlantWateredButton(_PlantButtonBase):
    def __init__(self, store: PlantStore, plant_id: str) -> None:
        super().__init__(store, plant_id, "Podlano", "mark_watered", "mdi:watering-can")

    async def async_press(self) -> None:
        self._store.mark_watered(self._plant_id)
        await self._finish()


class PlantWateredFertilizedButton(_PlantButtonBase):
    def __init__(self, store: PlantStore, plant_id: str) -> None:
        super().__init__(store, plant_id, "Podlano + Nawóz", "mark_watered_fertilized", "mdi:watering-can-outline")

    async def async_press(self) -> None:
        self._store.mark_watered(self._plant_id, also_fertilize=True)
        await self._finish()


def _entities_for_plant(store: PlantStore, plant_id: str) -> list[ButtonEntity]:
    return [
        PlantWateredButton(store, plant_id),
        PlantWateredFertilizedButton(store, plant_id),
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
