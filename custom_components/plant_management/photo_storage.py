"""Persistent photo storage for Plant Management, backed by HA's file_upload."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

from homeassistant.components.file_upload import process_uploaded_file
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PHOTOS_URL_PATH = f"/api/{DOMAIN}/photos"


def _photos_dir(hass: HomeAssistant) -> Path:
    return Path(hass.config.path(".storage", f"{DOMAIN}_photos"))


def _ensure_photos_dir(hass: HomeAssistant) -> Path:
    photos_dir = _photos_dir(hass)
    photos_dir.mkdir(parents=True, exist_ok=True)
    return photos_dir


async def async_register_photo_path(hass: HomeAssistant) -> None:
    photos_dir = await hass.async_add_executor_job(_ensure_photos_dir, hass)
    await hass.http.async_register_static_paths(
        [StaticPathConfig(PHOTOS_URL_PATH, str(photos_dir), False)]
    )


def _write_photo(hass: HomeAssistant, plant_id: str, file_id: str) -> str:
    photos_dir = _photos_dir(hass)
    photos_dir.mkdir(parents=True, exist_ok=True)
    with process_uploaded_file(hass, file_id) as path:
        suffix = Path(path).suffix or ".jpg"
        filename = f"{plant_id}{suffix}"
        shutil.copy(path, photos_dir / filename)
    return filename


async def async_save_uploaded_photo(hass: HomeAssistant, plant_id: str, file_id: str) -> str:
    return await hass.async_add_executor_job(_write_photo, hass, plant_id, file_id)
