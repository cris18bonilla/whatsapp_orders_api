from db import SessionLocal
from models_saas import Restaurant

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
