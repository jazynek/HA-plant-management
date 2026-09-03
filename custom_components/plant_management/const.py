"""Constants for the Plant Management integration."""

DOMAIN = "plant_management"

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_plants"

PLATFORMS = ["sensor", "button"]

CONF_NOTIFY_SERVICE = "notify_service"
CONF_CHECK_TIME = "check_time"

DEFAULT_CHECK_TIME = "08:00:00"
DEFAULT_WATER_INTERVAL_DAYS = 7
DEFAULT_FERT_INTERVAL_DAYS = 30

SIGNAL_PLANT_ADDED = f"{DOMAIN}_plant_added"
SIGNAL_PLANT_REMOVED = f"{DOMAIN}_plant_removed"
SIGNAL_PLANT_UPDATED = f"{DOMAIN}_plant_updated"

STATUS_OK = "ok"
STATUS_WATER_DUE = "water_due"
STATUS_FERTILIZE_DUE = "fertilize_due"
STATUS_BOTH_DUE = "both_due"

HISTORY_MAX_LEN = 100

EVENT_NOTIFICATION_ACTION = "mobile_app_notification_action"

ACTION_WATER = "WATER"
ACTION_WATER_FERTILIZE = "WATER_FERTILIZE"
ACTION_SNOOZE_WATER = "SNOOZE_WATER"
ACTION_SNOOZE_FERTILIZE = "SNOOZE_FERTILIZE"
ACTION_SNOOZE_BOTH = "SNOOZE_BOTH"
SNOOZE_DAYS_CHOICES = (1, 3, 5)

SERVICE_ADD_PLANT = "add_plant"
SERVICE_UPDATE_PLANT = "update_plant"
SERVICE_REMOVE_PLANT = "remove_plant"
SERVICE_REMOVE_BY_NAME = "remove_by_name"
SERVICE_MARK_WATERED = "mark_watered"
SERVICE_MARK_FERTILIZED = "mark_fertilized"
SERVICE_MARK_WATERED_AND_FERTILIZED = "mark_watered_and_fertilized"
SERVICE_SNOOZE_WATERING = "snooze_watering"
SERVICE_SNOOZE_FERTILIZING = "snooze_fertilizing"
SERVICE_REPOT = "repot"
SERVICE_ADD_NOTE = "add_note"
SERVICE_IMPORT_SEED = "import_seed"
SERVICE_SET_PHOTO = "set_photo"

ATTR_PLANT_ID = "plant_id"
ATTR_DAYS = "days"
ATTR_NOTE = "note"
ATTR_DEVICE_ID = "device_id"
ATTR_PHOTO = "photo"
