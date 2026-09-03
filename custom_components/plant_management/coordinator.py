"""Data storage and business logic for Plant Management."""
from __future__ import annotations

import logging
import secrets
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DEFAULT_FERT_INTERVAL_DAYS,
    DEFAULT_WATER_INTERVAL_DAYS,
    HISTORY_MAX_LEN,
    STATUS_BOTH_DUE,
    STATUS_FERTILIZE_DUE,
    STATUS_OK,
    STATUS_WATER_DUE,
    STORAGE_KEY,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)


def _today() -> date:
    return dt_util.now().date()


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


class PlantStore:
    """Holds all plant data, persisted via Home Assistant's Store helper."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.plants: dict[str, dict[str, Any]] = {}

    async def async_load(self) -> None:
        data = await self._store.async_load()
        self.plants = (data or {}).get("plants", {})

    async def async_save(self) -> None:
        await self._store.async_save({"plants": self.plants})

    def all_plants(self) -> dict[str, dict[str, Any]]:
        return self.plants

    def get_plant(self, plant_id: str) -> dict[str, Any] | None:
        return self.plants.get(plant_id)

    def _new_id(self) -> str:
        while True:
            candidate = "p_" + secrets.token_hex(4)
            if candidate not in self.plants:
                return candidate

    def _log(self, plant: dict[str, Any], event_type: str, detail: str | None = None) -> None:
        history: list[dict[str, Any]] = plant.setdefault("history", [])
        history.insert(
            0,
            {
                "date": dt_util.now().isoformat(),
                "type": event_type,
                "detail": detail,
            },
        )
        del history[HISTORY_MAX_LEN:]

    def _recompute_water_due(self, plant: dict[str, Any]) -> None:
        last = _parse_date(plant.get("last_watered"))
        interval = plant.get("watering_interval_days") or DEFAULT_WATER_INTERVAL_DAYS
        if last:
            plant["next_watering"] = _iso(last + timedelta(days=interval))

    def _recompute_fertilize_due(self, plant: dict[str, Any]) -> None:
        last = _parse_date(plant.get("last_fertilized"))
        interval = plant.get("fertilizing_interval_days") or DEFAULT_FERT_INTERVAL_DAYS
        if last:
            plant["next_fertilizing"] = _iso(last + timedelta(days=interval))

    def add_plant(self, **fields: Any) -> str:
        plant_id = self._new_id()
        plant: dict[str, Any] = {
            "id": plant_id,
            "name": fields.get("name") or "Roślina",
            "species": fields.get("species"),
            "zone": fields.get("zone"),
            "light_zone": fields.get("light_zone"),
            "watering_interval_days": fields.get("watering_interval_days") or DEFAULT_WATER_INTERVAL_DAYS,
            "fertilizing_interval_days": fields.get("fertilizing_interval_days") or DEFAULT_FERT_INTERVAL_DAYS,
            "watering_notes": fields.get("watering_notes"),
            "fertilizing_notes": fields.get("fertilizing_notes"),
            "care_notes": fields.get("care_notes"),
            "photo": fields.get("photo"),
            "last_watered": fields.get("last_watered"),
            "next_watering": fields.get("next_watering"),
            "last_fertilized": fields.get("last_fertilized"),
            "next_fertilizing": fields.get("next_fertilizing"),
            "last_repotted": fields.get("last_repotted"),
            "trello_url": fields.get("trello_url"),
            "notified_water_date": None,
            "notified_fertilize_date": None,
            "created_at": dt_util.now().isoformat(),
            "history": [],
        }
        if not plant["next_watering"] and plant["last_watered"]:
            self._recompute_water_due(plant)
        if not plant["next_fertilizing"] and plant["last_fertilized"]:
            self._recompute_fertilize_due(plant)
        self._log(plant, "created")
        self.plants[plant_id] = plant
        return plant_id

    def update_plant(self, plant_id: str, **fields: Any) -> None:
        plant = self.plants.get(plant_id)
        if not plant:
            raise ValueError(f"Unknown plant_id: {plant_id}")
        for key, value in fields.items():
            if value is not None and key in plant:
                plant[key] = value
        self._log(plant, "updated")

    def remove_plant(self, plant_id: str) -> None:
        self.plants.pop(plant_id, None)

    def mark_watered(
        self, plant_id: str, also_fertilize: bool = False, note: str | None = None, when: date | None = None
    ) -> None:
        plant = self.plants.get(plant_id)
        if not plant:
            raise ValueError(f"Unknown plant_id: {plant_id}")
        when = when or _today()
        plant["last_watered"] = _iso(when)
        self._recompute_water_due(plant)
        plant["notified_water_date"] = None
        self._log(plant, "water_fertilize" if also_fertilize else "water", note)
        if also_fertilize:
            plant["last_fertilized"] = _iso(when)
            self._recompute_fertilize_due(plant)
            plant["notified_fertilize_date"] = None

    def mark_fertilized(self, plant_id: str, note: str | None = None, when: date | None = None) -> None:
        plant = self.plants.get(plant_id)
        if not plant:
            raise ValueError(f"Unknown plant_id: {plant_id}")
        when = when or _today()
        plant["last_fertilized"] = _iso(when)
        self._recompute_fertilize_due(plant)
        plant["notified_fertilize_date"] = None
        self._log(plant, "fertilize", note)

    def snooze_watering(self, plant_id: str, days: int) -> None:
        plant = self.plants.get(plant_id)
        if not plant:
            raise ValueError(f"Unknown plant_id: {plant_id}")
        base = _parse_date(plant.get("next_watering")) or _today()
        new_due = max(base, _today()) + timedelta(days=days)
        plant["next_watering"] = _iso(new_due)
        plant["notified_water_date"] = None
        self._log(plant, "snooze_water", f"+{days}d -> {new_due.isoformat()}")

    def snooze_fertilizing(self, plant_id: str, days: int) -> None:
        plant = self.plants.get(plant_id)
        if not plant:
            raise ValueError(f"Unknown plant_id: {plant_id}")
        base = _parse_date(plant.get("next_fertilizing")) or _today()
        new_due = max(base, _today()) + timedelta(days=days)
        plant["next_fertilizing"] = _iso(new_due)
        plant["notified_fertilize_date"] = None
        self._log(plant, "snooze_fertilize", f"+{days}d -> {new_due.isoformat()}")

    def repot(self, plant_id: str, note: str | None = None, when: date | None = None) -> None:
        plant = self.plants.get(plant_id)
        if not plant:
            raise ValueError(f"Unknown plant_id: {plant_id}")
        when = when or _today()
        plant["last_repotted"] = _iso(when)
        self._log(plant, "repot", note)

    def add_note(self, plant_id: str, note: str) -> None:
        plant = self.plants.get(plant_id)
        if not plant:
            raise ValueError(f"Unknown plant_id: {plant_id}")
        self._log(plant, "note", note)

    def set_photo(self, plant_id: str, filename: str) -> None:
        plant = self.plants.get(plant_id)
        if not plant:
            raise ValueError(f"Unknown plant_id: {plant_id}")
        plant["photo"] = filename
        self._log(plant, "photo_updated", filename)

    def status(self, plant_id: str) -> str:
        plant = self.plants.get(plant_id)
        if not plant:
            return STATUS_OK
        today = _today()
        water_due = (nw := _parse_date(plant.get("next_watering"))) is not None and nw <= today
        fert_due = (nf := _parse_date(plant.get("next_fertilizing"))) is not None and nf <= today
        if water_due and fert_due:
            return STATUS_BOTH_DUE
        if water_due:
            return STATUS_WATER_DUE
        if fert_due:
            return STATUS_FERTILIZE_DUE
        return STATUS_OK

    def plants_due_for_notification(self) -> list[tuple[str, dict[str, Any], bool, bool]]:
        """Return (plant_id, plant, water_due_unnotified, fertilize_due_unnotified)."""
        today_iso = _iso(_today())
        results = []
        for plant_id, plant in self.plants.items():
            today = _today()
            nw = _parse_date(plant.get("next_watering"))
            nf = _parse_date(plant.get("next_fertilizing"))
            water_due = nw is not None and nw <= today and plant.get("notified_water_date") != today_iso
            fert_due = nf is not None and nf <= today and plant.get("notified_fertilize_date") != today_iso
            if water_due or fert_due:
                results.append((plant_id, plant, water_due, fert_due))
        return results

    def mark_notified(self, plant_id: str, water: bool, fertilize: bool) -> None:
        plant = self.plants.get(plant_id)
        if not plant:
            return
        today_iso = _iso(_today())
        if water:
            plant["notified_water_date"] = today_iso
        if fertilize:
            plant["notified_fertilize_date"] = today_iso
