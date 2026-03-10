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
