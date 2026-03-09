from db import SessionLocal
from models_saas import (
    Restaurant,
    RestaurantModule,
    RestaurantSetting,
    RestaurantUser,
)

db = SessionLocal()

slug = "deaca"

restaurant = db.query(Restaurant).filter(Restaurant.slug == slug).first()

if not restaurant:
    restaurant = Restaurant(
        name="DEACA",
        slug="deaca",
        brand_name="DEACA POS",
        tagline="Fritanga Nica",
        logo_url="/static/logo.png",
        ruc="PENDIENTE",
        address="De la entrada de las fuentes 5c y media al sur mano izquierda",
        schedule="9:00 a.m. a 10:00 p.m.",
        latitude=None,
        longitude=None,
        whatsapp_phone_number_id=None,
        is_active=True,
    )
    db.add(restaurant)
    db.commit()
    db.refresh(restaurant)

# módulos habilitados iniciales para DEACA
module_codes = [
    "admin_core",
    "delivery_pos",
]

for code in module_codes:
    exists = (
        db.query(RestaurantModule)
        .filter(
            RestaurantModule.restaurant_id == restaurant.id,
            RestaurantModule.module_code == code,
        )
        .first()
    )
    if not exists:
        db.add(
            RestaurantModule(
                restaurant_id=restaurant.id,
                module_code=code,
                is_enabled=True,
            )
        )

# settings iniciales
settings = {
    "usd_to_nio_rate": "36.25",
    "accept_usd_cash": "1",
    "delivery_price_per_km": "5",
    "delivery_min_fee": "40",
    "delivery_max_radius_km": "15",
    "tax_enabled": "1",
    "tax_rate": "15",
    "show_tax_on_invoice": "1",
    "print_ticket_width_mm": "80",
    "ticket_footer_text": "Gracias por su compra",
    "show_driver_on_ticket": "1",
    "show_location_main": "1",
    "show_advisor_main": "1",
    "show_clear_order_main": "1",
}

for key, value in settings.items():
    exists = (
        db.query(RestaurantSetting)
        .filter(
            RestaurantSetting.restaurant_id == restaurant.id,
            RestaurantSetting.setting_key == key,
        )
        .first()
    )
    if not exists:
        db.add(
            RestaurantSetting(
                restaurant_id=restaurant.id,
                setting_key=key,
                setting_value=value,
            )
        )

# owner principal
owner = (
    db.query(RestaurantUser)
    .filter(
        RestaurantUser.restaurant_id == restaurant.id,
        RestaurantUser.role_code == "owner",
    )
    .first()
)

if not owner:
    owner = RestaurantUser(
        restaurant_id=restaurant.id,
        name="Owner DEACA",
        pin_code="1234",
        role_code="owner",
        is_active=True,
    )
    db.add(owner)

db.commit()
db.close()

print("Primer restaurante SaaS creado: DEACA")
