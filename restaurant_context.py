from db import SessionLocal
from models_saas import Restaurant, RestaurantModule, RestaurantSetting, RestaurantUser

DEFAULT_RESTAURANT_SLUG = "deaca"


def get_restaurant_by_slug(slug: str):
    db = SessionLocal()
    try:
        restaurant = db.query(Restaurant).filter(Restaurant.slug == slug).first()
        return restaurant
    finally:
        db.close()


def get_default_restaurant():
    return get_restaurant_by_slug(DEFAULT_RESTAURANT_SLUG)

def get_restaurant_setting(db, restaurant_id: int, key: str, default=None):
    row = (
        db.query(RestaurantSetting)
        .filter(
            RestaurantSetting.restaurant_id == restaurant_id,
            RestaurantSetting.setting_key == key,
        )
        .first()
    )
    return row.setting_value if row and row.setting_value is not None else default

def get_restaurant_setting_str(db, restaurant_id: int, key: str, default=None):
    value = get_restaurant_setting(db, restaurant_id, key, default)
    return value if value is not None else default


def get_restaurant_setting_float(db, restaurant_id: int, key: str, default=0.0):
    value = get_restaurant_setting(db, restaurant_id, key, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def get_restaurant_setting_int(db, restaurant_id: int, key: str, default=0):
    value = get_restaurant_setting(db, restaurant_id, key, default)
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return int(default)


def get_restaurant_setting_bool(db, restaurant_id: int, key: str, default=False):
    value = get_restaurant_setting(db, restaurant_id, key, default)
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    return str(value).strip().lower() in {"1", "true", "yes", "si", "sí", "on"}

def is_restaurant_module_enabled(db, restaurant_id: int, module_code: str) -> bool:
    row = (
        db.query(RestaurantModule)
        .filter(
            RestaurantModule.restaurant_id == restaurant_id,
            RestaurantModule.module_code == module_code,
            RestaurantModule.is_enabled == True,
        )
        .first()
    )
    return row is not None


def get_restaurant_users(db, restaurant_id: int):
    return (
        db.query(RestaurantUser)
        .filter(
            RestaurantUser.restaurant_id == restaurant_id,
            RestaurantUser.is_active == True,
        )
        .order_by(RestaurantUser.id.asc())
        .all()
    )
