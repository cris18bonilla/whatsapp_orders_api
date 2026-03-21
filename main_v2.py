import os
import json
import requests
import re
from typing import Optional, List, Dict
from decimal import Decimal
from pydantic import BaseModel, Field
from datetime import datetime

from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session

from config import settings
from db import Base, engine, SessionLocal, get_db

# Importar modelos NUEVOS para registrar tablas
from models.core_models import Restaurant, RestaurantModule, RestaurantSetting
from models.security_models import (
    RestaurantUser,
    Permission,
    RolePermission,
    UserPermission,
    UserSession,
    ActivityLog,
)
from models.sales_models import Order, OrderItem, OrderPayment, RestaurantZone, RestaurantTable
from models.cash_models import CashSession, CashMovement
from models.inventory_models import Product, InventoryItem, Recipe, InventoryMovement
from models.hr_models import (
    Employee,
    EmployeeAttendance,
    EmployeeVacation,
    SalaryAdvance,
    EmployeeSettlement,
)
from models.analytics_models import (
    DailyMetric,
    ProductSalesMetric,
    UserSalesMetric,
    DriverMetric,
)

app = FastAPI(title="NICALIA POS SUITE Demo V1")


# =========================
# CONFIG / SEED
# =========================

DEFAULT_RESTAURANT_NAME = os.getenv("DEFAULT_RESTAURANT_NAME", "DEACA")
DEFAULT_RESTAURANT_SLUG = os.getenv("DEFAULT_RESTAURANT_SLUG", "deaca")
DEFAULT_BRAND_NAME = os.getenv("DEFAULT_BRAND_NAME", "NICALIA POS SUITE Demo")
DEFAULT_TAGLINE = os.getenv("DEFAULT_TAGLINE", "Sistema modular para restaurantes")


MODULE_CODES = [
    "admin",
    "pos_local",
    "pos_delivery",
    "kitchen",
    "cash",
    "inventory",
    "hr",
    "analytics",
    "whatsapp",
]

DEFAULT_PERMISSIONS = [
    ("admin.access", "Entrar a Admin", "admin"),
    ("pos.local.access", "Entrar a POS Local", "pos_local"),
    ("pos.delivery.access", "Entrar a POS Delivery", "pos_delivery"),
    ("kitchen.access", "Entrar a Kitchen Display", "kitchen"),
    ("cash.access", "Entrar a Caja", "cash"),
    ("inventory.access", "Entrar a Inventario", "inventory"),
    ("hr.access", "Entrar a RRHH", "hr"),
    ("analytics.access", "Entrar a Analytics", "analytics"),
    ("whatsapp.access", "Entrar a configuración WhatsApp", "whatsapp"),
    ("cash.open", "Abrir caja", "cash"),
    ("cash.move", "Registrar movimiento de caja", "cash"),
    ("cash.close", "Cerrar caja", "cash"),
    ("orders.create", "Crear órdenes", "pos_local"),
    ("orders.pay", "Cobrar órdenes", "cash"),
    ("inventory.adjust", "Ajustar inventario", "inventory"),
    ("hr.manage", "Gestionar RRHH", "hr"),
    ("analytics.view", "Ver analytics", "analytics"),
]


def seed_permissions(db: Session) -> None:
    for code, name, module_code in DEFAULT_PERMISSIONS:
        exists = db.query(Permission).filter(Permission.code == code).first()
        if not exists:
            db.add(
                Permission(
                    code=code,
                    name=name,
                    module_code=module_code,
                )
            )
    db.commit()


def seed_restaurant_and_owner(db: Session) -> Restaurant:
    restaurant = (
        db.query(Restaurant)
        .filter(Restaurant.slug == DEFAULT_RESTAURANT_SLUG)
        .first()
    )

    if not restaurant:
        restaurant = Restaurant(
            name=DEFAULT_RESTAURANT_NAME,
            slug=DEFAULT_RESTAURANT_SLUG,
            brand_name=DEFAULT_BRAND_NAME,
            tagline=DEFAULT_TAGLINE,
            is_active=True,
        )
        db.add(restaurant)
        db.commit()
        db.refresh(restaurant)

    for module_code in MODULE_CODES:
        exists = (
            db.query(RestaurantModule)
            .filter(
                RestaurantModule.restaurant_id == restaurant.id,
                RestaurantModule.module_code == module_code,
            )
            .first()
        )
        if not exists:
            db.add(
                RestaurantModule(
                    restaurant_id=restaurant.id,
                    module_code=module_code,
                    is_enabled=True,
                )
            )

    setting_pairs = {
        "tax_enabled": "1",
        "tax_rate": "15",
        "currency_default": "NIO",
        "invoice_prefix": "DEACA",
        "session_warning_seconds": str(settings.session_warning_seconds),
        "default_idle_timeout_seconds": str(settings.default_idle_timeout_seconds),
        "whatsapp_catalog_enabled": "1",
    }

    for key, value in setting_pairs.items():
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
                    setting_value=raw,
                )
            )

    db.commit()
    
    # OWNER / usuarios se migraran despues
    return restaurant

def seed_demo_products(db: Session, restaurant: Restaurant) -> None:
    demo_products = [
        {
            "name": "Pollo frito",
            "category": "Platos",
            "price": Decimal("180.00"),
            "description": "Pollo frito tradicional.",
            "image_url": "",
        },
        {
            "name": "Combo pollo + papas",
            "category": "Combos",
            "price": Decimal("220.00"),
            "description": "Combo con papas y bebida.",
            "image_url": "",
        },
        {
            "name": "Gaseosa",
            "category": "Bebidas",
            "price": Decimal("35.00"),
            "description": "Bebida gaseosa fría.",
            "image_url": "",
        },
        {
            "name": "Tajadas",
            "category": "Acompañantes",
            "price": Decimal("40.00"),
            "description": "Tajadas crujientes.",
            "image_url": "",
        },
    ]

    for item in demo_products:
        exists = (
            db.query(Product)
            .filter(
                Product.restaurant_id == restaurant.id,
                Product.name == item["name"],
            )
            .first()
        )
        if not exists:
            db.add(
                Product(
                    restaurant_id=restaurant.id,
                    name=item["name"],
                    category=item["category"],
                    price=item["price"],
                    description=item["description"],
                    image_url=item["image_url"],
                    is_active=True,
                )
            )

    db.commit()


@app.on_event("startup")
def startup_event():
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        seed_permissions(db)
        restaurant = seed_restaurant_and_owner(db)
        seed_demo_products(db, restaurant)
    finally:
        db.close()


# =========================
# HELPERS
# =========================

def get_setting_value(db: Session, restaurant_id: int, key: str, default: str = "") -> str:
    row = (
        db.query(RestaurantSetting)
        .filter(
            RestaurantSetting.restaurant_id == restaurant_id,
            RestaurantSetting.setting_key == key,
        )
        .first()
    )
    return row.setting_value if row and row.setting_value is not None else default


def get_tax_rate_decimal(db: Session, restaurant_id: int) -> Decimal:
    tax_enabled = get_setting_value(db, restaurant_id, "tax_enabled", "1")
    if str(tax_enabled).strip() not in ("1", "true", "True", "yes", "YES"):
        return Decimal("0")

    raw = get_setting_value(db, restaurant_id, "tax_rate", "15")
    try:
        return Decimal(str(raw))
    except Exception:
        return Decimal("15")


def to_decimal(value) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")

def get_restaurant_or_404(
    db: Session,
    restaurant_slug: Optional[str],
) -> Restaurant:
    restaurant = None

def get_restaurant_by_phone_number_id(db: Session, phone_number_id: str):
    if not phone_number_id:
        return None

    return (
        db.query(Restaurant)
        .filter(Restaurant.whatsapp_phone_number_id == str(phone_number_id))
        .first()
    )

    if restaurant_slug:
        restaurant = (
            db.query(Restaurant)
            .filter(
                Restaurant.slug == restaurant_slug,
                Restaurant.is_active == True,  # noqa: E712
            )
            .first()
        )

    if not restaurant:
        restaurant = (
            db.query(Restaurant)
            .filter(Restaurant.is_active == True)  # noqa: E712
            .order_by(Restaurant.id.asc())
            .first()
        )

    if not restaurant:
        raise HTTPException(status_code=404, detail="No hay restaurantes configurados.")

    return restaurant


def get_enabled_modules(db: Session, restaurant_id: int) -> List[str]:
    rows = (
        db.query(RestaurantModule)
        .filter(
            RestaurantModule.restaurant_id == restaurant_id,
            RestaurantModule.is_enabled == True,  # noqa: E712
        )
        .all()
    )
    return [row.module_code for row in rows]


def html_shell(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        f"""
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      --bg:#f5f7fb;
      --card:#ffffff;
      --text:#111827;
      --muted:#6b7280;
      --line:#d1d5db;
      --shadow:0 2px 10px rgba(0,0,0,.05);
      --dark:#111827;
      --accent:#2563eb;
    }}
    * {{ box-sizing:border-box; }}
    body {{
      margin:0;
      font-family:system-ui,-apple-system,Arial,sans-serif;
      background:var(--bg);
      color:var(--text);
    }}
    .wrap {{
      max-width:1200px;
      margin:0 auto;
      padding:24px;
    }}
    .top {{
      display:flex;
      justify-content:space-between;
      align-items:center;
      gap:12px;
      flex-wrap:wrap;
      margin-bottom:20px;
    }}
    .brand h1 {{
      margin:0;
      font-size:32px;
      line-height:1.05;
    }}
    .brand p {{
      margin:6px 0 0;
      color:var(--muted);
    }}
    .pill {{
      display:inline-flex;
      padding:8px 12px;
      border-radius:999px;
      background:#fff;
      border:1px solid var(--line);
      box-shadow:var(--shadow);
      font-size:13px;
      color:#374151;
    }}
    .grid {{
      display:grid;
      grid-template-columns:repeat(auto-fit,minmax(220px,1fr));
      gap:16px;
    }}
    .card {{
      background:var(--card);
      border:1px solid var(--line);
      border-radius:18px;
      padding:18px;
      box-shadow:var(--shadow);
      text-decoration:none;
      color:inherit;
      transition:.18s ease;
      display:block;
    }}
    .card:hover {{
      transform:translateY(-2px);
      border-color:#9ca3af;
    }}
    .card h3 {{
      margin:0 0 8px;
      font-size:20px;
    }}
    .card p {{
      margin:0;
      color:var(--muted);
      font-size:14px;
      line-height:1.5;
    }}
    .section {{
      margin-top:26px;
    }}
    .section h2 {{
      margin:0 0 12px;
      font-size:20px;
    }}
    .mono {{
      font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
    }}
    .muted {{
      color:var(--muted);
    }}
    .box {{
      background:#fff;
      border:1px solid var(--line);
      border-radius:16px;
      padding:18px;
      box-shadow:var(--shadow);
    }}
    .btn {{
      display:inline-flex;
      align-items:center;
      justify-content:center;
      border:none;
      background:var(--dark);
      color:#fff;
      padding:10px 14px;
      border-radius:10px;
      text-decoration:none;
      font-weight:700;
      cursor:pointer;
    }}
    table {{
      width:100%;
      border-collapse:collapse;
      background:#fff;
      border:1px solid var(--line);
      border-radius:14px;
      overflow:hidden;
    }}
    th, td {{
      text-align:left;
      padding:12px;
      border-bottom:1px solid #e5e7eb;
      font-size:14px;
    }}
    th {{
      background:#f9fafb;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    {body}
  </div>
</body>
</html>
"""
    )

def parse_pipe_notes_meta(notes: str) -> Dict[str, str]:
    data: Dict[str, str] = {}
    for raw in (notes or "").split("|"):
        chunk = (raw or "").strip()
        if not chunk or ":" not in chunk:
            continue
        key, value = chunk.split(":", 1)
        data[key.strip().lower()] = value.strip()
    return data

# =========================
# PYDANTIC SCHEMAS
# =========================

class OrderItemInput(BaseModel):
    product_id: int
    quantity: Decimal = Field(default=Decimal("1"))

class CreateOrderInput(BaseModel):
    channel: str
    customer_name: str = ""
    customer_phone: str = ""
    table_number: str = ""
    notes: str = ""
    items: List[OrderItemInput]

class PayOrderInput(BaseModel):
    method: str
    amount: Decimal
    reference: str = ""
    bank_name: str = ""
    terminal_id: str = ""
    authorization_code: str = ""
    card_brand: str = ""
    card_last4: str = ""

class ProductCreateInput(BaseModel):
    name: str
    category: str = ""
    price: Decimal = Field(default=Decimal("0"))
    description: str = ""
    image_url: str = ""
    is_active: bool = True


class ProductUpdateInput(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    price: Optional[Decimal] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    is_active: Optional[bool] = None

class CategoryRenameInput(BaseModel):
    old_name: str
    new_name: str


class CategoryDeleteInput(BaseModel):
    name: str
    replacement: str = "General"

class ZoneCreateInput(BaseModel):
    name: str
    sort_order: int = 0
    is_active: bool = True


class ZoneUpdateInput(BaseModel):
    name: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class TableCreateInput(BaseModel):
    zone_id: Optional[int] = None
    code: str
    display_name: str
    capacity: int = 4
    sort_order: int = 0
    is_active: bool = True


class TableUpdateInput(BaseModel):
    zone_id: Optional[int] = None
    code: Optional[str] = None
    display_name: Optional[str] = None
    capacity: Optional[int] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class OpenLocalTicketInput(BaseModel):
    service_mode: str  # table | bar | quick
    table_id: Optional[int] = None
    zone_id: Optional[int] = None
    customer_name: str = ""
    customer_phone: str = ""
    notes: str = ""


class LocalTicketItemInput(BaseModel):
    product_id: int
    quantity: Decimal = Field(default=Decimal("1"))
    notes: str = ""


class AddItemsToOpenTicketInput(BaseModel):
    items: List[LocalTicketItemInput]


class SendNewItemsInput(BaseModel):
    item_ids: Optional[List[int]] = None


class SplitItemLineInput(BaseModel):
    order_item_id: int
    quantity: Decimal = Field(default=Decimal("1"))


class SplitItemsInput(BaseModel):
    items: List[SplitItemLineInput]


class SplitPaymentLineInput(BaseModel):
    method: str
    amount: Decimal
    reference: str = ""
    bank_name: str = ""
    terminal_id: str = ""
    authorization_code: str = ""
    card_brand: str = ""
    card_last4: str = ""


class SplitPaymentInput(BaseModel):
    payments: List[SplitPaymentLineInput]


class CloseLocalTicketInput(BaseModel):
    force_close: bool = False

# =========================
# RUTAS BASE
# =========================

@app.get("/", response_class=HTMLResponse)
def root():
    return HTMLResponse(
        '<meta http-equiv="refresh" content="0; url=/v2/menu">'
    )


@app.get("/v2/health")
def v2_health():
    return {
        "ok": True,
        "app": settings.app_name,
        "env": settings.app_env,
        "database": settings.database_url.split("@")[-1] if "@" in settings.database_url else settings.database_url,
        "mode": "main_v2",
    }


@app.get("/v2/menu", response_class=HTMLResponse)
def v2_menu(
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)
    modules = set(get_enabled_modules(db, rest.id))

    def card(label: str, desc: str, path: str, module_code: str) -> str:
        if module_code not in modules and module_code != "admin":
            return ""
        return f"""
        <a class="card" href="{path}?restaurant={rest.slug}">
          <h3>{label}</h3>
          <p>{desc}</p>
        </a>
        """

    body = f"""
    <div class="top">
      <div class="brand">
        <h1>NICALIA POS SUITE</h1>
        <p>{rest.name} · {rest.tagline or 'Demo V1'}</p>
      </div>
      <div class="pill mono">restaurant={rest.slug}</div>
    </div>

    <div class="section">
        <h2>Usuarios</h2>
        <div class="box">
            <p>La migración de usuarios y sesiones se conectará en el siguiente bloque.</p>
        </div>
    </div>

    </div>    <div class="section">
      <h2>Menú principal</h2>
      <div class="grid">
        {card("POS Local", "Ventas en mostrador, mesas y salón.", "/v2/pos/local", "pos_local")}
        {card("POS Delivery", "Pedidos para envío y reparto.", "/v2/pos/delivery", "pos_delivery")}
        {card("Kitchen Display", "Pantalla de cocina en tiempo real.", "/v2/kitchen", "kitchen")}
        {card("Caja", "Apertura, movimientos y cierre de caja.", "/v2/cash", "cash")}
        {card("Inventario", "Stock, recetas y kardex.", "/v2/inventory", "inventory")}
        {card("RRHH", "Empleados, asistencia y vacaciones.", "/v2/hr", "hr")}
        {card("Analytics", "Métricas y rendimiento del negocio.", "/v2/analytics", "analytics")}
        {card("Admin", "Configuración general del sistema.", "/v2/admin", "admin")}
      </div>
    </div>

    <div class="section">
      <h2>Estado de la Demo</h2>
      <div class="box">
        <p><strong>Base nueva activa:</strong> sí</p>
        <p><strong>Motor:</strong> FastAPI + PostgreSQL</p>
        <p><strong>Canales de venta:</strong> local, delivery, pickup, whatsapp</p>
        <p><strong>Pin admin demo:</strong> {settings.admin_pin}</p>
      </div>
    </div>
    """
    return html_shell("NICALIA POS SUITE", body)


# =========================
# PÁGINAS PLACEHOLDER
# =========================

def placeholder_page(title: str, restaurant_slug: str, message: str) -> HTMLResponse:
    body = f"""
    <div class="top">
      <div class="brand">
        <h1>{title}</h1>
        <p class="muted">restaurant={restaurant_slug}</p>
      </div>
      <a class="btn" href="/v2/menu?restaurant={restaurant_slug}">Volver al menú</a>
    </div>
    <div class="box">
      <p>{message}</p>
    </div>
    """
    return html_shell(title, body)

@app.get("/v2/pos/local/floor", response_class=HTMLResponse)
def v2_pos_local_floor(
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    body = f"""
    <style>
      .floor-shell {{
        display: grid;
        gap: 16px;
      }}
      .floor-top {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 12px;
        flex-wrap: wrap;
      }}
      .floor-brand h1 {{
        margin: 0;
        font-size: 32px;
        font-weight: 800;
      }}
      .floor-brand p {{
        margin: 4px 0 0 0;
        color: #6b7280;
      }}
      .floor-actions {{
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
      }}
      .floor-btn {{
        border: 0;
        border-radius: 12px;
        padding: 12px 16px;
        font-weight: 700;
        cursor: pointer;
        background: #111827;
        color: #fff;
      }}
      .floor-btn.light {{
        background: #fff;
        color: #111827;
        border: 1px solid #e5e7eb;
      }}
      .zone-bar {{
        display: flex;
        gap: 10px;
        overflow-x: auto;
        padding-bottom: 2px;
      }}
      .zone-btn {{
        border: 1px solid #e5e7eb;
        background: #fff;
        color: #111827;
        border-radius: 999px;
        padding: 10px 14px;
        font-weight: 700;
        white-space: nowrap;
        cursor: pointer;
      }}
      .zone-btn.active {{
        background: #111827;
        color: #fff;
        border-color: #111827;
      }}
      .floor-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
        gap: 16px;
      }}
      .table-card {{
        border: 1px solid #e5e7eb;
        border-radius: 18px;
        background: #fff;
        padding: 16px;
        cursor: pointer;
        transition: 0.18s ease;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
      }}
      .table-card:hover {{
        transform: translateY(-1px);
        box-shadow: 0 10px 25px rgba(0,0,0,0.08);
      }}
      .table-card.free {{
        border-color: #d1d5db;
      }}
      .table-card.open {{
        border-color: #111827;
      }}
      .table-card.preparing {{
        border-color: #f59e0b;
        background: #fffaf0;
      }}
      .table-card.ready {{
        border-color: #10b981;
        background: #f0fdf4;
      }}
      .table-card.paid {{
        border-color: #60a5fa;
        background: #eff6ff;
      }}
      .table-top {{
        display: flex;
        justify-content: space-between;
        align-items: start;
        gap: 10px;
      }}
      .table-name {{
        font-size: 20px;
        font-weight: 800;
        line-height: 1.1;
      }}
      .table-zone {{
        color: #6b7280;
        font-size: 13px;
        margin-top: 4px;
      }}
      .table-badge {{
        border-radius: 999px;
        padding: 6px 10px;
        font-size: 12px;
        font-weight: 800;
        background: #f3f4f6;
        color: #111827;
      }}
      .table-meta {{
        margin-top: 14px;
y        display: grid;
        gap: 8px;
      }}
      .table-meta-row {{
        display: flex;
        justify-content: space-between;
        gap: 8px;
        font-size: 14px;
      }}
      .table-meta-row strong {{
        font-size: 18px;
      }}
      .muted {{
        color: #6b7280;
      }}
      .section-title {{
        margin: 8px 0 0 0;
        font-size: 20px;
        font-weight: 800;
      }}
    </style>

    <div class="floor-shell">
      <div class="floor-top">
        <div class="floor-brand">
          <h1>POS Local · Floor</h1>
          <p>{rest.name} · {rest.slug}</p>
        </div>

        <div class="floor-actions">
          <button class="floor-btn light" onclick="window.location.href='/v2/menu?restaurant={rest.slug}'">Volver al menú</button>
          <button class="floor-btn light" onclick="openBarTicket()">Barra</button>
          <button class="floor-btn" onclick="openQuickTicket()">Venta rápida</button>
        </div>
      </div>

      <div class="zone-bar" id="zoneBar"></div>

      <h2 class="section-title">Mesas</h2>
      <div class="floor-grid" id="floorGrid"></div>
    </div>

    <script>
      const floorRestaurantSlug = "__REST_SLUG__";
      let floorZones = [];
      let floorTables = [];
      let activeZoneId = null;

      function statusLabel(status) {{
        const map = {{
          free: "Libre",
          open: "Ocupada",
          preparing: "Preparando",
          ready: "Lista",
          paid: "Pagada",
          closed: "Cerrada",
          cancelled: "Cancelada"
        }};
        return map[status] || status || "Libre";
      }}

      function renderZoneBar() {{
        const bar = document.getElementById("zoneBar");
        const items = [
          {{ id: null, name: "Todas" }},
          ...floorZones.map(z => ({{ id: z.id, name: z.name }}))
        ];

        bar.innerHTML = items.map(z => `
          <button
            class="zone-btn ${{z.id === activeZoneId ? "active" : ""}}"
            onclick="setActiveZone(${{z.id === null ? 'null' : z.id}})">
            ${{z.name}}
          </button>
        `).join("");
      }}

      function renderFloorGrid() {{
        const grid = document.getElementById("floorGrid");

        let filtered = [...floorTables];
        if (activeZoneId !== null) {{
          filtered = filtered.filter(x => Number(x.table.zone_id || 0) === Number(activeZoneId));
        }}

        const cards = filtered.map(x => {{
          const st = x.status || "free";
          const total = Number(x.total || 0).toFixed(2);
          const unsent = Number(x.unsent_count || 0);
          const tableName = x.table.display_name || x.table.code || "Mesa";
          const zoneName = x.zone_name || "Sin zona";
          const targetAction = x.active_order_id
            ? `window.location.href='/v2/pos/local/ticket/${{x.active_order_id}}?restaurant=${{floorRestaurantSlug}}'`
            : `openTableTicket(${{x.table.id}})`;

          return `
            <div class="table-card ${{st}}" onclick="${{targetAction}}">
              <div class="table-top">
                <div>
                  <div class="table-name">${{tableName}}</div>
                  <div class="table-zone">${{zoneName}}</div>
                </div>
                <div class="table-badge">${{statusLabel(st)}}</div>
              </div>

              <div class="table-meta">
                <div class="table-meta-row">
                  <span class="muted">Código</span>
                  <span>${{x.table.code || "-"}}</span>
                </div>
                <div class="table-meta-row">
                  <span class="muted">Capacidad</span>
                  <span>${{x.table.capacity || 0}}</span>
                </div>
                <div class="table-meta-row">
                  <span class="muted">Pendientes</span>
                  <span>${{unsent}}</span>
                </div>
                <div class="table-meta-row">
                  <span class="muted">Total</span>
                  <strong>C$${{total}}</strong>
                </div>
              </div>
            </div>
          `;
        }});

        grid.innerHTML = cards.length
          ? cards.join("")
          : `<div class="muted">No hay mesas en esta zona.</div>`;
      }}

      function setActiveZone(zoneId) {{
        activeZoneId = zoneId;
        renderZoneBar();
        renderFloorGrid();
      }}

      async function loadFloor() {{
        const res = await fetch(`/v2/api/floor?restaurant=${{floorRestaurantSlug}}`);
        const data = await res.json();

        floorZones = data.zones || [];
        floorTables = data.tables || [];

        renderZoneBar();
        renderFloorGrid();
      }}

      async function openTableTicket(tableId) {{
        const res = await fetch(`/v2/api/local/open-ticket?restaurant=${{floorRestaurantSlug}}`, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{
            service_mode: "table",
            table_id: Number(tableId),
            customer_name: "",
            customer_phone: "",
            notes: ""
          }})
        }});

        const data = await res.json();

        if (!res.ok) {{
          alert(data.detail || "No se pudo abrir la mesa.");
          return;
        }}

        window.location.href = `/v2/pos/local/ticket/${{data.ticket.id}}?restaurant=${{floorRestaurantSlug}}`;
      }}

      async function openBarTicket() {{
        const res = await fetch(`/v2/api/local/open-ticket?restaurant=${{floorRestaurantSlug}}`, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{
            service_mode: "bar",
            customer_name: "",
            customer_phone: "",
            notes: ""
          }})
        }});
        const data = await res.json();

        if (!res.ok) {{
          alert(data.detail || "No se pudo abrir el ticket de barra.");
          return;
        }}

        window.location.href = `/v2/pos/local/ticket/${{data.ticket.id}}?restaurant=${{floorRestaurantSlug}}`;
      }}

      async function openQuickTicket() {{
        const res = await fetch(`/v2/api/local/open-ticket?restaurant=${{floorRestaurantSlug}}`, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{
            service_mode: "quick",
            customer_name: "",
            customer_phone: "",
            notes: ""
          }})
        }});
        const data = await res.json();

        if (!res.ok) {{
          alert(data.detail || "No se pudo abrir la venta rápida.");
          return;
        }}

        window.location.href = `/v2/pos/local/ticket/${{data.ticket.id}}?restaurant=${{floorRestaurantSlug}}`;
      }}

      loadFloor();
    </script>
    """

    body = body.replace("__REST_SLUG__", str(rest.slug or ""))
    return html_shell("POS Local Floor", body)

@app.get("/v2/pos/local/ticket/{order_id}", response_class=HTMLResponse)
def v2_pos_local_ticket(
    order_id: int,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    order = (
        db.query(Order)
        .filter(
            Order.id == order_id,
            Order.restaurant_id == rest.id,
        )
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Ticket no encontrado.")

    body = f"""
    <style>
      .ticket-shell {{
        display: grid;
        grid-template-columns: minmax(320px, 1.1fr) minmax(360px, 0.9fr);
        gap: 18px;
      }}
      .panel {{
        background: #fff;
        border: 1px solid #e5e7eb;
        border-radius: 18px;
        padding: 16px;
        box-sizing: border-box;
      }}
      .ticket-top {{
        display: flex;
        justify-content: space-between;
        align-items: start;
        gap: 12px;
        flex-wrap: wrap;
        margin-bottom: 12px;
      }}
      .ticket-title {{
        margin: 0;
        font-size: 28px;
        font-weight: 800;
      }}
      .ticket-sub {{
        margin: 4px 0 0 0;
        color: #6b7280;
      }}
      .pill-row {{
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
      }}
      .pill {{
        border: 1px solid #e5e7eb;
        background: #fff;
        border-radius: 999px;
        padding: 8px 12px;
        font-size: 12px;
        font-weight: 800;
      }}
      .toolbar {{
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
        margin-bottom: 14px;
      }}
      .btn {{
        border: 0;
        border-radius: 12px;
        padding: 12px 16px;
        font-weight: 800;
        cursor: pointer;
      }}
      .btn.dark {{
        background: #111827;
        color: #fff;
      }}
      .btn.light {{
        background: #fff;
        color: #111827;
        border: 1px solid #e5e7eb;
      }}
      .btn.warn {{
        background: #f59e0b;
        color: #111827;
      }}
      .btn.good {{
        background: #10b981;
        color: #fff;
      }}
      .section-title {{
        font-size: 18px;
        font-weight: 800;
        margin: 8px 0 12px 0;
      }}
      .products-toolbar {{
        display: grid;
        grid-template-columns: 1fr 220px;
        gap: 10px;
        margin-bottom: 12px;
      }}
      .input, .select {{
        width: 100%;
        border: 1px solid #d1d5db;
        border-radius: 12px;
        padding: 12px 14px;
        font-size: 14px;
        box-sizing: border-box;
        background: #fff;
      }}
      .category-bar {{
        display: flex;
        gap: 10px;
        overflow-x: auto;
        padding-bottom: 2px;
        margin-bottom: 14px;
      }}
      .category-btn {{
        border: 1px solid #e5e7eb;
        background: #fff;
        color: #111827;
        border-radius: 999px;
        padding: 10px 14px;
        font-weight: 700;
        white-space: nowrap;
        cursor: pointer;
      }}
      .category-btn.active {{
        background: #111827;
        color: #fff;
        border-color: #111827;
      }}
      .products-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
        gap: 12px;
      }}
      .product-card {{
        border: 1px solid #e5e7eb;
        border-radius: 16px;
        background: #fff;
        padding: 14px;
        cursor: pointer;
      }}
      .product-name {{
        font-size: 16px;
        font-weight: 800;
      }}
      .product-category {{
        margin-top: 4px;
        color: #6b7280;
        font-size: 12px;
      }}
      .product-price {{
        margin-top: 12px;
        font-size: 20px;
        font-weight: 800;
      }}
      .ticket-box {{
        display: grid;
        gap: 10px;
      }}
      .line-card {{
        border: 1px solid #e5e7eb;
        border-radius: 14px;
        padding: 12px 14px;
        background: #fff;
      }}
      .line-top {{
        display: flex;
        justify-content: space-between;
        gap: 10px;
        align-items: start;
      }}
      .line-name {{
        font-weight: 800;
        font-size: 16px;
      }}
      .line-meta {{
        margin-top: 4px;
        color: #6b7280;
        font-size: 13px;
      }}
      .line-total {{
        font-weight: 800;
        font-size: 16px;
        white-space: nowrap;
      }}
      .badge {{
        display: inline-block;
        border-radius: 999px;
        padding: 5px 10px;
        font-size: 11px;
        font-weight: 800;
        background: #f3f4f6;
        margin-top: 8px;
      }}
      .badge.unsent {{
        background: #fff7ed;
        color: #9a3412;
      }}
      .badge.sent {{
        background: #eff6ff;
        color: #1d4ed8;
      }}
      .summary {{
        margin-top: 14px;
        display: grid;
        gap: 10px;
      }}
      .summary-row {{
        display: flex;
        justify-content: space-between;
        gap: 10px;
      }}
      .summary-total {{
        font-size: 28px;
        font-weight: 900;
      }}
      .muted {{
        color: #6b7280;
      }}
      .empty {{
        color: #6b7280;
        padding: 14px 0;
      }}
      .split-box {{
        margin-top: 18px;
        border-top: 1px solid #e5e7eb;
        padding-top: 16px;
        display: grid;
        gap: 10px;
      }}
      .split-row {{
        display: grid;
        grid-template-columns: 24px 1fr 110px;
        gap: 10px;
        align-items: center;
      }}
      .split-qty {{
        width: 100%;
        border: 1px solid #d1d5db;
        border-radius: 10px;
        padding: 8px 10px;
        box-sizing: border-box;
      }}
      .split-summary {{
        display: grid;
        gap: 8px;
        margin-top: 10px;
        padding: 12px;
        border: 1px dashed #d1d5db;
        border-radius: 12px;
        background: #fafafa;
      }}
    </style>

    <div class="ticket-shell">
      <div class="panel">
        <div class="ticket-top">
          <div>
            <h1 class="ticket-title">Ticket Local</h1>
            <p class="ticket-sub">Restaurante: {rest.name} · Ticket #__ORDER_ID__</p>
          </div>

          <div class="toolbar">
            <button class="btn light" onclick="window.location.href='/v2/pos/local/floor?restaurant=__REST_SLUG__'">Volver al floor</button>
            <button class="btn light" onclick="openBarFromTicket()">Barra</button>
            <button class="btn light" onclick="openQuickFromTicket()">Venta rápida</button>
            <button class="btn warn" onclick="sendNewItems()">A cocina</button>
          </div> 
        </div>

        <div class="pill-row" id="ticketHeaderPills"></div>

        <div class="section-title">Agregar productos</div>

        <div class="products-toolbar">
          <input id="searchProduct" class="input" placeholder="Buscar por nombre..." />
          <select id="categorySelect" class="select"></select>
        </div>

        <div class="category-bar" id="categoryBar"></div>
        <div class="products-grid" id="productsGrid"></div>
      </div>

      <div class="panel">
        <div class="section-title">Cuenta abierta</div>
        <div id="ticketBox" class="ticket-box"></div>

        <div class="summary">
          <div class="summary-row"><span>Subtotal</span><strong id="subtotalView">C$0.00</strong></div>
          <div class="summary-row"><span>Impuesto</span><strong id="taxView">C$0.00</strong></div>
          <div class="summary-row"><span>Total</span><strong id="totalView" class="summary-total">C$0.00</strong></div>
        </div>
        <div class="section-title" style="margin-top:18px;">Cobro</div>

        <div style="display:grid;gap:10px;margin-bottom:12px;">
          <select id="payMethod" class="select">
            <option value="cash">Efectivo</option>
            <option value="card">Tarjeta</option>
            <option value="transfer">Transferencia</option>
            <option value="credit">Crédito</option>
          </select>

          <input id="payAmount" class="input" type="number" step="0.01" placeholder="Monto a cobrar" />

          <input id="payReference" class="input" placeholder="Referencia / nota" />

          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
            <input id="payBank" class="input" placeholder="Banco" />
            <input id="payTerminal" class="input" placeholder="Terminal" />
          </div>

          <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">
            <input id="payAuth" class="input" placeholder="Autorización" />
            <input id="payCardMeta" class="input" placeholder="Marca y últimos 4" />
          </div>

          <div style="display:flex;gap:10px;flex-wrap:wrap;">
            <button class="btn dark" onclick="chargeTicket()">Cobrar</button>
            <button class="btn light" onclick="fillPendingBalance()">Cobrar saldo exacto</button>
            <button class="btn good" onclick="closeTicket(false)">Cerrar ticket</button>
            <button class="btn warn" onclick="closeTicket(true)">Forzar cierre</button>
          </div>
        </div>

        <div class="summary">
          <div class="summary-row"><span>Pagado</span><strong id="paidAmountView">C$0.00</strong></div>
          <div class="summary-row"><span>Saldo pendiente</span><strong id="balanceDueView">C$0.00</strong></div>
        </div>

        <div class="section-title" style="margin-top:18px;">Pagos aplicados</div>
        <div id="paymentsBox" class="ticket-box"></div>
        <div class="split-box">
          <div class="section-title">Split por productos</div>
          <div id="splitItemsBox" class="ticket-box"></div>

          <div class="split-summary">
            <div class="summary-row"><span>Total selección</span><strong id="splitTotalView">C$0.00</strong></div>
            <div class="summary-row"><span>Saldo antes</span><strong id="splitBeforeView">C$0.00</strong></div>
            <div class="summary-row"><span>Saldo después</span><strong id="splitAfterView">C$0.00</strong></div>
          </div>

          <div style="display:flex;gap:10px;flex-wrap:wrap;">
            <button class="btn light" onclick="previewSplitSelection()">Previsualizar selección</button>
            <button class="btn dark" onclick="paySplitSelection()">Pagar selección</button>
          </div>
        </div>
      </div>
    </div>

    <script>
      const ticketRestaurantSlug = "__REST_SLUG__";
      const currentOrderId = Number("__ORDER_ID__");

      let ticketData = null;
      let paymentsData = null;
      let splitPreviewData = null;
      let products = [];
      let categories = [];
      let activeCategory = "Todas";

      function money(v) {{
        return `C$${{Number(v || 0).toFixed(2)}}`;
      }}

      function statusLabel(status) {{
        const map = {{
          open: "Abierta",
          preparing: "Preparando",
          ready: "Lista",
          paid: "Pagada",
          closed: "Cerrada",
          cancelled: "Cancelada"
        }};
        return map[status] || status || "Abierta";
      }}

      async function loadTicket() {{
        const res = await fetch(`/v2/api/local/ticket/${{currentOrderId}}?restaurant=${{ticketRestaurantSlug}}`);
        const data = await res.json();
        if (!res.ok) {{
          alert(data.detail || "No se pudo cargar el ticket.");
          return;
        }}
        ticketData = data.ticket;
        renderTicket();
      }}

      async function loadProducts() {{
        const res = await fetch(`/v2/api/products?restaurant=${{ticketRestaurantSlug}}`);
        const data = await res.json();
        products = data.items || [];

        categories = ["Todas", ...new Set(products.map(p => (p.category || "General").trim() || "General"))];
        renderCategories();
        renderProducts();
      }}

      function renderCategories() {{
        const select = document.getElementById("categorySelect");
        const bar = document.getElementById("categoryBar");

        select.innerHTML = categories.map(cat =>
          `<option value="${{cat}}" ${{cat === activeCategory ? "selected" : ""}}>${{cat}}</option>`
        ).join("");

        bar.innerHTML = categories.map(cat => `
          <button class="category-btn ${{cat === activeCategory ? "active" : ""}}" onclick="setCategory('${{cat.replace(/'/g, "\\'")}}')">
            ${{cat}}
          </button>
        `).join("");
      }}

      function setCategory(cat) {{
        activeCategory = cat;
        renderCategories();
        renderProducts();
      }}

      function renderProducts() {{
        const q = (document.getElementById("searchProduct").value || "").trim().toLowerCase();
        const grid = document.getElementById("productsGrid");

        let filtered = [...products];
        if (activeCategory !== "Todas") {{
          filtered = filtered.filter(p => (((p.category || "General").trim()) || "General") === activeCategory);
        }}
        if (q) {{
          filtered = filtered.filter(p =>
            (p.name || "").toLowerCase().includes(q) ||
            (((p.category || "General").trim()) || "General").toLowerCase().includes(q)
          );
        }}

        grid.innerHTML = filtered.length ? filtered.map(p => `
          <div class="product-card" onclick="addProductToTicket(${{p.id}})">
            <div class="product-name">${{p.name || ""}}</div>
            <div class="product-category">${{p.category || "General"}}</div>
            <div class="product-price">${{money(p.price)}}</div>
          </div>
        `).join("") : `<div class="empty">No hay productos para este filtro.</div>`;
      }}

      function renderTicket() {{
        const pills = document.getElementById("ticketHeaderPills");
        const box = document.getElementById("ticketBox");

        const serviceMode = ticketData.service_mode || "quick";
        const tableLabel = ticketData.table_number || "Sin mesa";

        pills.innerHTML = `
          <div class="pill">Ticket: #${{ticketData.id}}</div>
          <div class="pill">Estado: ${{statusLabel(ticketData.status)}}</div>
          <div class="pill">Modo: ${{serviceMode}}</div>
          <div class="pill">Mesa: ${{tableLabel}}</div>
          <div class="pill">Pendientes: ${{ticketData.counts?.unsent || 0}}</div>
          <div class="pill">Enviados: ${{ticketData.counts?.sent || 0}}</div>
        `;

        const items = (ticketData.items || []).filter(it => Number(it.pending_quantity || 0) > 0);
        box.innerHTML = items.length ? items.map(it => `
          <div class="line-card">
            <div class="line-top">
              <div>
                <div class="line-name">${{it.product_name_snapshot || "Producto"}}</div>
                <div class="line-meta">Cant total: ${{Number(it.quantity || 0)}} · Pendiente: ${{Number(it.pending_quantity || 0)}} · Unit: ${{money(it.unit_price)}}</div>
                ${{it.notes ? `<div class="line-meta">Nota: ${{it.notes}}</div>` : ""}}
                <div class="badge ${{it.sent_to_kitchen ? "sent" : "unsent"}}">
                  ${{it.sent_to_kitchen ? "Enviado a cocina" : "Pendiente por enviar"}}
                </div>
              </div>
              <div class="line-total">${{money(it.total_price)}}</div>
            </div>
          </div>
        `).join("") : `<div class="empty">No hay productos agregados todavía.</div>`;

        document.getElementById("subtotalView").textContent = money(ticketData.subtotal);
        document.getElementById("taxView").textContent = money(ticketData.tax);
        document.getElementById("totalView").textContent = money(ticketData.total);
        renderSplitItems();
      }}

      async function addProductToTicket(productId) {{
        const res = await fetch(`/v2/api/local/ticket/${{currentOrderId}}/items/add?restaurant=${{ticketRestaurantSlug}}`, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{
            items: [
              {{
                product_id: Number(productId),
                quantity: 1,
                notes: ""
              }}
            ]
          }})
        }});

        const data = await res.json();
        if (!res.ok) {{
          alert(data.detail || "No se pudo agregar el producto.");
          return;
        }}

        ticketData = data.ticket;
        renderTicket();
        loadPayments();
      }}

      async function openBarFromTicket() {{
        const res = await fetch(`/v2/api/local/open-ticket?restaurant=${{ticketRestaurantSlug}}`, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{
            service_mode: "bar",
            customer_name: "",
            customer_phone: "",
            notes: ""
          }})
        }});

        const data = await res.json();
        if (!res.ok) {{
          alert(data.detail || "No se pudo abrir barra.");
          return;
        }}

        window.location.href = `/v2/pos/local/ticket/${{data.ticket.id}}?restaurant=${{ticketRestaurantSlug}}`;
      }}

      async function openQuickFromTicket() {{
        const res = await fetch(`/v2/api/local/open-ticket?restaurant=${{ticketRestaurantSlug}}`, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{
            service_mode: "quick",
            customer_name: "",
            customer_phone: "",
            notes: ""
          }})
        }});

        const data = await res.json();
        if (!res.ok) {{
          alert(data.detail || "No se pudo abrir venta rápida.");
          return;
        }}

        window.location.href = `/v2/pos/local/ticket/${{data.ticket.id}}?restaurant=${{ticketRestaurantSlug}}`;
      }}

      async function sendNewItems() {{
        const res = await fetch(`/v2/api/local/ticket/${{currentOrderId}}/send-new-items?restaurant=${{ticketRestaurantSlug}}`, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{}})
        }});

        const data = await res.json();
        if (!res.ok) {{
          alert(data.detail || "No se pudo enviar a cocina.");
          return;
        }}

        ticketData = data.ticket;
        renderTicket();
        loadPayments();
        alert(`Se enviaron ${{data.sent_count || 0}} productos nuevos a cocina.`);
      }}
      
      async function loadPayments() {{
        const res = await fetch(`/v2/api/local/ticket/${{currentOrderId}}/payments?restaurant=${{ticketRestaurantSlug}}`);
        const data = await res.json();

        if (!res.ok) {{
          console.error(data.detail || "No se pudieron cargar los pagos.");
          return;
        }}

        paymentsData = data;
        renderPayments();
      }}

      function renderPayments() {{
        const paid = Number(paymentsData?.paid_amount || 0);
        const balance = Number(paymentsData?.balance_due || 0);
        const items = paymentsData?.items || [];

        document.getElementById("paidAmountView").textContent = money(paid);
        document.getElementById("balanceDueView").textContent = money(balance);

        const box = document.getElementById("paymentsBox");
        box.innerHTML = items.length ? items.map(p => `
          <div class="line-card">
            <div class="line-top">
              <div>
                <div class="line-name">${{p.method || "Pago"}}</div>
                <div class="line-meta">Referencia: ${{p.reference || "-"}}</div>
                <div class="line-meta">Banco: ${{p.bank_name || "-"}} · Terminal: ${{p.terminal_id || "-"}}</div>
              </div>
              <div class="line-total">${{money(p.amount)}}</div>
            </div>
          </div>
        `).join("") : `<div class="empty">No hay pagos aplicados todavía.</div>`;
      }}

      function fillPendingBalance() {{
        const pending = Number(paymentsData?.balance_due || 0);
        document.getElementById("payAmount").value = pending > 0 ? pending.toFixed(2) : "0.00";
      }}

      async function chargeTicket() {{
        const payload = {{
          payments: [
            {{
              method: document.getElementById("payMethod").value || "cash",
              amount: Number(document.getElementById("payAmount").value || 0),
              reference: document.getElementById("payReference").value || "",
              bank_name: document.getElementById("payBank").value || "",
              terminal_id: document.getElementById("payTerminal").value || "",
              authorization_code: document.getElementById("payAuth").value || "",
              card_brand: "",
              card_last4: document.getElementById("payCardMeta").value || ""
            }}
          ]
        }};

        const res = await fetch(`/v2/api/local/ticket/${{currentOrderId}}/pay-split?restaurant=${{ticketRestaurantSlug}}`, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify(payload)
        }});

        const data = await res.json();
        if (!res.ok) {{
          alert(data.detail || "No se pudo aplicar el pago.");
          return;
        }}

        await loadTicket();
        await loadPayments();

        document.getElementById("payAmount").value = "";
        document.getElementById("payReference").value = "";
        document.getElementById("payBank").value = "";
        document.getElementById("payTerminal").value = "";
        document.getElementById("payAuth").value = "";
        document.getElementById("payCardMeta").value = "";

        alert(`Pago aplicado. Saldo pendiente: ${{money(data.balance_due)}}`);
      }}

      async function closeTicket(forceClose) {{
        const res = await fetch(`/v2/api/local/ticket/${{currentOrderId}}/close?restaurant=${{ticketRestaurantSlug}}`, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ force_close: !!forceClose }})
        }});

        const data = await res.json();
        if (!res.ok) {{
          alert(data.detail || "No se pudo cerrar el ticket.");
          return;
        }}

        alert("Ticket cerrado correctamente.");
        window.location.href = `/v2/pos/local/floor?restaurant=${{ticketRestaurantSlug}}`;
      }}
    
      function renderSplitItems() {{
        const box = document.getElementById("splitItemsBox");
        const items = (ticketData?.items || []).filter(it => Number(it.pending_quantity || 0) > 0);

        box.innerHTML = items.length ? items.map(it => `
          <div class="line-card">
            <div class="split-row">
              <input type="checkbox" class="split-check" data-item-id="${{it.id}}" />
              <div>
                <div class="line-name">${{it.product_name_snapshot || "Producto"}}</div>
                <div class="line-meta">
                  Pendiente: ${{Number(it.pending_quantity || 0)}} · Unit: ${{money(it.unit_price)}}
                </div>
              </div>
              <input
                type="number"
                min="0"
                step="0.01"
                value="${{Number(it.pending_quantity || 0)}}"
                class="split-qty"
                data-qty-id="${{it.id}}"
              />
            </div>
          </div>
        `).join("") : `<div class="empty">No hay líneas pendientes para split.</div>`;

        clearSplitSummary();
      }}

      function clearSplitSummary() {{
        document.getElementById("splitTotalView").textContent = "C$0.00";
        document.getElementById("splitBeforeView").textContent = money(paymentsData?.balance_due || 0);
        document.getElementById("splitAfterView").textContent = money(paymentsData?.balance_due || 0);
      }}

      function getSelectedSplitItems() {{
        const checks = [...document.querySelectorAll(".split-check:checked")];
        return checks.map(ch => {{
          const itemId = Number(ch.dataset.itemId);
          const qtyInput = document.querySelector(`[data-qty-id="${{itemId}}"]`);
          return {{
            order_item_id: itemId,
            quantity: Number(qtyInput?.value || 0)
          }};
        }}).filter(x => x.order_item_id && x.quantity > 0);
      }}

      async function previewSplitSelection() {{
        const selected = getSelectedSplitItems();
        if (!selected.length) {{
          alert("Selecciona al menos una línea para el split.");
          return;
        }}

        const res = await fetch(`/v2/api/local/ticket/${{currentOrderId}}/pay-items?restaurant=${{ticketRestaurantSlug}}`, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ items: selected }})
        }});

        const data = await res.json();
        if (!res.ok) {{
          alert(data.detail || "No se pudo calcular la selección.");
          return;
        }}

        splitPreviewData = data;
        document.getElementById("splitTotalView").textContent = money(data.split_total || 0);
        document.getElementById("splitBeforeView").textContent = money(data.balance_before || 0);
        document.getElementById("splitAfterView").textContent = money(data.balance_after || 0);
      }}

      async function paySplitSelection() {{
        const selected = getSelectedSplitItems();
        if (!selected.length) {{
          alert("Selecciona al menos una línea para pagar.");
          return;
        }}

        const payload = {{
          items: selected,
          method: document.getElementById("payMethod").value || "cash",
          reference: document.getElementById("payReference").value || "",
          bank_name: document.getElementById("payBank").value || "",
          terminal_id: document.getElementById("payTerminal").value || "",
          authorization_code: document.getElementById("payAuth").value || "",
          card_brand: "",
          card_last4: document.getElementById("payCardMeta").value || ""
        }};

        const res = await fetch(`/v2/api/local/ticket/${{currentOrderId}}/pay-selected-items?restaurant=${{ticketRestaurantSlug}}`, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify(payload)
        }});

        const data = await res.json();
        if (!res.ok) {{
          alert(data.detail || "No se pudo pagar la selección.");
          return;
        }}

        await loadTicket();
        await loadPayments();

        document.getElementById("payAmount").value = "";
        document.getElementById("payReference").value = "";
        document.getElementById("payBank").value = "";
        document.getElementById("payTerminal").value = "";
        document.getElementById("payAuth").value = "";
        document.getElementById("payCardMeta").value = "";

        alert(`Selección pagada. Saldo pendiente: ${{money(data.balance_due || 0)}}`);
      }}

       document.getElementById("searchProduct").addEventListener("input", renderProducts);
       document.getElementById("categorySelect").addEventListener("change", (e) => {{
        activeCategory = e.target.value;
        renderCategories();
        renderProducts();
      }});

      loadProducts();
      loadTicket();
      loadPayments();
    </script>
    """

    body = body.replace("__REST_SLUG__", str(rest.slug or ""))
    body = body.replace("__ORDER_ID__", str(order.id))
    return html_shell("POS Local Ticket", body)

@app.get("/v2/pos/local", response_class=HTMLResponse)
def v2_pos_local_redirect(
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)
    return HTMLResponse(
        f'<meta http-equiv="refresh" content="0; url=/v2/pos/local/floor?restaurant={rest.slug}">'
    )

@app.get("/v2/pos/delivery", response_class=HTMLResponse)
def v2_pos_delivery(restaurant: Optional[str] = Query(None), db: Session = Depends(get_db)):
    rest = get_restaurant_or_404(db, restaurant)

    body = """
    <style>
      .pos-shell {
        height: calc(100vh - 150px);
        display:grid;
        grid-template-columns: .9fr 1.15fr .95fr;
        gap:14px;
        overflow:hidden;
      }
      .panel {
        background:#fff; border:1px solid #d1d5db; border-radius:16px;
        box-shadow:0 2px 10px rgba(0,0,0,.05); overflow:hidden;
      }
      .panel-pad { padding:14px; }
      .topline {
        display:flex; justify-content:space-between; align-items:center;
        gap:10px; flex-wrap:wrap; margin-bottom:10px;
      }
      .title h1 { margin:0; font-size:22px; }
      .title p { margin:4px 0 0; color:#6b7280; }
      .pill-row { display:flex; gap:8px; flex-wrap:wrap; }
      .pill-lite {
        display:inline-flex; align-items:center; justify-content:center;
        padding:7px 11px; border-radius:999px; background:#f3f4f6;
        border:1px solid #d1d5db; font-size:12px; font-weight:700;
      }
      .mode-row {
        display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:10px;
      }
      .mode-btn {
        border:none; border-radius:10px; padding:10px 8px; font-weight:800; cursor:pointer;
        background:#e5e7eb; color:#111827;
      }
      .mode-btn.active { background:#0f172a; color:#fff; }
      .orders-list {
        max-height:calc(100vh - 270px);
        overflow:auto; display:grid; gap:8px;
      }
      .order-chip {
        border:1px solid #d1d5db; border-radius:12px; background:#fff;
        padding:10px; cursor:pointer;
      }
      .order-chip.active { border-color:#111827; background:#f8fafc; }
      .order-chip .top { display:flex; justify-content:space-between; gap:8px; font-weight:800; }
      .order-chip .sub { font-size:12px; color:#6b7280; margin-top:4px; }
      .field-grid {
        display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:10px;
      }
      .field label { display:block; font-size:12px; color:#6b7280; margin-bottom:4px; }
      .field input, .field textarea, .field select {
        width:100%; padding:9px 11px; border:1px solid #d1d5db; border-radius:10px; font:inherit;
      }
      .field textarea { min-height:42px; resize:vertical; }
      .field-row {
        display:grid; grid-template-columns:1fr 220px; gap:10px; margin-bottom:10px;
      }
      .category-tabs { display:flex; gap:8px; overflow:auto; padding-bottom:4px; margin-bottom:10px; }
      .category-btn {
        border:1px solid #cbd5e1; background:#f8fafc; border-radius:10px;
        padding:9px 12px; font-weight:700; cursor:pointer; white-space:nowrap;
      }
      .category-btn.active { background:#0f172a; color:#fff; border-color:#0f172a; }
      .products-grid {
        display:grid; grid-template-columns:repeat(auto-fill, minmax(125px, 1fr));
        gap:10px; max-height:calc(100vh - 500px); overflow:auto;
      }
      .product-btn {
        border:1px solid #cbd5e1; border-radius:14px; background:#fff;
        padding:12px; min-height:106px; cursor:pointer; display:grid; align-content:space-between; gap:8px;
      }
      .product-btn .name { font-weight:800; line-height:1.15; }
      .product-btn .category { font-size:12px; color:#6b7280; }
      .product-btn .price { font-weight:900; font-size:18px; }
      .right-shell { height:100%; display:grid; grid-template-rows:auto auto 1fr auto auto; gap:10px; }
      .ticket-meta { display:grid; grid-template-columns:1fr 1fr; gap:6px; font-size:13px; }
      .ticket-list {
        border:1px solid #e5e7eb; border-radius:14px; background:#fafafa;
        padding:10px; overflow:auto; min-height:220px; max-height:calc(100vh - 520px);
      }
      .ticket-empty { color:#6b7280; font-size:14px; }
      .ticket-line {
        border:1px solid #e5e7eb; border-radius:12px; background:#fff;
        padding:9px; margin-bottom:8px; cursor:pointer;
      }
      .ticket-line.selected { border-color:#111827; background:#f8fafc; }
      .ticket-line-top { display:flex; justify-content:space-between; gap:10px; font-weight:800; }
      .ticket-line-sub { font-size:12px; color:#6b7280; margin-top:4px; }
      .ticket-line-actions { display:flex; gap:6px; flex-wrap:wrap; margin-top:7px; }
      .mini-action {
        border:none; background:#e5e7eb; border-radius:8px; padding:5px 8px; font-weight:800; cursor:pointer;
      }
      .delivery-box {
        border:1px dashed #cbd5e1; border-radius:12px; background:#fafafa;
        padding:10px; display:grid; gap:6px; font-size:13px;
      }
      .summary-box { border-top:1px solid #e5e7eb; padding-top:8px; display:grid; gap:6px; }
      .summary-row { display:flex; justify-content:space-between; gap:10px; }
      .summary-total { font-size:28px; font-weight:900; }
      .pay-grid { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:8px; }
      .action-bar {
        display:grid; grid-template-columns:repeat(3, 1fr); gap:8px; margin-top:8px;
      }
      .action-btn {
        border:none; border-radius:10px; padding:10px 8px; font-weight:800; cursor:pointer;
      }
      .action-primary { background:#0f172a; color:#fff; }
      .action-accent { background:#2563eb; color:#fff; }
      .action-soft { background:#e5e7eb; color:#111827; }
      @media (max-width: 1350px) {
        .pos-shell {
          height: calc(100vh - 150px)
          display:grid;
          grid-template-columns: .9fr 1.15fr .95fr
          gap:14px;
          overflow:hidden;
        } 
        .orders-list, .products-grid, .ticket-list { max-height:320px; }
      }
       .panel-scroll {
         height:100%;
         overflow:auto;
         min-height:0;
         padding-right:4px;
       }

       .orders-list {
         max-height:none;
         overflow:auto;
         display:grid;
         gap:8px;
       }

       .products-grid {
         display:grid;
         grid-template-columns:repeat(auto-fill, minmax(125px, 1fr));
         gap:10px;
         max-height:none;
         overflow:auto;
         min-height:220px;
         padding-right:4px;
       }

       .ticket-list {
         border:1px solid #e5e7eb;
         border-radius:14px;
         background:#fafafa;
         padding:10px;
         overflow:auto;
         min-height:180px;
         max-height:none;
       }
    </style>

    <div class="topline">
      <div class="title">
        <h1>POS Delivery Pro</h1>
        <p>__REST_NAME__ · restaurant=__REST_SLUG__</p>
      </div>
      <div class="pill-row">
        <div class="pill-lite" id="activeUserBadge">Operador: OWNER</div>
        <div class="pill-lite">Canal: delivery</div>
        <a class="btn" href="/v2/menu?restaurant=__REST_SLUG__">Volver al menú</a>
      </div>
    </div>

    <div class="pos-shell">
      <div class="panel panel-pad panel-scroll">
        <div class="mode-row">
          <button class="mode-btn active" id="modeAutofillBtn" onclick="setMode('autofill')">Órdenes existentes</button>
          <button class="mode-btn" id="modeManualBtn" onclick="setMode('manual')">Manual</button>
        </div>

        <div class="pill-row" style="margin-bottom:8px;">
          <div class="pill-lite">Pendientes de cobro</div>
        </div>

        <div class="orders-list" id="deliveryOrdersBox">
          <div class="ticket-empty">Cargando órdenes...</div>
        </div>
      </div>

      <div class="panel panel-pad panel-scroll">
        <div class="field-grid">
          <div class="field">
            <label>Operador</label>
            <input id="server_name" value="OWNER">
          </div>
          <div class="field">
            <label>Cliente</label>
            <input id="customer_name" placeholder="Nombre del cliente">
          </div>
          <div class="field">
            <label>Teléfono</label>
            <input id="customer_phone" placeholder="Número">
          </div>
          <div class="field">
            <label>Zona / distrito</label>
            <input id="district_group" placeholder="Zona">
          </div>
          <div class="field">
            <label>Método de pago</label>
            <select id="payment_method">
              <option value="cash">Efectivo</option>
              <option value="transfer">Transferencia</option>
              <option value="card">Tarjeta</option>
              <option value="credit">Crédito</option>
            </select>
          </div>
          <div class="field">
            <label>Rider</label>
            <input id="driver_name" placeholder="Motorizado">
          </div>
        </div>

        <div class="field" style="margin-bottom:10px;">
          <label>Dirección</label>
          <textarea id="delivery_address" placeholder="Dirección completa"></textarea>
        </div>

        <div class="field" style="margin-bottom:10px;">
          <label>Notas</label>
          <textarea id="notes" placeholder="Notas generales"></textarea>
        </div>

        <div class="field-row">
          <div class="field">
            <label>Buscar producto</label>
            <input id="search_product" placeholder="Buscar por nombre..." oninput="renderProducts()">
          </div>
          <div class="field">
            <label>Categoría activa</label>
            <input id="active_category_view" value="Todas" readonly>
          </div>
        </div>

        <div class="category-tabs" id="categoryBar"></div>
        <div class="products-grid" id="productsBox"></div>
      </div>

      <div class="panel panel-pad right-shell">
        <div>
          <h2 style="margin:0 0 6px;">Ticket delivery</h2>
          <div class="ticket-meta">
            <div><strong>Restaurant:</strong> __REST_SLUG__</div>
            <div><strong>Canal:</strong> delivery</div>
            <div><strong>Cliente:</strong> <span id="ticketCustomerView">-</span></div>
            <div><strong>Operador:</strong> <span id="ticketServerView">OWNER</span></div>
          </div>
        </div>
 
        <div class="panel-scroll">
        <div class="delivery-box">
          <div><strong>Dirección:</strong> <span id="ticketAddressView">-</span></div>
          <div><strong>Zona:</strong> <span id="ticketDistrictView">-</span></div>
          <div><strong>Pago:</strong> <span id="ticketPaymentMethodView">cash</span></div>
          <div><strong>Rider:</strong> <span id="ticketDriverView">-</span></div>
          <div><strong>Promo:</strong> <span id="promoCodeView">-</span></div>
          <div><strong>Descuento:</strong> <span id="promoDiscountView">0%</span></div>
        </div>

        <div class="ticket-list" id="ticketBox">
          <div class="ticket-empty">No hay productos agregados.</div>
        </div>

        <div>
          <div class="summary-box">
            <div class="summary-row">
              <span>Subtotal</span>
              <strong id="subtotalView">C$0.00</strong>
            </div>
            <div class="summary-row">
              <span>Impuesto</span>
              <strong id="taxView">C$0.00</strong>
            </div>
            <div class="summary-row">
              <span>Total</span>
              <span id="totalView">C$0.00</span>
            </div>
          </div>

          <div class="pay-grid">
            <div class="field">
              <label>Monto recibido</label>
              <input id="pay_amount" type="number" step="0.01" value="0">
            </div>

            <div class="field">
              <label>Referencia</label>
              <input id="pay_reference" placeholder="Transferencia / tarjeta / nota">
            </div>
          </div>

          <div class="action-bar">
            <button class="action-btn action-primary" onclick="createManualOrder()">Crear manual</button>
            <button class="action-btn action-accent" onclick="paySelectedOrder()">Cobrar</button>
            <button class="action-btn action-soft" onclick="assignDriverInline()">Asignar rider</button>
            <button class="action-btn action-soft" onclick="sendToKitchenMock()">A cocina</button>
            <button class="action-btn action-soft" onclick="repeatSelectedItem()">Repetir</button>
            <button class="action-btn action-soft" onclick="removeSelectedLine()">Quitar línea</button>
          </div>
        </div>

        <div class="pill-row">
          <div class="pill-lite" id="itemsCount">0 items</div>
          <div class="pill-lite" id="selectedLineLabel">Línea: ninguna</div>
          <div class="pill-lite" id="modeBadge">Modo: autofill</div>
        </div>
       </div>

        <div id="resultBox"></div>
      </div>
    </div>

    <script>
      const restaurantSlug = "__REST_SLUG__";

      let products = [];
      let categories = [];
      let activeCategory = "Todas";
      let cart = [];
      let selectedLineIndex = null;
      let currentMode = "autofill";
      let currentOrderId = null;
      let lastCreatedOrderId = null;
      let pendingOrders = [];
      let selectedPromoCode = "";
      let selectedPromoDiscount = 0;

      function money(value) {
        return `C$${Number(value || 0).toFixed(2)}`;
      }

      function setMode(mode) {
        currentMode = mode;
        document.getElementById("modeAutofillBtn").classList.toggle("active", mode === "autofill");
        document.getElementById("modeManualBtn").classList.toggle("active", mode === "manual");
        document.getElementById("modeBadge").textContent = `Modo: ${mode}`;
      }

      async function loadProducts() {
        const res = await fetch(`/v2/api/products?restaurant=${restaurantSlug}`);
        const data = await res.json();
        products = data.items || [];
        categories = ["Todas", ...new Set(products.map(p => p.category || "General"))];
        renderCategories();
        renderProducts();
      }

      async function loadPendingOrders() {
        const res = await fetch(`/v2/api/delivery/pending?restaurant=${restaurantSlug}`);
        const data = await res.json();
        pendingOrders = data.items || [];

        const box = document.getElementById("deliveryOrdersBox");
        if (!pendingOrders.length) {
          box.innerHTML = "<div class='ticket-empty'>No hay órdenes delivery pendientes.</div>";
          return;
        }

        box.innerHTML = pendingOrders.map(o => `
          <div class="order-chip ${currentOrderId === o.id ? 'active' : ''}" onclick="selectExistingOrder(${o.id})">
            <div class="top">
              <span>#${o.id}</span>
              <span>${money(o.total)}</span>
            </div>
            <div class="sub">${o.customer_name || "Sin nombre"} · ${o.status || "-"}</div>
            <div class="sub">${o.customer_phone || "-"} · ${o.district_group || "-"}</div>
          </div>
        `).join("");
      }

      function renderCategories() {
        const bar = document.getElementById("categoryBar");
        bar.innerHTML = categories.map(cat => `
          <button class="category-btn ${cat === activeCategory ? 'active' : ''}" onclick="setCategory('${String(cat).replaceAll("'", "\\'")}')">
            ${cat}
          </button>
        `).join("");
        document.getElementById("active_category_view").value = activeCategory;
      }

      function setCategory(cat) {
        activeCategory = cat;
        renderCategories();
        renderProducts();
      }

      function renderProducts() {
        const q = (document.getElementById("search_product").value || "").toLowerCase().trim();
        let filtered = [...products];

        if (activeCategory !== "Todas") {
          filtered = filtered.filter(p => (p.category || "General") === activeCategory);
        }
        if (q) {
          filtered = filtered.filter(p => (p.name || "").toLowerCase().includes(q));
        }

        const box = document.getElementById("productsBox");
        if (!filtered.length) {
          box.innerHTML = "<div class='ticket-empty'>No hay productos en esta vista.</div>";
          return;
        }

        box.innerHTML = filtered.map(p => `
          <button class="product-btn" onclick="addProduct(${p.id})">
            <div>
              <div class="name">${p.name}</div>
              <div class="category">${p.category || ""}</div>
            </div>
            <div class="price">${money(p.price)}</div>
          </button>
        `).join("");
      }

      function addProduct(productId) {
        const product = products.find(p => Number(p.id) === Number(productId));
        if (!product) return;

        const existing = cart.find(item => Number(item.product_id) === Number(product.id));
        if (existing) {
          existing.quantity += 1;
        } else {
          cart.push({
            product_id: product.id,
            name: product.name,
            category: product.category || "",
            price: Number(product.price || 0),
            quantity: 1,
            special_notes: ""
          });
        }

        renderCart();
      }

      async function selectExistingOrder(orderId) {
        const res = await fetch(`/v2/api/orders/${orderId}/detail?restaurant=${restaurantSlug}`);
        const data = await res.json();

        if (!res.ok) {
          alert(data.detail || "No se pudo cargar la orden.");
          return;
        }

        const o = data.order || {};
        const items = data.items || [];

        currentOrderId = o.id;
        setMode("autofill");

        document.getElementById("server_name").value = o.operator_name || "OWNER";
        document.getElementById("customer_name").value = o.customer_name || "";
        document.getElementById("customer_phone").value = o.customer_phone || "";
        document.getElementById("district_group").value = o.district_group || "";
        document.getElementById("payment_method").value = o.payment_method || "cash";
        document.getElementById("driver_name").value = o.driver_name || "";
        document.getElementById("delivery_address").value = o.delivery_address || "";
        document.getElementById("notes").value = o.notes || "";
        document.getElementById("pay_amount").value = Number(o.total || 0).toFixed(2);

        selectedPromoCode = o.promo_code || "";
        selectedPromoDiscount = Number(o.discount_percent || 0);

        cart = items.map(it => ({
          product_id: it.product_id,
          name: it.name,
          category: it.category || "",
          price: Number(it.price || 0),
          quantity: Number(it.quantity || 0),
          special_notes: ""
        }));

        renderCart();
        loadPendingOrders();
      }

      function renderCart() {
        const box = document.getElementById("ticketBox");

        document.getElementById("ticketCustomerView").textContent =
          document.getElementById("customer_name").value || "-";

        document.getElementById("ticketServerView").textContent =
          document.getElementById("server_name").value || "OWNER";

        document.getElementById("ticketAddressView").textContent =
          document.getElementById("delivery_address").value || "-";

        document.getElementById("ticketDistrictView").textContent =
          document.getElementById("district_group").value || "-";

        document.getElementById("ticketPaymentMethodView").textContent =
          document.getElementById("payment_method").value || "cash";

        document.getElementById("ticketDriverView").textContent =
          document.getElementById("driver_name").value || "-";

        document.getElementById("promoCodeView").textContent =
          selectedPromoCode || "-";

        document.getElementById("promoDiscountView").textContent =
          `${Number(selectedPromoDiscount || 0).toFixed(2)}%`;

        document.getElementById("activeUserBadge").textContent =
          `Operador: ${document.getElementById("server_name").value || "OWNER"}`;

        if (!cart.length) {
          box.innerHTML = "<div class='ticket-empty'>No hay productos agregados.</div>";
          document.getElementById("itemsCount").textContent = "0 items";
          document.getElementById("selectedLineLabel").textContent = "Línea: ninguna";
          updateTotals();
          return;
        }

        box.innerHTML = cart.map((item, index) => `
          <div class="ticket-line ${selectedLineIndex === index ? 'selected' : ''}" onclick="selectLine(${index})">
            <div class="ticket-line-top">
              <span>${item.name}</span>
              <span>${money(item.price * item.quantity)}</span>
            </div>
            <div class="ticket-line-sub">Cant: ${item.quantity} · ${item.category || ""}</div>
            <div class="ticket-line-actions">
              <button class="mini-action" onclick="event.stopPropagation(); changeQty(${index}, -1)">-</button>
              <button class="mini-action" onclick="event.stopPropagation(); changeQty(${index}, 1)">+</button>
              <button class="mini-action" onclick="event.stopPropagation(); addSpecialNote(${index})">Nota</button>
            </div>
          </div>
        `).join("");

        const totalQty = cart.reduce((acc, item) => acc + Number(item.quantity || 0), 0);
        document.getElementById("itemsCount").textContent = `${totalQty} items`;

        const current = cart[selectedLineIndex];
        document.getElementById("selectedLineLabel").textContent =
          current ? `Línea: ${current.name}` : "Línea: ninguna";

        updateTotals();
      }

      function selectLine(index) {
        selectedLineIndex = index;
        renderCart();
      }

      function changeQty(index, diff) {
        if (!cart[index]) return;
        cart[index].quantity += diff;
        if (cart[index].quantity <= 0) {
          cart.splice(index, 1);
          if (selectedLineIndex === index) selectedLineIndex = null;
        }
        renderCart();
      }

      function addSpecialNote(index) {
        if (!cart[index]) return;
        const current = cart[index].special_notes || "";
        const note = window.prompt("Nota especial para este ítem:", current);
        if (note === null) return;
        cart[index].special_notes = note.trim();
        renderCart();
      }

      function repeatSelectedItem() {
        if (selectedLineIndex === null || !cart[selectedLineIndex]) {
          alert("Selecciona una línea primero.");
          return;
        }
        const item = cart[selectedLineIndex];
        cart.push({
          product_id: item.product_id,
          name: item.name,
          category: item.category,
          price: item.price,
          quantity: item.quantity,
          special_notes: item.special_notes || ""
        });
        renderCart();
      }

      function removeSelectedLine() {
        if (selectedLineIndex === null || !cart[selectedLineIndex]) {
          alert("Selecciona una línea primero.");
          return;
        }
        cart.splice(selectedLineIndex, 1);
        selectedLineIndex = null;
        renderCart();
      }

      function currentSubtotal() {
        return cart.reduce((acc, item) => acc + (Number(item.price || 0) * Number(item.quantity || 0)), 0);
      }

      function currentTax() {
        return currentSubtotal() * 0.15;
      }

      function currentTotal() {
        return currentSubtotal() + currentTax();
      }

      function updateTotals() {
        document.getElementById("subtotalView").textContent = money(currentSubtotal());
        document.getElementById("taxView").textContent = money(currentTax());
        document.getElementById("totalView").textContent = money(currentOrderId ? Number(document.getElementById("pay_amount").value || 0) : currentTotal());
      }

      function buildManualPayload() {
        const notesText = [
          document.getElementById("notes").value || "",
          `Dirección: ${document.getElementById("delivery_address").value || ""}`,
          `Zona: ${document.getElementById("district_group").value || ""}`,
          `Pago: ${document.getElementById("payment_method").value || "cash"}`,
          `Repartidor: ${document.getElementById("driver_name").value || ""}`,
          `Operador: ${document.getElementById("server_name").value || "OWNER"}`,
          selectedPromoCode ? `PromoCode: ${selectedPromoCode}` : "",
          Number(selectedPromoDiscount || 0) > 0 ? `DiscountPercent: ${Number(selectedPromoDiscount).toFixed(2)}` : ""
        ].filter(Boolean).join(" | ");

        return {
          channel: "delivery",
          customer_name: document.getElementById("customer_name").value || "",
          customer_phone: document.getElementById("customer_phone").value || "",
          table_number: "",
          notes: notesText,
          items: cart.map(item => ({
            product_id: item.product_id,
            quantity: item.quantity
          }))
        };
      }

      async function createManualOrder() {
        if (currentMode !== "manual") {
          alert("Para crear manual, cambia a modo manual.");
          return;
        }
        if (!cart.length) {
          alert("Agrega productos al ticket.");
          return;
        }

        const payload = buildManualPayload();
        const res = await fetch(`/v2/api/orders/create?restaurant=${restaurantSlug}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const data = await res.json();

        if (!res.ok) {
          alert(data.detail || "No se pudo crear la orden manual.");
          return;
        }

        currentOrderId = data.order.id;
        lastCreatedOrderId = data.order.id;
        document.getElementById("pay_amount").value = Number(data.order.total || 0).toFixed(2);

        document.getElementById("resultBox").innerHTML = `
          <div style="padding:12px;border:1px solid #bbf7d0;background:#f0fdf4;border-radius:12px;">
            Orden manual creada.<br>
            ID: ${data.order.id}<br>
            Total: ${money(data.order.total)}
          </div>
        `;

        loadPendingOrders();
      }

      async function paySelectedOrder() {
        const targetId = currentOrderId || lastCreatedOrderId;
        if (!targetId) {
          alert("Selecciona una orden existente o crea una manual.");
          return;
        }

        const payload = {
          method: document.getElementById("payment_method").value || "cash",
          amount: parseFloat(document.getElementById("pay_amount").value || "0"),
          reference: document.getElementById("pay_reference").value || ""
        };

        const res = await fetch(`/v2/api/orders/${targetId}/pay?restaurant=${restaurantSlug}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        const data = await res.json();

        if (!res.ok) {
          alert(data.detail || "No se pudo cobrar la orden.");
          return;
        }

        document.getElementById("resultBox").innerHTML = `
          <div style="padding:12px;border:1px solid #bfdbfe;background:#eff6ff;border-radius:12px;">
            Orden cobrada correctamente.<br>
            ID: ${data.order_id}<br>
            Método: ${data.method}<br>
            Pagado: ${money(data.paid_amount)}<br>
            Vuelto: ${money(data.change)}
          </div>
        `;

        loadPendingOrders();
      }

      function assignDriverInline() {
        const current = document.getElementById("driver_name").value || "";
        const value = window.prompt("Asignar rider:", current);
        if (value === null) return;
        document.getElementById("driver_name").value = value.trim();
        renderCart();
      }

      async function sendToKitchenMock() {

        if (!lastCreatedOrderId) {
          alert("Primero crea la orden.");
          return;
        }

        const res = await fetch(`/v2/api/kitchen/orders/${lastCreatedOrderId}/status?restaurant=${restaurantSlug}&status=preparing`, {
          method: "POST"
        });

        const data = await res.json();

        if (!res.ok) {
          alert(data.detail || "No se pudo enviar a cocina.");
          return;
        }

        document.getElementById("resultBox").innerHTML = `
          <div style="padding:12px;border:1px solid #fde68a;background:#fffbeb;border-radius:12px;">
            Orden enviada a cocina.<br>
            ID: ${data.order.id}<br>
            Estado: ${data.order.status}
          </div>
        `; 
      }

      document.getElementById("server_name").addEventListener("input", renderCart);
      document.getElementById("customer_name").addEventListener("input", renderCart);
      document.getElementById("delivery_address").addEventListener("input", renderCart);
      document.getElementById("district_group").addEventListener("input", renderCart);
      document.getElementById("payment_method").addEventListener("change", renderCart);
      document.getElementById("driver_name").addEventListener("input", renderCart);

      loadProducts();
      loadPendingOrders();
      renderCart();
    </script>
    """
    body = body.replace("__REST_NAME__", str(rest.name or "")).replace("__REST_SLUG__", str(rest.slug or ""))
    return html_shell("POS Delivery Pro", body)

@app.get("/v2/kitchen", response_class=HTMLResponse)
def v2_kitchen(restaurant: Optional[str] = Query(None), db: Session = Depends(get_db)):
    rest = get_restaurant_or_404(db, restaurant)

    body = """
<style>
.kds-shell{
  min-height:calc(100vh - 120px);
  display:grid;
  grid-template-columns:260px 1fr;
  gap:16px;
}
.kds-panel{
  background:#fff;
  border:1px solid #e5e7eb;
  border-radius:16px;
  padding:16px;
  box-sizing:border-box;
}
.kds-title{
  font-size:28px;
  font-weight:800;
  margin:0 0 4px;
}
.kds-sub{
  color:#6b7280;
  font-size:14px;
  margin-bottom:14px;
}
.kds-filter{
  display:flex;
  flex-direction:column;
  gap:10px;
  margin-bottom:14px;
}
.kds-filter button{
  border:none;
  background:#eef2ff;
  color:#1f2937;
  font-weight:700;
  border-radius:10px;
  padding:12px 14px;
  cursor:pointer;
  text-align:left;
}
.kds-filter button.active{
  background:#111827;
  color:#fff;
}
.kds-board{
  display:grid;
  grid-template-columns:repeat(auto-fill,minmax(320px,1fr));
  gap:14px;
}
.kds-card{
  border:1px solid #dbe2ea;
  border-radius:16px;
  background:#fff;
  padding:14px;
  box-sizing:border-box;
}
.kds-card-top{
  display:flex;
  justify-content:space-between;
  gap:10px;
  margin-bottom:10px;
}
.kds-badge{
  display:inline-block;
  padding:6px 10px;
  border-radius:999px;
  font-size:12px;
  font-weight:800;
  background:#eef2ff;
}
.kds-meta{
  font-size:13px;
  color:#4b5563;
  line-height:1.45;
}
.kds-items{
  margin-top:10px;
  border-top:1px dashed #d1d5db;
  padding-top:10px;
  display:flex;
  flex-direction:column;
  gap:8px;
}
.kds-item{
  border:1px solid #edf2f7;
  border-radius:12px;
  padding:10px;
  background:#fafafa;
}
.kds-item strong{
  display:block;
  margin-bottom:4px;
}
.kds-actions{
  display:grid;
  grid-template-columns:repeat(2,1fr);
  gap:8px;
  margin-top:12px;
}
.kds-actions button{
  border:none;
  border-radius:10px;
  padding:10px 12px;
  font-weight:800;
  cursor:pointer;
}
.kds-btn-pending{ background:#e5e7eb; }
.kds-btn-preparing{ background:#fde68a; }
.kds-btn-ready{ background:#93c5fd; }
.kds-btn-delivered{ background:#86efac; }
.kds-empty{
  border:1px dashed #cbd5e1;
  border-radius:16px;
  padding:24px;
  text-align:center;
  color:#6b7280;
  background:#fff;
}
.kds-result{
  margin-top:14px;
  padding:12px;
  border:1px solid #dbeafe;
  background:#eff6ff;
  border-radius:12px;
  display:none;
}
</style>

<div class="kds-shell">
  <div class="kds-panel">
    <h1 class="kds-title">Kitchen Display</h1>
    <div class="kds-sub">__REST_NAME__ · restaurant=__REST_SLUG__</div>

    <div class="kds-filter">

    <div style="font-size:13px;font-weight:700;margin-bottom:6px;">Canal</div>

    <button class="active" onclick="setKitchenChannel('all', this)">Todos</button>
    <button onclick="setKitchenChannel('local', this)">Local</button>
    <button onclick="setKitchenChannel('delivery', this)">Delivery</button>

    <hr style="margin:10px 0;border:none;border-top:1px solid #e5e7eb;">

    <div style="font-size:13px;font-weight:700;margin-bottom:6px;">Estado</div>

    <button class="active" onclick="setKitchenFilter('all', this)">Todas</button>
    <button onclick="setKitchenFilter('pending', this)">Pendientes</button>
    <button onclick="setKitchenFilter('preparing', this)">Preparando</button>
    <button onclick="setKitchenFilter('ready', this)">Listas</button>
    <button onclick="setKitchenFilter('delivered', this)">Entregadas</button>

    </div>

    <div class="kds-result" id="kdsResultBox"></div>
  </div>

  <div>
    <div class="kds-board" id="kdsBoard"></div>
  </div>
</div>

<script>
const kitchenRestaurantSlug = "__REST_SLUG__";
let kitchenStatusFilter = "all";
let kitchenChannelFilter = "all";

function kitchenStatusBadge(status){
  const map = {
    pending: "Pendiente",
    preparing: "Preparando",
    ready: "Lista",
    delivered: "Entregada"
  };
  return map[status] || status || "Pendiente";
}

function money(v){
  const n = Number(v || 0);
  return "C$" + n.toFixed(2);
}

function setKitchenFilter(status, btn){
  kitchenStatusFilter = status;
  document.querySelectorAll(".kds-filter button").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  loadKitchenOrders();
}

function setKitchenChannel(channel, btn){
  kitchenChannelFilter = channel;

  document.querySelectorAll(".kds-filter button").forEach(b=>{
    if(b.innerText==="Todos" || b.innerText==="Local" || b.innerText==="Delivery"){
      b.classList.remove("active");
    }
  });

  btn.classList.add("active");
  loadKitchenOrders();
}

async function loadKitchenOrders(){
  let url = `/v2/api/kitchen/orders?restaurant=${kitchenRestaurantSlug}`;
  if(kitchenChannelFilter !== "all"){
    url += `&channel=${kitchenChannelFilter}`;
  }
  
  if(kitchenStatusFilter !== "all"){
    url += `&status=${kitchenStatusFilter}`;
  }

  const res = await fetch(url);
  const data = await res.json();

  const board = document.getElementById("kdsBoard");
  board.innerHTML = "";

  const items = (data && data.items) ? data.items : [];

  if(!items.length){
    board.innerHTML = `<div class="kds-empty">No hay órdenes en este filtro.</div>`;
    return;
  }

  for(const order of items){
    const card = document.createElement("div");
    card.className = "kds-card";

    const orderItems = (order.items || []).map(it => `
      <div class="kds-item">
        <strong>${it.product_name_snapshot || "Producto"}</strong>
        <div class="kds-meta">Cant: ${it.quantity} · ${money(it.total_price)}</div>
        ${it.notes ? `<div class="kds-meta">Nota: ${it.notes}</div>` : ""}
      </div>
    `).join("");

    card.innerHTML = `
      <div class="kds-card-top">
        <div>
          <div style="font-size:22px;font-weight:800;">Orden #${order.id}</div>
          <div class="kds-meta">Canal: ${order.channel || "-"} · Estado: ${kitchenStatusBadge(order.status)}</div>
        </div>
        <div class="kds-badge">${kitchenStatusBadge(order.status)}</div>
      </div>

      <div class="kds-meta">
        Cliente: ${order.customer_name || "-"}<br>
        Teléfono: ${order.customer_phone || "-"}<br>
        Mesa: ${order.table_number || "-"}<br>
        Total: ${money(order.total)}
      </div>

      ${order.notes ? `<div class="kds-meta" style="margin-top:8px;"><strong>Notas:</strong> ${order.notes}</div>` : ""}

      <div class="kds-items">${orderItems || `<div class="kds-empty">Sin items.</div>`}</div>

      <div class="kds-actions">
        <button class="kds-btn-pending" onclick="updateKitchenStatus(${order.id}, 'pending')">Pendiente</button>
        <button class="kds-btn-preparing" onclick="updateKitchenStatus(${order.id}, 'preparing')">Preparando</button>
        <button class="kds-btn-ready" onclick="updateKitchenStatus(${order.id}, 'ready')">Lista</button>
        <button class="kds-btn-delivered" onclick="updateKitchenStatus(${order.id}, 'delivered')">Entregada</button>
      </div>
    `;

    board.appendChild(card);
  }
}

async function updateKitchenStatus(orderId, status){
  const res = await fetch(`/v2/api/kitchen/orders/${orderId}/status?restaurant=${kitchenRestaurantSlug}&status=${status}`, {
    method: "POST"
  });

  const data = await res.json();
  const box = document.getElementById("kdsResultBox");
  box.style.display = "block";

  if(!res.ok){
    box.innerHTML = `No se pudo actualizar la orden.`;
    return;
  }

  box.innerHTML = `Orden #${data.order.id} actualizada a: <strong>${kitchenStatusBadge(data.order.status)}</strong>`;
  loadKitchenOrders();
}

loadKitchenOrders();
setInterval(loadKitchenOrders, 8000);
</script>
"""

    body = body.replace("__REST_NAME__", str(rest.name or "")).replace("__REST_SLUG__", str(rest.slug or ""))
    return html_shell("Kitchen Display", body)

@app.get("/v2/api/kitchen/orders")
def v2_api_kitchen_orders(
    restaurant: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = None

    if restaurant:
        rest = db.query(Restaurant).filter(Restaurant.slug == str(restaurant).strip()).first()

    if not rest:
        print("⚠️ Kitchen fallback: restaurant not found for slug =", restaurant)
        rest = db.query(Restaurant).filter(Restaurant.slug == "deaca").first()

    if not rest:
        return JSONResponse(
            {"ok": False, "error": "Restaurant not found"},
            status_code=404
        )

    query = db.query(Order).filter(Order.restaurant_id == rest.id)

    if status:
        query = query.filter(Order.status == status)

    if channel:
        query = query.filter(Order.channel == channel)

    rows = query.order_by(Order.id.desc()).limit(100).all()

    return {
        "ok": True,
        "restaurant": rest.slug,
        "items": [
            {
                "id": o.id,
                "channel": o.channel,
                "status": o.status,
                "customer_name": o.customer_name or "",
                "customer_phone": o.customer_phone or "",
                "table_number": o.table_number or "",
                "subtotal": float(o.subtotal or 0),
                "tax": float(o.tax or 0),
                "total": float(o.total or 0),
                "payment_status": o.payment_status or "",
                "notes": o.notes or "",
                "created_at": str(o.created_at or ""),
                "items": [
                    {
                        "id": it.id,
                        "product_id": it.product_id,
                        "product_name_snapshot": it.product_name_snapshot or "",
                        "quantity": float(it.quantity or 0),
                        "unit_price": float(it.unit_price or 0),
                        "total_price": float(it.total_price or 0),
                        "notes": it.notes or "",
                    }
                    for it in (o.items or [])
                ],
            }
            for o in rows
        ],
    }


@app.post("/v2/api/kitchen/orders/{order_id}/status")
def v2_api_kitchen_update_status(
    order_id: int,
    status: str = Query(...),
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    order = (
        db.query(Order)
        .filter(
            Order.id == order_id,
            Order.restaurant_id == rest.id,
        )
        .first()
    )

    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada.")

    allowed = {"pending", "preparing", "ready", "delivered"}
    new_status = (status or "").strip().lower()

    if new_status not in allowed:
        raise HTTPException(status_code=400, detail="Estado inválido.")

    order.status = new_status
    db.commit()
    db.refresh(order)

    return {
        "ok": True,
        "order": {
            "id": order.id,
            "status": order.status,
            "channel": order.channel,
            "payment_status": order.payment_status or "",
        },
    }

@app.get("/v2/cash", response_class=HTMLResponse)
def v2_cash(restaurant: Optional[str] = Query(None), db: Session = Depends(get_db)):
    rest = get_restaurant_or_404(db, restaurant)
    return placeholder_page(
        "Caja",
        rest.slug,
        "Aquí conectaremos apertura, movimientos y cierre de caja en el Bloque 9.",
    )


@app.get("/v2/inventory", response_class=HTMLResponse)
def v2_inventory(restaurant: Optional[str] = Query(None), db: Session = Depends(get_db)):
    rest = get_restaurant_or_404(db, restaurant)
    return placeholder_page(
        "Inventario",
        rest.slug,
        "Aquí conectaremos productos, recetas y kardex en el Bloque 10.",
    )


@app.get("/v2/hr", response_class=HTMLResponse)
def v2_hr(restaurant: Optional[str] = Query(None), db: Session = Depends(get_db)):
    rest = get_restaurant_or_404(db, restaurant)
    return placeholder_page(
        "RRHH",
        rest.slug,
        "Aquí conectaremos empleados, asistencia, vacaciones y liquidaciones en el Bloque 11.",
    )


@app.get("/v2/analytics", response_class=HTMLResponse)
def v2_analytics(restaurant: Optional[str] = Query(None), db: Session = Depends(get_db)):
    rest = get_restaurant_or_404(db, restaurant)
    return placeholder_page(
        "Analytics",
        rest.slug,
        "Aquí conectaremos dashboards y métricas en el Bloque 12.",
    )

DEFAULT_TENANT_CONFIG = {
    "payment_methods": {
        "cash": True,
        "card": True,
        "transfer": True,
        "credit": False,
    },
    "service_modes": {
        "table": True,
        "bar": True,
        "quick": True,
        "delivery": True,
        "pickup": True,
        "whatsapp": True,
    },
    "whatsapp": {
    "brand_title": "DEACA POS",
    "main_menu": [
        {"id": "menu", "title": "Menú", "description": "Ver categorías disponibles", "enabled": True},
        {"id": "order", "title": "Pedir", "description": "Iniciar pedido", "enabled": True},
        {"id": "cart", "title": "Carrito", "description": "Ver carrito actual", "enabled": True},
        {"id": "location_hours", "title": "Ubicación y horario", "description": "Ver dirección y horario", "enabled": True},
        {"id": "advisor", "title": "Asesor", "description": "Hablar con un asesor", "enabled": True},
        {"id": "clear_order", "title": "Borrar orden", "description": "Vaciar pedido actual", "enabled": True},
    ],
    "category_menu": [
        {"id": "desayunos", "title": "Desayunos", "description": "Ver opciones", "image_url": "", "enabled": True},
        {"id": "almuerzos", "title": "Almuerzos", "description": "Elegí plato + acompañamientos", "image_url": "", "enabled": True},
        {"id": "fritangas", "title": "Fritangas", "description": "Elegí plato + acompañamientos", "image_url": "", "enabled": True},
        {"id": "bebidas", "title": "Bebidas", "description": "Frescos, cacao y café", "image_url": "", "enabled": True},
        {"id": "extras", "title": "Extras", "description": "Agregar adicionales", "image_url": "", "enabled": True},
    ],
    "flow": {
        "ask_name": True,
        "ask_fulfillment_type": True,
        "ask_location_for_delivery": True,
        "ask_written_address": True,
        "ask_district": True,
        "ask_payment_method": True,
        "ask_order_confirmation": True,
    },
    "messages": {
        "welcome": "👋 Bienvenido a DEACA POS",
        "choose_option": "Elegí una opción:",
        "choose_category": "📋 Menú — elegí categoría",
        "choose_product": "Tocá para elegir",
        "cart_prefix": "🧺 Tu carrito:",
        "delivery_notice": "🚚 El envío tiene un costo adicional.",
        "ask_proceed_delivery": "¿Procedemos con tus datos?",
        "ask_address": "📍 Escribí tu dirección completa (y referencia si querés):",
        "ask_district": "📍 ¿A qué distrito pertenece tu dirección?",
        "ask_payment_method": "Método de pago:",
        "confirm_order": "¿Confirmás el pedido?",
        "advisor": "Un asesor te atenderá en breve.",
        "cancel": "Tu pedido fue cancelado.",
        "received": "✅ Pedido recibido y guardado.",
     }
   }
}


def get_restaurant_setting_value(
    db: Session,
    restaurant_id: int,
    key: str,
    default=None,
):
    row = (
        db.query(RestaurantSetting)
        .filter(
            RestaurantSetting.restaurant_id == restaurant_id,
            RestaurantSetting.setting_key == key,
        )
        .first()
    )
    if not row:
        return default
    raw = row.setting_value or ""
    try:
        return json.loads(raw)
    except Exception:
        return raw if raw != "" else default


def set_restaurant_setting_value(
    db: Session,
    restaurant_id: int,
    key: str,
    value,
):
    row = (
        db.query(RestaurantSetting)
        .filter(
            RestaurantSetting.restaurant_id == restaurant_id,
            RestaurantSetting.setting_key == key,
        )
        .first()
    )
    raw = json.dumps(value, ensure_ascii=False)
    if row:
        row.setting_value = raw
    else:
        row = RestaurantSetting(
            restaurant_id=restaurant_id,
            setting_key=key,
            setting_value=raw,
        )
        db.add(row)
    return row


class TenantConfigInput(BaseModel):
    payment_methods: Dict = {}
    service_modes: Dict = {}
    whatsapp: Dict = {}

class WhatsAppSessionStartInput(BaseModel):
    phone: str
    customer_name: str = ""


class WhatsAppCartItemInput(BaseModel):
    phone: str
    product_id: int
    quantity: Decimal = Field(default=Decimal("1"))


class WhatsAppCartRemoveInput(BaseModel):
    phone: str
    product_id: int
    quantity: Decimal = Field(default=Decimal("1"))


class WhatsAppCartReadInput(BaseModel):
    phone: str

class WhatsAppDeliveryInput(BaseModel):
    phone: str
    lat: float
    lng: float
    address: str
    district: str


class DeliveryConfigInput(BaseModel):
    origin_lat: float
    origin_lng: float
    origin_address: str
    price_per_km: float

@app.get("/v2/api/admin/config")
def v2_api_admin_config(
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    payment_methods = get_restaurant_setting_value(
        db, rest.id, "payment_methods", DEFAULT_TENANT_CONFIG["payment_methods"]
    )
    service_modes = get_restaurant_setting_value(
        db, rest.id, "service_modes", DEFAULT_TENANT_CONFIG["service_modes"]
    )
    whatsapp = get_tenant_whatsapp_config(db, rest.id)

    return {
        "ok": True,
        "restaurant": rest.slug,
        "config": {
            "payment_methods": payment_methods,
            "service_modes": service_modes,
            "whatsapp": whatsapp,
        },
    }

@app.post("/v2/api/admin/config")
def v2_api_admin_config_save(
    payload: TenantConfigInput,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    current_payment_methods = get_restaurant_setting_value(
        db, rest.id, "payment_methods", DEFAULT_TENANT_CONFIG["payment_methods"]
    )
    current_service_modes = get_restaurant_setting_value(
        db, rest.id, "service_modes", DEFAULT_TENANT_CONFIG["service_modes"]
    )
    current_whatsapp = get_tenant_whatsapp_config(db, rest.id)

    merged_payment_methods = dict(current_payment_methods or {})
    merged_service_modes = dict(current_service_modes or {})
    merged_whatsapp = dict(current_whatsapp or {})

    if payload.payment_methods is not None:
        merged_payment_methods.update(payload.payment_methods)

    if payload.service_modes is not None:
        merged_service_modes.update(payload.service_modes)

    if payload.whatsapp is not None:
        merged_whatsapp.update(payload.whatsapp)

    set_restaurant_setting_value(db, rest.id, "payment_methods", merged_payment_methods)
    set_restaurant_setting_value(db, rest.id, "service_modes", merged_service_modes)
    set_restaurant_setting_value(db, rest.id, "whatsapp", merged_whatsapp)

    db.commit()

    return {
        "ok": True,
        "restaurant": rest.slug,
        "config": {
            "payment_methods": merged_payment_methods,
            "service_modes": merged_service_modes,
            "whatsapp": merged_whatsapp,
        },
    }
def get_tenant_whatsapp_config(db: Session, rest_id: int) -> dict:
    data = get_restaurant_setting_value(
        db,
        rest_id,
        "whatsapp",
        DEFAULT_TENANT_CONFIG["whatsapp"],
    )

    defaults = DEFAULT_TENANT_CONFIG["whatsapp"]

    base = {
        "brand_title": defaults.get("brand_title", ""),
        "main_menu": [dict(x) for x in defaults.get("main_menu", [])],
        "category_menu": [dict(x) for x in defaults.get("category_menu", [])],
        "flow": dict(defaults.get("flow", {})),
        "messages": dict(defaults.get("messages", {})),
    }

    if not isinstance(data, dict):
        return base

    old_keys = {
        "welcome_message",
        "menu_intro",
        "cart_summary_prefix",
        "confirm_message",
        "order_received_message",
        "advisor_message",
        "cancel_message",
    }

    # Migración de formato viejo -> nuevo
    if any(k in data for k in old_keys):
        migrated = {
            "brand_title": defaults.get("brand_title", ""),
            "main_menu": [dict(x) for x in defaults.get("main_menu", [])],
            "category_menu": [dict(x) for x in defaults.get("category_menu", [])],
            "flow": dict(defaults.get("flow", {})),
            "messages": dict(defaults.get("messages", {})),
        }

        if isinstance(data.get("welcome_message"), str) and data.get("welcome_message").strip():
            migrated["messages"]["welcome"] = data["welcome_message"].strip()

        if isinstance(data.get("menu_intro"), str) and data.get("menu_intro").strip():
            migrated["messages"]["choose_category"] = data["menu_intro"].strip()

        if isinstance(data.get("cart_summary_prefix"), str) and data.get("cart_summary_prefix").strip():
            migrated["messages"]["cart_prefix"] = data["cart_summary_prefix"].strip()

        if isinstance(data.get("confirm_message"), str) and data.get("confirm_message").strip():
            migrated["messages"]["confirm_order"] = data["confirm_message"].strip()

        if isinstance(data.get("order_received_message"), str) and data.get("order_received_message").strip():
            migrated["messages"]["received"] = data["order_received_message"].strip()

        if isinstance(data.get("advisor_message"), str) and data.get("advisor_message").strip():
            migrated["messages"]["advisor"] = data["advisor_message"].strip()

        if isinstance(data.get("cancel_message"), str) and data.get("cancel_message").strip():
            migrated["messages"]["cancel"] = data["cancel_message"].strip()

        return migrated

    # Formato nuevo
    if isinstance(data.get("brand_title"), str):
        base["brand_title"] = data["brand_title"]

    if isinstance(data.get("main_menu"), list):
        base["main_menu"] = data["main_menu"]

    if isinstance(data.get("category_menu"), list):
        base["category_menu"] = data["category_menu"]

    if isinstance(data.get("flow"), dict):
        base["flow"].update(data["flow"])

    if isinstance(data.get("messages"), dict):
        base["messages"].update(data["messages"])

    return base

def get_tenant_payment_methods(db: Session, rest_id: int) -> dict:
    data = get_restaurant_setting_value(
        db,
        rest_id,
        "payment_methods",
        DEFAULT_TENANT_CONFIG["payment_methods"],
    )
    return data or dict(DEFAULT_TENANT_CONFIG["payment_methods"])


def get_tenant_service_modes(db: Session, rest_id: int) -> dict:
    data = get_restaurant_setting_value(
        db,
        rest_id,
        "service_modes",
        DEFAULT_TENANT_CONFIG["service_modes"],
    )
    return data or dict(DEFAULT_TENANT_CONFIG["service_modes"])

def get_whatsapp_catalog_visibility_map(db: Session, rest_id: int) -> dict:
    data = get_restaurant_setting_value(
        db,
        rest_id,
        "whatsapp_catalog_visibility",
        {},
    )
    return data or {}

def normalize_phone(value: str) -> str:
    raw = (value or "").strip()
    return "".join(ch for ch in raw if ch.isdigit() or ch == "+")


def get_whatsapp_session_key(phone: str) -> str:
    return f"wa_session::{normalize_phone(phone)}"


def get_whatsapp_cart_key(phone: str) -> str:
    return f"wa_cart::{normalize_phone(phone)}"


def get_whatsapp_session(db: Session, rest_id: int, phone: str) -> dict:
    key = get_whatsapp_session_key(phone)
    data = get_restaurant_setting_value(db, rest_id, key, {})
    return data or {}


def set_whatsapp_session(db: Session, rest_id: int, phone: str, data: dict):
    key = get_whatsapp_session_key(phone)
    set_restaurant_setting_value(db, rest_id, key, data or {})

def set_whatsapp_state(db: Session, rest_id: int, phone: str, state: str, extra: dict = None):
    session_data = get_whatsapp_session(db, rest_id, phone) or {}

    session_data["phone"] = phone
    session_data["state"] = state
    session_data["updated_at"] = datetime.utcnow().isoformat()

    if extra and isinstance(extra, dict):
        session_data.update(extra)

    set_whatsapp_session(db, rest_id, phone, session_data)
    return session_data

def clear_whatsapp_cart(db: Session, rest_id: int, phone: str):
    session_data = get_whatsapp_session(db, rest_id, phone) or {}
    session_data["cart"] = []
    session_data["updated_at"] = datetime.utcnow().isoformat()
    set_whatsapp_session(db, rest_id, phone, session_data)
    return session_data

def get_whatsapp_cart(db: Session, rest_id: int, phone: str) -> dict:
    key = get_whatsapp_cart_key(phone)
    data = get_restaurant_setting_value(db, rest_id, key, {"items": []})
    if not data:
        data = {"items": []}
    data.setdefault("items", [])
    return data


def set_whatsapp_cart(db: Session, rest_id: int, phone: str, data: dict):
    key = get_whatsapp_cart_key(phone)
    payload = data or {"items": []}
    payload.setdefault("items", [])
    set_restaurant_setting_value(db, rest_id, key, payload)


def clear_whatsapp_cart(db: Session, rest_id: int, phone: str):
    set_whatsapp_cart(db, rest_id, phone, {"items": []})


def find_product_for_whatsapp(db: Session, rest_id: int, product_id: int):
    return (
        db.query(Product)
        .filter(
            Product.id == product_id,
            Product.restaurant_id == rest_id,
            Product.is_active == True,  # noqa: E712
        )
        .first()
    )


def add_product_to_whatsapp_cart(
    db: Session,
    rest,
    phone: str,
    product_id: int,
    quantity: Decimal,
):
    if quantity <= 0:
        raise HTTPException(status_code=400, detail="Cantidad inválida.")

    product = find_product_for_whatsapp(db, rest.id, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")

    visibility_map = get_whatsapp_catalog_visibility_map(db, rest.id)
    if not is_product_visible_in_whatsapp(visibility_map, product.id):
        raise HTTPException(status_code=400, detail="Producto no visible en WhatsApp.")

    cart = get_whatsapp_cart(db, rest.id, phone)
    items = cart.get("items", [])

    found = None
    for row in items:
        if int(row.get("product_id") or 0) == int(product.id):
            found = row
            break

    if found:
        found["quantity"] = float(Decimal(str(found.get("quantity") or 0)) + quantity)
    else:
        items.append({
            "product_id": product.id,
            "name": product.name or "",
            "price": float(product.price or 0),
            "quantity": float(quantity),
            "category": product.category or "General",
        })

    cart["items"] = items
    set_whatsapp_cart(db, rest.id, phone, cart)
    return cart


def remove_product_from_whatsapp_cart(
    db: Session,
    rest,
    phone: str,
    product_id: int,
    quantity: Decimal,
):
    if quantity <= 0:
        raise HTTPException(status_code=400, detail="Cantidad inválida.")

    cart = get_whatsapp_cart(db, rest.id, phone)
    items = cart.get("items", [])

    next_items = []
    found = False

    for row in items:
        if int(row.get("product_id") or 0) == int(product_id):
            found = True
            current_qty = Decimal(str(row.get("quantity") or 0))
            new_qty = current_qty - quantity
            if new_qty > 0:
                row["quantity"] = float(new_qty)
                next_items.append(row)
        else:
            next_items.append(row)

    if not found:
        raise HTTPException(status_code=404, detail="Producto no existe en el carrito.")

    cart["items"] = next_items
    set_whatsapp_cart(db, rest.id, phone, cart)
    return cart


def build_whatsapp_cart_summary(db: Session, rest, phone: str) -> dict:
    wa = get_tenant_whatsapp_config(db, rest.id)
    cart = get_whatsapp_cart(db, rest.id, phone)
    items = cart.get("items", [])

    total = Decimal("0")
    lines = []

    prefix = (wa.get("cart_summary_prefix") or "Tu pedido actual es:").strip()
    lines.append(prefix)

    if not items:
        lines.append("- No hay productos en el carrito.")
    else:
        for row in items:
            qty = Decimal(str(row.get("quantity") or 0))
            price = Decimal(str(row.get("price") or 0))
            line_total = qty * price
            total += line_total
            lines.append(
                f"- {row.get('name') or 'Producto'} x{float(qty):.2f} · C${float(line_total):.2f}"
            )

    lines.append("")
    lines.append(f"Total: C${float(total):.2f}")

    return {
        "items": items,
        "total": float(total),
        "text": "\n".join(lines).strip(),
    }

DEFAULT_DELIVERY_CONFIG = {
    "origin_name": "Sucursal principal",
    "origin_address": "",
    "origin_lat": None,
    "origin_lng": None,
    "price_per_km": 10.0,
}


def get_tenant_delivery_config(db: Session, rest_id: int) -> dict:
    data = get_restaurant_setting_value(
        db,
        rest_id,
        "delivery_config",
        DEFAULT_DELIVERY_CONFIG,
    )
    base = dict(DEFAULT_DELIVERY_CONFIG)
    if isinstance(data, dict):
        base.update(data)
    return base


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    from math import radians, sin, cos, sqrt, atan2

    if None in (lat1, lon1, lat2, lon2):
        return 0.0

    r = 6371.0
    dlat = radians(float(lat2) - float(lat1))
    dlon = radians(float(lon2) - float(lon1))

    a = sin(dlat / 2)**2 + cos(radians(float(lat1))) * cos(radians(float(lat2))) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return r * c


def set_whatsapp_delivery_data(
    db: Session,
    rest,
    phone: str,
    lat: float,
    lng: float,
    address: str,
    district: str,
):
    session_data = get_whatsapp_session(db, rest.id, phone)

    config = get_tenant_delivery_config(db, rest.id)

    origin_lat = config.get("origin_lat")
    origin_lng = config.get("origin_lng")
    price_per_km = Decimal(str(config.get("price_per_km") or 0))

    distance = Decimal(str(haversine_km(origin_lat, origin_lng, lat, lng)))
    fee = distance * price_per_km

    session_data.update({
        "delivery": True,
        "customer_lat": lat,
        "customer_lng": lng,
        "customer_address": address,
        "customer_district": district,
        "distance_km": float(distance),
        "delivery_fee": float(fee),
        "price_per_km": float(price_per_km),
    })

    set_whatsapp_session(db, rest.id, phone, session_data)
    return session_data


def build_whatsapp_delivery_summary(db: Session, rest, phone: str) -> dict:
    cart = build_whatsapp_cart_summary(db, rest, phone)
    session_data = get_whatsapp_session(db, rest.id, phone)

    delivery_fee = Decimal(str(session_data.get("delivery_fee") or 0))
    distance = Decimal(str(session_data.get("distance_km") or 0))
    price_per_km = Decimal(str(session_data.get("price_per_km") or 0))

    total = Decimal(str(cart["total"])) + delivery_fee

    text = f'''
{cart["text"]}

Distancia: {distance:.2f} km
Tarifa por km: C${price_per_km:.2f}
Delivery: C${delivery_fee:.2f}

TOTAL FINAL: C${total:.2f}
'''.strip()

    return {
        "total": float(total),
        "delivery_fee": float(delivery_fee),
        "distance": float(distance),
        "text": text
    }

def create_real_order_from_whatsapp_cart(
    db: Session,
    rest,
    phone: str,
):
    normalized = normalize_phone(phone)
    cart = get_whatsapp_cart(db, rest.id, normalized)
    items = cart.get("items", [])

    if not items:
        raise HTTPException(status_code=400, detail="El carrito WhatsApp está vacío.")

    session_data = get_whatsapp_session(db, rest.id, normalized)

    payload_items = []
    session_data = get_whatsapp_session(db, rest.id, normalized)

    notes_lines = ["Origen: WhatsApp"]

    if session_data.get("delivery"):
        notes_lines.extend([
            f"Dirección: {session_data.get('customer_address') or ''}",
            f"Distrito: {session_data.get('customer_district') or ''}",
            f"Distancia: {session_data.get('distance_km') or 0} km",
            f"Delivery: C${session_data.get('delivery_fee') or 0}",
        ])

    for row in items:
        product_id = int(row.get("product_id") or 0)
        qty = Decimal(str(row.get("quantity") or 0))

        product = find_product_for_whatsapp(db, rest.id, product_id)
        if not product:
            raise HTTPException(status_code=400, detail=f"Producto inválido en carrito: {product_id}")
        if qty <= 0:
            raise HTTPException(status_code=400, detail=f"Cantidad inválida para producto {product.name}")

        payload_items.append({
            "product_id": product.id,
            "quantity": qty,
        })

    customer_name = (session_data.get("customer_name") or "").strip()

    temp_payload = CreateOrderInput(
        channel="whatsapp",
        customer_name=customer_name,
        customer_phone=normalized,
        table_number="",
        notes="\n".join(notes_lines),
        items=[
            OrderItemInput(
                product_id=int(x["product_id"]),
                quantity=Decimal(str(x["quantity"]))
            )
            for x in payload_items
        ]
    )

    result = v2_api_create_order(
        payload=temp_payload,
        restaurant=rest.slug,
        db=db,
    )

    order_id = result["order"]["id"]

    session_data["state"] = "order_created"
    session_data["last_order_id"] = order_id
    session_data["updated_at"] = datetime.utcnow().isoformat()
    set_whatsapp_session(db, rest.id, normalized, session_data)

    clear_whatsapp_cart(db, rest.id, normalized)
    db.commit()

    return {
        "order_id": order_id,
        "session": session_data,
        "result": result,
    }

def set_whatsapp_catalog_visibility_map(db: Session, rest_id: int, data: dict):
    set_restaurant_setting_value(
        db,
        rest_id,
        "whatsapp_catalog_visibility",
        data or {},
    )


def is_product_visible_in_whatsapp(visibility_map: dict, product_id: int) -> bool:
    key = str(product_id)
    if key not in visibility_map:
        return True
    return bool(visibility_map.get(key))

def build_whatsapp_catalog_data(db: Session, rest) -> dict:
    visibility_map = get_whatsapp_catalog_visibility_map(db, rest.id)

    rows = (
        db.query(Product)
        .filter(
            Product.restaurant_id == rest.id,
            Product.is_active == True,  # noqa: E712
        )
        .order_by(Product.category.asc(), Product.name.asc())
        .all()
    )

    grouped = {}
    visible_rows = []

    for p in rows:
        if not is_product_visible_in_whatsapp(visibility_map, p.id):
            continue

        visible_rows.append(p)
        category = (p.category or "General").strip() or "General"
        grouped.setdefault(category, []).append({
            "id": p.id,
            "name": p.name or "",
            "price": float(p.price or 0),
            "description": p.description or "",
            "image_url": p.image_url or "",
        })

    categories = [
        {
            "name": cat,
            "items": items,
        }
        for cat, items in grouped.items()
    ]

    return {
        "restaurant": {
            "id": rest.id,
            "name": rest.name,
            "slug": rest.slug,
            "brand_name": getattr(rest, "brand_name", None) or rest.name,
            "tagline": getattr(rest, "tagline", None) or "",
        },
        "categories": categories,
        "count_categories": len(categories),
        "count_products": len(visible_rows),
    }

def build_whatsapp_menu_text(db: Session, rest) -> str:
    wa = get_tenant_whatsapp_config(db, rest.id)
    messages = wa.get("messages") or {}
    brand_title = wa.get("brand_title") or rest.name
    main_menu = [x for x in (wa.get("main_menu") or []) if x.get("enabled")]

    lines = []
    lines.append((messages.get("welcome") or f"👋 Bienvenido a {brand_title}").strip())
    lines.append("")
    lines.append((messages.get("choose_option") or "Elegí una opción:").strip())
    lines.append("")

    for idx, item in enumerate(main_menu, start=1):
        title = item.get("title") or "Opción"
        lines.append(f"{idx}) {title}")

    return "\n".join(lines).strip()

def get_enabled_main_menu_items(db: Session, rest_id: int) -> list:
    wa = get_tenant_whatsapp_config(db, rest_id)
    return [x for x in (wa.get("main_menu") or []) if x.get("enabled")]


def get_enabled_category_menu_items(db: Session, rest_id: int) -> list:
    wa = get_tenant_whatsapp_config(db, rest_id)
    return [x for x in (wa.get("category_menu") or []) if x.get("enabled")]


def normalize_text_key(value: str) -> str:
    raw = (value or "").strip().lower()
    return raw


def build_whatsapp_main_menu_text(db: Session, rest) -> str:
    wa = get_tenant_whatsapp_config(db, rest.id)
    msgs = wa.get("messages") or {}
    items = get_enabled_main_menu_items(db, rest.id)

    lines = []
    lines.append((msgs.get("welcome") or "👋 Bienvenido").strip())
    lines.append("")
    lines.append((msgs.get("choose_option") or "Elegí una opción:").strip())
    lines.append("")

    for idx, item in enumerate(items, start=1):
        title = item.get("title") or f"Opción {idx}"
        desc = item.get("description") or ""
        if desc:
            lines.append(f"{idx}) {title} — {desc}")
        else:
            lines.append(f"{idx}) {title}")

    return "\n".join(lines).strip()


def build_whatsapp_category_menu_text(db: Session, rest) -> str:
    wa = get_tenant_whatsapp_config(db, rest.id)
    msgs = wa.get("messages") or {}
    items = get_enabled_category_menu_items(db, rest.id)

    lines = []
    lines.append((msgs.get("choose_category") or "📋 Menú — elegí categoría").strip())
    lines.append("")

    for idx, item in enumerate(items, start=1):
        title = item.get("title") or f"Categoría {idx}"
        desc = item.get("description") or ""
        if desc:
            lines.append(f"{idx}) {title} — {desc}")
        else:
            lines.append(f"{idx}) {title}")

    return "\n".join(lines).strip()


def resolve_main_menu_selection(db: Session, rest_id: int, text: str):
    items = get_enabled_main_menu_items(db, rest_id)
    raw = normalize_text_key(text)

    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(items):
            return items[idx]

    for item in items:
        if normalize_text_key(item.get("title")) == raw:
            return item

    return None


def resolve_category_selection(db: Session, rest_id: int, text: str):
    items = get_enabled_category_menu_items(db, rest_id)
    raw = normalize_text_key(text)

    if raw.isdigit():
        idx = int(raw) - 1
        if 0 <= idx < len(items):
            return items[idx]

    for item in items:
        if normalize_text_key(item.get("title")) == raw:
            return item

    return None


def build_products_for_category_text(db: Session, rest, category_title: str) -> str:
    wa = get_tenant_whatsapp_config(db, rest.id)
    msgs = wa.get("messages") or {}
    visibility_map = get_whatsapp_catalog_visibility_map(db, rest.id)

    rows = (
        db.query(Product)
        .filter(
            Product.restaurant_id == rest.id,
            Product.is_active == True,  # noqa: E712
            Product.category == category_title,
        )
        .order_by(Product.name.asc())
        .all()
    )

    visible_rows = [p for p in rows if is_product_visible_in_whatsapp(visibility_map, p.id)]

    title = (msgs.get("choose_product") or "Tocá para elegir").strip()
    lines = [f"🍽 {category_title} ({title})", ""]

    if not visible_rows:
        lines.append("No hay productos visibles en esta categoría.")
        return "\n".join(lines).strip()

    for idx, p in enumerate(visible_rows, start=1):
        price_txt = f"C${float(p.price or 0):.2f}"
        lines.append(f"{idx}) [{p.id}] {p.name} — {price_txt}")

    lines.append("")
    lines.append("Responde con el ID del producto o con 'menu' para volver.")
    return "\n".join(lines).strip()

@app.get("/v2/api/whatsapp/catalog")
def v2_api_whatsapp_catalog(
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    catalog = build_whatsapp_catalog_data(db, rest)
    wa = get_tenant_whatsapp_config(db, rest.id)
    payment_methods = get_tenant_payment_methods(db, rest.id)
    service_modes = get_tenant_service_modes(db, rest.id)

    return {
        "ok": True,
        "restaurant": rest.slug,
        "catalog": catalog,
        "whatsapp": wa,
        "payment_methods": payment_methods,
        "service_modes": service_modes,
        "menu_text": build_whatsapp_menu_text(db, rest),
    }


@app.get("/v2/api/whatsapp/menu-text")
def v2_api_whatsapp_menu_text(
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)
    return {
        "ok": True,
        "restaurant": rest.slug,
        "menu_text": build_whatsapp_menu_text(db, rest),
    }

@app.get("/v2/api/admin/whatsapp-products")
def v2_api_admin_whatsapp_products(
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)
    visibility_map = get_whatsapp_catalog_visibility_map(db, rest.id)

    rows = (
        db.query(Product)
        .filter(Product.restaurant_id == rest.id)
        .order_by(Product.category.asc(), Product.name.asc())
        .all()
    )

    return {
        "ok": True,
        "restaurant": rest.slug,
        "items": [
            {
                "id": p.id,
                "name": p.name or "",
                "category": p.category or "General",
                "price": float(p.price or 0),
                "is_active": bool(p.is_active),
                "whatsapp_visible": is_product_visible_in_whatsapp(visibility_map, p.id),
            }
            for p in rows
        ],
    }


class WhatsAppProductVisibilityInput(BaseModel):
    visible: bool


@app.patch("/v2/api/admin/whatsapp-products/{product_id}")
def v2_api_admin_whatsapp_products_patch(
    product_id: int,
    payload: WhatsAppProductVisibilityInput,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    product = (
        db.query(Product)
        .filter(
            Product.id == product_id,
            Product.restaurant_id == rest.id,
        )
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")

    visibility_map = get_whatsapp_catalog_visibility_map(db, rest.id)
    visibility_map[str(product.id)] = bool(payload.visible)
    set_whatsapp_catalog_visibility_map(db, rest.id, visibility_map)
    db.commit()

    return {
        "ok": True,
        "restaurant": rest.slug,
        "product_id": product.id,
        "visible": bool(payload.visible),
    }

@app.post("/v2/api/whatsapp/session/start")
def v2_api_whatsapp_session_start(
    payload: WhatsAppSessionStartInput,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)
    phone = normalize_phone(payload.phone)

    if not phone:
        raise HTTPException(status_code=400, detail="Teléfono inválido.")

    session_data = {
        "phone": phone,
        "customer_name": (payload.customer_name or "").strip(),
        "state": "browsing_menu",
        "updated_at": datetime.utcnow().isoformat(),
    }
    set_whatsapp_session(db, rest.id, phone, session_data)
    db.commit()

    return {
        "ok": True,
        "restaurant": rest.slug,
        "session": session_data,
        "menu_text": build_whatsapp_main_menu_text(db, rest),
    }


@app.get("/v2/api/whatsapp/session")
def v2_api_whatsapp_session_get(
    phone: str,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)
    normalized = normalize_phone(phone)
    session_data = get_whatsapp_session(db, rest.id, normalized)
    cart = build_whatsapp_cart_summary(db, rest, normalized)

    return {
        "ok": True,
        "restaurant": rest.slug,
        "session": session_data,
        "cart": cart,
    }


@app.post("/v2/api/whatsapp/cart/add")
def v2_api_whatsapp_cart_add(
    payload: WhatsAppCartItemInput,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)
    phone = normalize_phone(payload.phone)

    cart = add_product_to_whatsapp_cart(
        db,
        rest,
        phone,
        payload.product_id,
        Decimal(str(payload.quantity or 0)),
    )

    session_data = get_whatsapp_session(db, rest.id, phone)
    session_data["state"] = "editing_cart"
    session_data["updated_at"] = datetime.utcnow().isoformat()
    set_whatsapp_session(db, rest.id, phone, session_data)

    db.commit()

    summary = build_whatsapp_cart_summary(db, rest, phone)

    return {
        "ok": True,
        "restaurant": rest.slug,
        "cart": cart,
        "summary": summary,
    }


@app.post("/v2/api/whatsapp/cart/remove")
def v2_api_whatsapp_cart_remove(
    payload: WhatsAppCartRemoveInput,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)
    phone = normalize_phone(payload.phone)

    cart = remove_product_from_whatsapp_cart(
        db,
        rest,
        phone,
        payload.product_id,
        Decimal(str(payload.quantity or 0)),
    )

    session_data = get_whatsapp_session(db, rest.id, phone)
    session_data["state"] = "editing_cart"
    session_data["updated_at"] = datetime.utcnow().isoformat()
    set_whatsapp_session(db, rest.id, phone, session_data)

    db.commit()

    summary = build_whatsapp_cart_summary(db, rest, phone)

    return {
        "ok": True,
        "restaurant": rest.slug,
        "cart": cart,
        "summary": summary,
    }


@app.get("/v2/api/whatsapp/cart")
def v2_api_whatsapp_cart_get(
    phone: str,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)
    normalized = normalize_phone(phone)
    summary = build_whatsapp_cart_summary(db, rest, normalized)

    return {
        "ok": True,
        "restaurant": rest.slug,
        "summary": summary,
    }


@app.post("/v2/api/whatsapp/cart/confirm")
def v2_api_whatsapp_cart_confirm(
    payload: WhatsAppCartReadInput,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)
    phone = normalize_phone(payload.phone)

    session_data = get_whatsapp_session(db, rest.id, phone)
    session_data["state"] = "awaiting_order_confirmation"
    session_data["updated_at"] = datetime.utcnow().isoformat()
    set_whatsapp_session(db, rest.id, phone, session_data)

    db.commit()

    wa = get_tenant_whatsapp_config(db, rest.id)
    summary = build_whatsapp_cart_summary(db, rest, phone)

    return {
        "ok": True,
        "restaurant": rest.slug,
        "session": session_data,
        "summary": summary,
        "confirm_message": (wa.get("confirm_message") or "¿Deseas confirmar tu pedido?").strip(),
    }

@app.post("/v2/api/whatsapp/cart/create-order")
def v2_api_whatsapp_cart_create_order(
    payload: WhatsAppCartReadInput,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)
    data = create_real_order_from_whatsapp_cart(db, rest, payload.phone)

    wa = get_tenant_whatsapp_config(db, rest.id)

    return {
        "ok": True,
        "restaurant": rest.slug,
        "order_id": data["order_id"],
        "session": data["session"],
        "order": data["result"]["order"],
        "order_received_message": (wa.get("order_received_message") or "Pedido recibido y guardado.").strip(),
    }

@app.get("/v2/api/admin/delivery-config")
def get_delivery_config(
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)
    config = get_tenant_delivery_config(db, rest.id)

    return {
        "ok": True,
        "restaurant": rest.slug,
        "config": config,
    }

@app.post("/v2/api/admin/delivery-config")
def set_delivery_config(
    payload: DeliveryConfigInput,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    set_restaurant_setting_value(
        db,
        rest.id,
        "delivery_config",
        payload.dict(),
    )

    db.commit()

    return {"ok": True}

@app.post("/v2/api/whatsapp/delivery/set")
def v2_api_whatsapp_delivery_set(
    payload: WhatsAppDeliveryInput,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)
    phone = normalize_phone(payload.phone)

    session_data = set_whatsapp_delivery_data(
        db,
        rest,
        phone,
        payload.lat,
        payload.lng,
        payload.address,
        payload.district,
    )

    db.commit()

    summary = build_whatsapp_delivery_summary(db, rest, phone)

    return {
        "ok": True,
        "summary": summary,
        "session": session_data,
    }

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "")


def send_whatsapp_text(to_phone: str, body: str):
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        return {"ok": False, "detail": "Faltan WHATSAPP_TOKEN o PHONE_NUMBER_ID"}

    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {
            "body": body[:4096]
        }
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=20)
        return {
            "ok": resp.ok,
            "status_code": resp.status_code,
            "data": resp.json() if resp.content else {},
        }
    except Exception as e:
        return {"ok": False, "detail": str(e)}


@app.get("/webhook/whatsapp")
async def whatsapp_verify(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN and challenge:
        return PlainTextResponse(challenge, status_code=200)

    return PlainTextResponse("forbidden", status_code=403)


@app.post("/webhook/whatsapp")
async def webhook(request: Request, db: Session = Depends(get_db)):
    data = await request.json()

    try:
        entry = (data.get("entry") or [])[0]
        change = (entry.get("changes") or [])[0]
        value = change.get("value") or {}
        messages = value.get("messages") or []
        contacts = value.get("contacts") or []
        metadata = value.get("metadata") or {}
        phone_number_id = str(metadata.get("phone_number_id") or "").strip()

        if not messages:
            return JSONResponse({"ok": True})

        msg = messages[0]
        from_id = normalize_phone(msg.get("from") or "")
        if not from_id:
            return JSONResponse({"ok": True})

        profile_name = ""
        if contacts:
            profile_name = (((contacts[0].get("profile") or {}).get("name")) or "").strip()

        rest = get_restaurant_by_phone_number_id(db, phone_number_id)

        if not rest:
            print("⚠️ No restaurant by phone_number_id:", phone_number_id)
            rest = db.query(Restaurant).filter(Restaurant.slug == "deaca").first()

        if not rest:
            print("❌ CRITICAL: No restaurant found at all")
            return JSONResponse({"ok": False, "error": "Restaurant not found"}, status_code=500)

        wa = get_tenant_whatsapp_config(db, rest.id)
        msgs = wa.get("messages") or {}

        session_data = get_whatsapp_session(db, rest.id, from_id)
        if not session_data:
            session_data = {
                "phone": from_id,
                "customer_name": profile_name,
                "state": "main_menu",
                "updated_at": datetime.utcnow().isoformat(),
            }
            set_whatsapp_session(db, rest.id, from_id, session_data)
            db.commit()

        state = (session_data.get("state") or "main_menu").strip()

        mtype = msg.get("type") or ""
        text = ""
        selected_text = ""
        location = None

        if mtype == "text":
            text = ((msg.get("text") or {}).get("body") or "").strip()
            selected_text = text

        elif mtype == "interactive":
            inter = msg.get("interactive") or {}
            itype = inter.get("type")

            if itype == "button_reply":
                selected_text = (((inter.get("button_reply") or {}).get("title")) or "").strip()
                if not selected_text:
                    selected_text = (((inter.get("button_reply") or {}).get("id")) or "").strip()

            elif itype == "list_reply":
                selected_text = (((inter.get("list_reply") or {}).get("title")) or "").strip()
                if not selected_text:
                    selected_text = (((inter.get("list_reply") or {}).get("id")) or "").strip()

        elif mtype == "location":
            loc = msg.get("location") or {}
            location = {
                "latitude": loc.get("latitude"),
                "longitude": loc.get("longitude"),
                "name": loc.get("name") or "",
                "address": loc.get("address") or "",
            }

        incoming = (selected_text or text or "").strip().lower()

        # ===== comandos globales =====
        if incoming in {"hola", "inicio", "start"}:
            set_whatsapp_state(db, rest.id, from_id, "main_menu", {
                "customer_name": profile_name or session_data.get("customer_name", "")
            })
            db.commit()
            send_whatsapp_text(from_id, build_whatsapp_main_menu_text(db, rest))
            return JSONResponse({"ok": True, "action": "main_menu"})

        if incoming == "menu":
            set_whatsapp_state(db, rest.id, from_id, "category_menu")
            db.commit()
            send_whatsapp_text(from_id, build_whatsapp_category_menu_text(db, rest))
            return JSONResponse({"ok": True, "action": "category_menu"})

        if incoming == "carrito":
            summary = build_whatsapp_cart_summary(db, rest, from_id)
            send_whatsapp_text(from_id, summary["text"])
            return JSONResponse({"ok": True, "action": "cart_summary"})

        if incoming == "asesor":
            send_whatsapp_text(from_id, (msgs.get("advisor") or "Un asesor te atenderá en breve.").strip())
            return JSONResponse({"ok": True, "action": "advisor"})

        if incoming in {"cancelar", "borrar", "borrar orden"}:
            clear_whatsapp_cart(db, rest.id, from_id)
            set_whatsapp_state(db, rest.id, from_id, "main_menu")
            db.commit()
            send_whatsapp_text(from_id, (msgs.get("cancel") or "Tu pedido fue cancelado.").strip())
            return JSONResponse({"ok": True, "action": "cancel"})

        # ===== selección menú principal =====
        if state == "main_menu":
            selected = resolve_main_menu_selection(db, rest.id, selected_text or text)
            if selected:
                selected_id = selected.get("id")

                if selected_id in {"menu", "order"}:
                    set_whatsapp_state(db, rest.id, from_id, "category_menu")
                    db.commit()
                    send_whatsapp_text(from_id, build_whatsapp_category_menu_text(db, rest))
                    return JSONResponse({"ok": True, "action": "category_menu"})

                if selected_id == "cart":
                    summary = build_whatsapp_cart_summary(db, rest, from_id)
                    send_whatsapp_text(from_id, summary["text"])
                    return JSONResponse({"ok": True, "action": "cart_from_main"})

                if selected_id == "location_hours":
                    delivery_cfg = get_tenant_delivery_config(db, rest.id)
                    address = delivery_cfg.get("origin_address") or "Dirección no configurada."
                    send_whatsapp_text(from_id, f"📍 {address}")
                    return JSONResponse({"ok": True, "action": "location_hours"})

                if selected_id == "advisor":
                    send_whatsapp_text(from_id, (msgs.get("advisor") or "Un asesor te atenderá en breve.").strip())
                    return JSONResponse({"ok": True, "action": "advisor_from_main"})

                if selected_id == "clear_order":
                    clear_whatsapp_cart(db, rest.id, from_id)
                    set_whatsapp_state(db, rest.id, from_id, "main_menu")
                    db.commit()
                    send_whatsapp_text(from_id, "Pedido vaciado correctamente.")
                    return JSONResponse({"ok": True, "action": "clear_order_from_main"})

        # ===== selección categoría =====
        if state == "category_menu":
            selected_category = resolve_category_selection(db, rest.id, selected_text or text)
            if selected_category:
                category_title = selected_category.get("title") or ""
                set_whatsapp_state(db, rest.id, from_id, "product_menu", {
                    "selected_category_id": selected_category.get("id"),
                    "selected_category_title": category_title,
                })
                db.commit()
                send_whatsapp_text(from_id, build_products_for_category_text(db, rest, category_title))
                return JSONResponse({"ok": True, "action": "product_menu"})

        # ===== agregar producto =====
        parsed = parse_product_command(selected_text or text)
        if parsed:
            add_product_to_whatsapp_cart(
                db,
                rest,
                from_id,
                parsed["product_id"],
                parsed["quantity"],
            )
            set_whatsapp_state(db, rest.id, from_id, "editing_cart")
            db.commit()

            summary = build_whatsapp_cart_summary(db, rest, from_id)
            send_whatsapp_text(
                from_id,
                summary["text"] + "\n\nEscribe 'delivery', 'pickup', 'menu' o 'confirmar'."
            )
            return JSONResponse({"ok": True, "action": "product_added"})

        # ===== pickup / delivery =====
        if incoming == "pickup":
            set_whatsapp_state(db, rest.id, from_id, "awaiting_order_confirmation", {
                "delivery": False
            })
            db.commit()
            summary = build_whatsapp_cart_summary(db, rest, from_id)
            send_whatsapp_text(
                from_id,
                summary["text"] + "\n\n" + (msgs.get("confirm_order") or "¿Confirmás el pedido?").strip()
            )
            return JSONResponse({"ok": True, "action": "pickup_confirmation"})

        if incoming == "delivery":
            set_whatsapp_state(db, rest.id, from_id, "awaiting_delivery_location", {
                "delivery": True
            })
            db.commit()
            send_whatsapp_text(from_id, "Compárteme tu ubicación actual para calcular el delivery.")
            return JSONResponse({"ok": True, "action": "awaiting_location"})

        if mtype == "location":
            if state != "awaiting_delivery_location":
                send_whatsapp_text(from_id, "Ubicación recibida. Escribe 'delivery' para continuar con el envío.")
                return JSONResponse({"ok": True, "action": "location_out_of_flow"})

            session_data = get_whatsapp_session(db, rest.id, from_id)
            session_data["delivery"] = True
            session_data["customer_lat"] = location.get("latitude")
            session_data["customer_lng"] = location.get("longitude")
            session_data["updated_at"] = datetime.utcnow().isoformat()
            session_data["state"] = "awaiting_delivery_address"
            set_whatsapp_session(db, rest.id, from_id, session_data)
            db.commit()

            send_whatsapp_text(from_id, (msgs.get("ask_address") or "Escribí tu dirección completa.").strip())
            return JSONResponse({"ok": True, "action": "awaiting_address"})

        if state == "awaiting_delivery_address":
            if not (selected_text or text).strip():
                send_whatsapp_text(from_id, (msgs.get("ask_address") or "Escribí tu dirección completa.").strip())
                return JSONResponse({"ok": True, "action": "address_retry"})

            session_data = get_whatsapp_session(db, rest.id, from_id)
            session_data["customer_address"] = (selected_text or text).strip()
            session_data["updated_at"] = datetime.utcnow().isoformat()
            session_data["state"] = "awaiting_delivery_district"
            set_whatsapp_session(db, rest.id, from_id, session_data)
            db.commit()

            send_whatsapp_text(from_id, (msgs.get("ask_district") or "¿A qué distrito pertenece tu dirección?").strip())
            return JSONResponse({"ok": True, "action": "awaiting_district"})

        if state == "awaiting_delivery_district":
            if incoming not in {"1", "2", "3", "4", "5", "6", "7"}:
                send_whatsapp_text(from_id, "Distrito inválido. Responde con un número del 1 al 7.")
                return JSONResponse({"ok": True, "action": "district_retry"})

            session_data = get_whatsapp_session(db, rest.id, from_id)
            lat = session_data.get("customer_lat")
            lng = session_data.get("customer_lng")
            address = session_data.get("customer_address") or ""

            set_whatsapp_delivery_data(
                db,
                rest,
                from_id,
                float(lat or 0),
                float(lng or 0),
                address,
                incoming,
            )
            set_whatsapp_state(db, rest.id, from_id, "awaiting_order_confirmation")
            db.commit()

            summary = build_whatsapp_delivery_summary(db, rest, from_id)
            send_whatsapp_text(
                from_id,
                summary["text"] + "\n\n" + (msgs.get("confirm_order") or "¿Confirmás el pedido?").strip()
            )
            return JSONResponse({"ok": True, "action": "delivery_summary"})

        # ===== confirmar =====
        if incoming == "confirmar":
            current_session = get_whatsapp_session(db, rest.id, from_id)
            current_state = current_session.get("state") or ""

            if current_state not in {"awaiting_order_confirmation", "editing_cart", "product_menu", "category_menu"}:
                send_whatsapp_text(from_id, "Aún no tengo un pedido listo para confirmar.")
                return JSONResponse({"ok": True, "action": "confirm_blocked"})

            data_created = create_real_order_from_whatsapp_cart(db, rest, from_id)
            send_whatsapp_text(
                from_id,
                f"{(msgs.get('received') or 'Pedido recibido y guardado.').strip()}\nID orden: {data_created['order_id']}"
            )
            return JSONResponse({"ok": True, "action": "order_created", "order_id": data_created["order_id"]}

            )

        # ===== fallback =====
        send_whatsapp_text(from_id, build_whatsapp_main_menu_text(db, rest))
        return JSONResponse({"ok": True, "action": "fallback_main_menu"})

    except Exception as e:
        print("WEBHOOK_ERROR", str(e))
        return JSONResponse({"ok": False, "error": str(e)}, status_code=200)

@app.get("/v2/admin", response_class=HTMLResponse)
def v2_admin(
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    body = f"""
    <link
      rel="stylesheet"
      href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
    />
    <style>
      .admin-shell {{
        display: grid;
        gap: 18px;
      }}
      .admin-top {{
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 12px;
        flex-wrap: wrap;
      }}
      .admin-brand h1 {{
        margin: 0;
        font-size: 30px;
        font-weight: 900;
      }}
      .admin-brand p {{
        margin: 4px 0 0 0;
        color: #6b7280;
      }}
      .toolbar {{
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
      }}
      .btn {{
        border: 0;
        border-radius: 12px;
        padding: 12px 16px;
        font-weight: 800;
        cursor: pointer;
      }}
      .btn.dark {{
        background: #111827;
        color: #fff;
      }}
      .btn.light {{
        background: #fff;
        color: #111827;
        border: 1px solid #e5e7eb;
      }}
      .panel {{
        background: #fff;
        border: 1px solid #e5e7eb;
        border-radius: 18px;
        padding: 16px;
      }}
      .panel h2 {{
        margin: 0 0 14px 0;
        font-size: 20px;
        font-weight: 800;
      }}
      .form-grid {{
        display: grid;
        grid-template-columns: repeat(4, minmax(140px, 1fr));
        gap: 10px;
      }}
      .input, .select {{
        width: 100%;
        border: 1px solid #d1d5db;
        border-radius: 12px;
        padding: 12px 14px;
        font-size: 14px;
        box-sizing: border-box;
        background: #fff;
      }}
      .list-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
        gap: 12px;
        margin-top: 14px;
      }}
      .card {{
        border: 1px solid #e5e7eb;
        border-radius: 16px;
        padding: 14px;
        background: #fff;
      }}
      .card-title {{
        font-size: 18px;
        font-weight: 800;
      }}
      .muted {{
        color: #6b7280;
      }}
      .mini-actions {{
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        margin-top: 12px;
      }}
      .mini-btn {{
        border: 1px solid #d1d5db;
        background: #fff;
        color: #111827;
        border-radius: 10px;
        padding: 8px 10px;
        font-size: 12px;
        font-weight: 800;
        cursor: pointer;
      }}
      .tag {{
        display: inline-block;
        padding: 4px 8px;
        border-radius: 999px;
        font-size: 11px;
        font-weight: 800;
        background: #f3f4f6;
        margin-top: 8px;
      }}
      .two-col {{
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 18px;
      }}
      .status-box {{
        margin-top: 10px;
        color: #6b7280;
        font-size: 14px;
      }}
       .wa-chat-shell {{
        margin-top: 14px;
        background: #efeae2;
        border: 1px solid #d1d5db;
        border-radius: 18px;
        padding: 14px;
      }}
      .wa-chat-header {{
        font-weight: 800;
        margin-bottom: 10px;
        color: #111827;
      }}
      .wa-chat-body {{
        display: grid;
        gap: 10px;
      }}
      .wa-bubble-row {{
        display: flex;
      }}
      .wa-bubble-row.left {{
        justify-content: flex-start;
      }}
      .wa-bubble-row.right {{
        justify-content: flex-end;
      }}
      .wa-bubble {{
        max-width: 78%;
        padding: 10px 12px;
        border-radius: 14px;
        line-height: 1.45;
        font-size: 14px;
        white-space: pre-wrap;
        box-shadow: 0 1px 2px rgba(0,0,0,.08);
      }}
      .wa-bubble.in {{
        background: #ffffff;
        color: #111827;
        border-top-left-radius: 4px;
      }}
      .wa-bubble.out {{
        background: #d9fdd3;
        color: #111827;
        border-top-right-radius: 4px;
      }}
      .wa-mini-label {{
        font-size: 11px;
        color: #6b7280;
        margin-bottom: 4px;
        font-weight: 700;
      }}

    </style>

    <div class="admin-shell">
      <div class="admin-top">
        <div class="admin-brand">
          <h1>Admin</h1>
          <p>{rest.name} · {rest.slug}</p>
        </div>

        <div class="toolbar">
          <button class="btn light" onclick="window.location.href='/v2/menu?restaurant=__REST_SLUG__'">Volver al menú</button>
          <button class="btn light" onclick="window.location.href='/v2/pos/local/floor?restaurant=__REST_SLUG__'">Ir al floor</button>
        </div>
      </div>

      <div class="two-col">
        <div class="panel">
          <h2>Zonas</h2>

          <div class="form-grid">
            <input id="zoneName" class="input" placeholder="Nombre de zona" />
            <input id="zoneSort" class="input" type="number" value="0" placeholder="Orden" />
            <select id="zoneActive" class="select">
              <option value="true">Activa</option>
              <option value="false">Inactiva</option>
            </select>
            <button class="btn dark" onclick="createZone()">Crear zona</button>
          </div>

          <div id="zonesBox" class="list-grid"></div>
          <div id="zonesStatus" class="status-box"></div>
        </div>

        <div class="panel">
          <h2>Mesas</h2>

          <div class="form-grid">
            <select id="tableZone" class="select"></select>
            <input id="tableCode" class="input" placeholder="Código (M1, VIP1...)" />
            <input id="tableDisplay" class="input" placeholder="Nombre visible" />
            <input id="tableCapacity" class="input" type="number" value="4" placeholder="Capacidad" />
            <input id="tableSort" class="input" type="number" value="0" placeholder="Orden" />
            <select id="tableActive" class="select">
              <option value="true">Activa</option>
              <option value="false">Inactiva</option>
            </select>
            <div></div>
            <button class="btn dark" onclick="createTable()">Crear mesa</button>
          </div>

          <div id="tablesBox" class="list-grid"></div>
          <div id="tablesStatus" class="status-box"></div>
        </div>
      </div>
    </div>
    
    <div class="panel">
  <h2>Configuración del tenant</h2>

  <div class="two-col">
    <div>
      <h3 style="margin-top:0;">Métodos de pago</h3>
      <div style="display:grid;gap:10px;">
        <label><input type="checkbox" id="pm_cash" /> Efectivo</label>
        <label><input type="checkbox" id="pm_card" /> Tarjeta</label>
        <label><input type="checkbox" id="pm_transfer" /> Transferencia</label>
        <label><input type="checkbox" id="pm_credit" /> Crédito</label>
      </div>

      <h3 style="margin-top:18px;">Modos de servicio</h3>
      <div style="display:grid;gap:10px;">
        <label><input type="checkbox" id="sm_table" /> Mesa</label>
        <label><input type="checkbox" id="sm_bar" /> Barra</label>
        <label><input type="checkbox" id="sm_quick" /> Venta rápida</label>
        <label><input type="checkbox" id="sm_delivery" /> Delivery</label>
        <label><input type="checkbox" id="sm_pickup" /> Pickup</label>
        <label><input type="checkbox" id="sm_whatsapp" /> WhatsApp</label>
      </div>
    </div>

    <div>
      <h3 style="margin-top:0;">WhatsApp Pro</h3>

<div class="form-grid">
  <input id="waBrandTitle" class="input" placeholder="Título de marca WhatsApp" />
</div>

<div style="margin-top:16px;font-weight:bold;">Menú principal</div>
<div id="waMainMenuBox"></div>

<div style="margin-top:16px;font-weight:bold;">Categorías WhatsApp</div>
<div id="waCategoryMenuBox"></div>

<div style="margin-top:16px;font-weight:bold;">Flujo</div>
<div class="form-grid">
  <label><input type="checkbox" id="waFlowAskName" /> Pedir nombre</label>
  <label><input type="checkbox" id="waFlowAskFulfillment" /> Tipo entrega</label>
  <label><input type="checkbox" id="waFlowAskLocation" /> Ubicación automática</label>
  <label><input type="checkbox" id="waFlowAskAddress" /> Dirección escrita</label>
  <label><input type="checkbox" id="waFlowAskDistrict" /> Distrito</label>
  <label><input type="checkbox" id="waFlowAskPayment" /> Método de pago</label>
  <label><input type="checkbox" id="waFlowAskConfirm" /> Confirmación final</label>
</div>

<div style="margin-top:16px;font-weight:bold;">Mensajes</div>
<div class="form-grid">
  <textarea id="waMsgWelcome" class="input"></textarea>
  <textarea id="waMsgChooseOption" class="input"></textarea>
  <textarea id="waMsgChooseCategory" class="input"></textarea>
  <textarea id="waMsgChooseProduct" class="input"></textarea>
  <textarea id="waMsgCartPrefix" class="input"></textarea>
  <textarea id="waMsgDeliveryNotice" class="input"></textarea>
  <textarea id="waMsgAskProceedDelivery" class="input"></textarea>
  <textarea id="waMsgAskAddress" class="input"></textarea>
  <textarea id="waMsgAskDistrict" class="input"></textarea>
  <textarea id="waMsgAskPaymentMethod" class="input"></textarea>
  <textarea id="waMsgConfirmOrder" class="input"></textarea>
  <textarea id="waMsgAdvisor" class="input"></textarea>
  <textarea id="waMsgCancel" class="input"></textarea>
  <textarea id="waMsgReceived" class="input"></textarea>
</div>

<div style="margin-top:16px;">
  <button onclick="saveWhatsAppProConfig()">Guardar WhatsApp Pro</button>
</div>

<div id="waProStatus"></div>
    </div>
  </div>

  <div class="panel">
  <h2>Catálogo WhatsApp</h2>

  <div class="toolbar" style="margin-bottom:12px;">
    <button class="btn light" onclick="loadWhatsAppProducts()">Recargar catálogo WhatsApp</button>
  </div>

  <div id="whatsAppCatalogBox" class="list-grid"></div>
  <div id="whatsAppCatalogStatus" class="status-box"></div>
</div>

  <div class="toolbar" style="margin-top:16px;">
    <button class="btn dark" onclick="saveTenantConfig()">Guardar configuración</button>
  </div>
  
  <div id="tenantConfigStatus" class="status-box"></div>
  
  <div class="toolbar" style="margin-top:10px;">
    <button class="btn light" onclick="previewWhatsAppMenu()">Previsualizar menú WhatsApp</button>
  </div>

  <div class="wa-chat-shell">
  <div class="wa-chat-header">Vista previa tipo WhatsApp</div>
  <div id="whatsAppPreviewBox" class="wa-chat-body"></div>
</div>

<div class="panel">
  <h2>Laboratorio WhatsApp</h2>

  <div class="form-grid">
    <input id="waTestPhone" class="input" placeholder="Teléfono cliente" />
    <input id="waTestName" class="input" placeholder="Nombre cliente" />
    <div></div>
    <button class="btn dark" onclick="startWhatsAppSession()">Iniciar sesión</button>
  </div>

  <div class="toolbar" style="margin-top:12px;">
    <button class="btn light" onclick="refreshWhatsAppSession()">Ver estado</button>
    <button class="btn light" onclick="confirmWhatsAppCart()">Confirmar carrito</button>
  </div>

  <div id="waSessionStatus" class="status-box" style="white-space:pre-wrap;"></div>
  <div class="form-grid" style="margin-top:12px;">
  <input id="waDeliveryLat" class="input" placeholder="Latitud cliente" />
  <input id="waDeliveryLng" class="input" placeholder="Longitud cliente" />
  <input id="waDeliveryAddress" class="input" placeholder="Dirección exacta cliente" />
  <input id="waDeliveryDistrict" class="input" placeholder="Distrito 1-7" />
</div>

<div class="toolbar" style="margin-top:12px;">
  <button class="btn light" onclick="useCurrentCustomerLocation()">Usar ubicación actual cliente</button>
  <button class="btn light" onclick="setDistrictQuick('1')">D1</button>
  <button class="btn light" onclick="setDistrictQuick('2')">D2</button>
  <button class="btn light" onclick="setDistrictQuick('3')">D3</button>
  <button class="btn light" onclick="setDistrictQuick('4')">D4</button>
  <button class="btn light" onclick="setDistrictQuick('5')">D5</button>
  <button class="btn light" onclick="setDistrictQuick('6')">D6</button>
  <button class="btn light" onclick="setDistrictQuick('7')">D7</button>
  <button class="btn dark" onclick="setWhatsAppDelivery()">Guardar delivery cliente</button>
</div>

<div style="margin-top:12px;border:1px solid #e5e7eb;border-radius:16px;overflow:hidden;">
  <div id="customerMap" style="height:320px;"></div>
</div>

<div id="waDeliverySummaryBox" class="status-box" style="white-space:pre-wrap;margin-top:12px;"></div>
  </div>
  
  <div class="toolbar" style="margin-top:12px;">
    <button class="btn light" onclick="loadWhatsAppProductsForLab()">Cargar productos para laboratorio</button>
  </div>

  <div id="waLabProductsBox" class="list-grid" style="margin-top:12px;"></div>
  <div id="waLabCartBox" class="status-box" style="white-space:pre-wrap;margin-top:12px;"></div>

  <div class="toolbar" style="margin-top:12px;">
    <button class="btn dark" onclick="createOrderFromWhatsAppCart()">Crear orden real desde carrito</button>
  </div>

  <div class="panel">
    <h2>Configuración Delivery</h2>

    <div class="form-grid">
      <input id="originLat" class="input" placeholder="Latitud origen" />
      <input id="originLng" class="input" placeholder="Longitud origen" />
      <input id="originAddress" class="input" placeholder="Dirección del local" />
      <input id="pricePerKm" class="input" placeholder="Tarifa por km" />
    </div>

    <div class="toolbar" style="margin-top:12px;">
      <button class="btn light" onclick="useCurrentOriginLocation()">Usar ubicación actual</button>
      <button class="btn dark" onclick="saveDeliveryConfig()">Guardar configuración delivery</button>
    </div>

    <div style="margin-top:12px;border:1px solid #e5e7eb;border-radius:16px;overflow:hidden;">
      <div id="originMap" style="height:320px;"></div>
    </div>

    <div id="deliveryStatus" class="status-box"></div>
  </div>
  </div>
    
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
      const adminRestaurantSlug = "__REST_SLUG__";
      let adminZones = [];
      let adminTables = [];
      let tenantConfig = null;
      let whatsAppProducts = [];
      let waTestSession = null;
      let waLabProducts = [];
      let originMap = null;
      let originMarker = null; 
      let customerMap = null;
      let customerMarker = null;
      let waProConfig = null;

      async function loadZones() {{
        const res = await fetch(`/v2/api/zones?restaurant=${{adminRestaurantSlug}}`);
        const data = await res.json();
        if (!res.ok) {{
          alert(data.detail || "No se pudieron cargar las zonas.");
          return;
        }}
        adminZones = data.items || [];
        renderZones();
        fillZoneSelect();
      }}

      async function loadTables() {{
        const res = await fetch(`/v2/api/tables?restaurant=${{adminRestaurantSlug}}`);
        const data = await res.json();
        if (!res.ok) {{
          alert(data.detail || "No se pudieron cargar las mesas.");
          return;
        }}
        adminTables = data.items || [];
        renderTables();
      }}

      function fillZoneSelect() {{
        const select = document.getElementById("tableZone");
        const opts = [`<option value="">Sin zona</option>`]
          .concat(adminZones.map(z => `<option value="${{z.id}}">${{z.name}}</option>`));
        select.innerHTML = opts.join("");
      }}

      function renderZones() {{
        const box = document.getElementById("zonesBox");
        const status = document.getElementById("zonesStatus");

        box.innerHTML = adminZones.length ? adminZones.map(z => `
          <div class="card">
            <div class="card-title">${{z.name}}</div>
            <div class="muted">Orden: ${{z.sort_order || 0}}</div>
            <div class="tag">${{z.is_active ? "Activa" : "Inactiva"}}</div>

            <div class="mini-actions">
              <button class="mini-btn" onclick="renameZone(${{z.id}}, '${{(z.name || "").replace(/'/g, "\\'")}}')">Renombrar</button>
              <button class="mini-btn" onclick="toggleZone(${{z.id}})">${{z.is_active ? "Desactivar" : "Activar"}}</button>
            </div>
          </div>
        `).join("") : `<div class="muted">No hay zonas creadas.</div>`;

        status.textContent = `Zonas registradas: ${{adminZones.length}}`;
      }}

      function renderTables() {{
        const box = document.getElementById("tablesBox");
        const status = document.getElementById("tablesStatus");

        box.innerHTML = adminTables.length ? adminTables.map(t => {{
          const zoneName = adminZones.find(z => Number(z.id) === Number(t.zone_id))?.name || "Sin zona";
          return `
            <div class="card">
              <div class="card-title">${{t.display_name || t.code}}</div>
              <div class="muted">Código: ${{t.code}}</div>
              <div class="muted">Zona: ${{zoneName}}</div>
              <div class="muted">Capacidad: ${{t.capacity || 0}}</div>
              <div class="muted">Orden: ${{t.sort_order || 0}}</div>
              <div class="tag">${{t.is_active ? "Activa" : "Inactiva"}}</div>

              <div class="mini-actions">
                <button class="mini-btn" onclick="renameTable(${{t.id}}, '${{(t.display_name || "").replace(/'/g, "\\'")}}')">Renombrar</button>
                <button class="mini-btn" onclick="toggleTable(${{t.id}})">${{t.is_active ? "Desactivar" : "Activar"}}</button>
                <button class="mini-btn" onclick="deleteTable(${{t.id}})">Eliminar</button>
              </div>
            </div>
          `;
        }}).join("") : `<div class="muted">No hay mesas creadas.</div>`;

        status.textContent = `Mesas registradas: ${{adminTables.length}}`;
      }}

      async function createZone() {{
        const payload = {{
          name: document.getElementById("zoneName").value || "",
          sort_order: Number(document.getElementById("zoneSort").value || 0),
          is_active: document.getElementById("zoneActive").value === "true"
        }};

        const res = await fetch(`/v2/api/zones?restaurant=${{adminRestaurantSlug}}`, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify(payload)
        }});
        const data = await res.json();

        if (!res.ok) {{
          alert(data.detail || "No se pudo crear la zona.");
          return;
        }}

        document.getElementById("zoneName").value = "";
        document.getElementById("zoneSort").value = "0";
        await loadZones();
        await loadTables();
      }}

      async function renameZone(zoneId, currentName) {{
        const name = prompt("Nuevo nombre de la zona:", currentName || "");
        if (name === null) return;

        const res = await fetch(`/v2/api/zones/${{zoneId}}?restaurant=${{adminRestaurantSlug}}`, {{
          method: "PUT",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ name: name }})
        }});
        const data = await res.json();

        if (!res.ok) {{
          alert(data.detail || "No se pudo renombrar la zona.");
          return;
        }}

        await loadZones();
        await loadTables();
      }}

      async function toggleZone(zoneId) {{
        const res = await fetch(`/v2/api/zones/${{zoneId}}/toggle?restaurant=${{adminRestaurantSlug}}`, {{
          method: "PATCH"
        }});
        const data = await res.json();

        if (!res.ok) {{
          alert(data.detail || "No se pudo cambiar el estado de la zona.");
          return;
        }}

        await loadZones();
      }}

      async function createTable() {{
        const rawZone = document.getElementById("tableZone").value;
        const payload = {{
          zone_id: rawZone ? Number(rawZone) : null,
          code: document.getElementById("tableCode").value || "",
          display_name: document.getElementById("tableDisplay").value || "",
          capacity: Number(document.getElementById("tableCapacity").value || 4),
          sort_order: Number(document.getElementById("tableSort").value || 0),
          is_active: document.getElementById("tableActive").value === "true"
        }};

        const res = await fetch(`/v2/api/tables?restaurant=${{adminRestaurantSlug}}`, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify(payload)
        }});
        const data = await res.json();

        if (!res.ok) {{
          alert(data.detail || "No se pudo crear la mesa.");
          return;
        }}

        document.getElementById("tableCode").value = "";
        document.getElementById("tableDisplay").value = "";
        document.getElementById("tableCapacity").value = "4";
        document.getElementById("tableSort").value = "0";
        await loadTables();
      }}

      async function renameTable(tableId, currentName) {{
        const name = prompt("Nuevo nombre visible de la mesa:", currentName || "");
        if (name === null) return;

        const res = await fetch(`/v2/api/tables/${{tableId}}?restaurant=${{adminRestaurantSlug}}`, {{
          method: "PUT",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ display_name: name }})
        }});
        const data = await res.json();

        if (!res.ok) {{
          alert(data.detail || "No se pudo renombrar la mesa.");
          return;
        }}

        await loadTables();
      }}

      async function toggleTable(tableId) {{
        const res = await fetch(`/v2/api/tables/${{tableId}}/toggle?restaurant=${{adminRestaurantSlug}}`, {{
          method: "PATCH"
        }});
        const data = await res.json();

        if (!res.ok) {{
          alert(data.detail || "No se pudo cambiar el estado de la mesa.");
          return;
        }}

        await loadTables();
      }}

      async function deleteTable(tableId) {{
        const ok = confirm("¿Eliminar esta mesa?");
        if (!ok) return;

        const res = await fetch(`/v2/api/tables/${{tableId}}?restaurant=${{adminRestaurantSlug}}`, {{
          method: "DELETE"
        }});
        const data = await res.json();

        if (!res.ok) {{
          alert(data.detail || "No se pudo eliminar la mesa.");
          return;
        }}

        await loadTables();
      }}

      async function loadTenantConfig() {{
        const res = await fetch(`/v2/api/admin/config?restaurant=${{adminRestaurantSlug}}`);
        const data = await res.json();

        if (!res.ok) {{
          alert(data.detail || "No se pudo cargar la configuración.");
          return;
        }}

        tenantConfig = data.config || {{}};
        waProConfig = tenantConfig.whatsapp || {{}};

        const pm = tenantConfig.payment_methods || {{}};
        const sm = tenantConfig.service_modes || {{}};

        const setChecked = (id, value) => {{
          const el = document.getElementById(id);
          if (el) el.checked = !!value;
        }};

        setChecked("pm_cash", pm.cash);
        setChecked("pm_card", pm.card);
        setChecked("pm_transfer", pm.transfer);
        setChecked("pm_credit", pm.credit);

        setChecked("sm_table", sm.table);
        setChecked("sm_bar", sm.bar);
        setChecked("sm_quick", sm.quick);
        setChecked("sm_delivery", sm.delivery);
        setChecked("sm_pickup", sm.pickup);
        setChecked("sm_whatsapp", sm.whatsapp);
         
        const brandEl = document.getElementById("waBrandTitle");
        if (brandEl) brandEl.value = waProConfig.brand_title || "";

        const flow = waProConfig.flow || {{}};
        setChecked("waFlowAskName", flow.ask_name);
        setChecked("waFlowAskFulfillment", flow.ask_fulfillment_type);
        setChecked("waFlowAskLocation", flow.ask_location_for_delivery);
        setChecked("waFlowAskAddress", flow.ask_written_address);
        setChecked("waFlowAskDistrict", flow.ask_district);
        setChecked("waFlowAskPayment", flow.ask_payment_method);
        setChecked("waFlowAskConfirm", flow.ask_order_confirmation);

        const msgs = waProConfig.messages || {{}};

        const setValue = (id, value) => {{
          const el = document.getElementById(id);
          if (el) el.value = value || "";
        }};

        setValue("waMsgWelcome", msgs.welcome);
        setValue("waMsgChooseOption", msgs.choose_option);
        setValue("waMsgChooseCategory", msgs.choose_category);
        setValue("waMsgChooseProduct", msgs.choose_product);
        setValue("waMsgCartPrefix", msgs.cart_prefix);
        setValue("waMsgDeliveryNotice", msgs.delivery_notice);
        setValue("waMsgAskProceedDelivery", msgs.ask_proceed_delivery);
        setValue("waMsgAskAddress", msgs.ask_address);
        setValue("waMsgAskDistrict", msgs.ask_district);
        setValue("waMsgAskPaymentMethod", msgs.ask_payment_method);
        setValue("waMsgConfirmOrder", msgs.confirm_order);
        setValue("waMsgAdvisor", msgs.advisor);
        setValue("waMsgCancel", msgs.cancel);
        setValue("waMsgReceived", msgs.received);

        renderWaMainMenu(waProConfig.main_menu || []);
        renderWaCategoryMenu(waProConfig.category_menu || []);
      }}
      
      async function saveWhatsAppProConfig() {{
        const mainMenu = (waProConfig?.main_menu || []).map((item, idx) => ({{
          ...item,
          title: document.getElementById(`waMainMenuTitle_${{idx}}`)?.value || "",
          description: document.getElementById(`waMainMenuDesc_${{idx}}`)?.value || "",
          enabled: !!document.getElementById(`waMainMenuEnabled_${{idx}}`)?.checked,
        }}));

        const categoryMenu = (waProConfig?.category_menu || []).map((item, idx) => ({{
          ...item,
          title: document.getElementById(`waCategoryTitle_${{idx}}`)?.value || "",
          description: document.getElementById(`waCategoryDesc_${{idx}}`)?.value || "",
          image_url: document.getElementById(`waCategoryImage_${{idx}}`)?.value || "",
          enabled: !!document.getElementById(`waCategoryEnabled_${{idx}}`)?.checked,
        }}));

        const payload = {{
          payment_methods: {{
            cash: !!document.getElementById("pm_cash")?.checked,
            card: !!document.getElementById("pm_card")?.checked,
            transfer: !!document.getElementById("pm_transfer")?.checked,
            credit: !!document.getElementById("pm_credit")?.checked,
          }},
          service_modes: {{
            table: !!document.getElementById("sm_table")?.checked,
            bar: !!document.getElementById("sm_bar")?.checked,
            quick: !!document.getElementById("sm_quick")?.checked,
            delivery: !!document.getElementById("sm_delivery")?.checked,
            pickup: !!document.getElementById("sm_pickup")?.checked,
            whatsapp: !!document.getElementById("sm_whatsapp")?.checked,
          }},
          whatsapp: {{
            brand_title: document.getElementById("waBrandTitle")?.value || "",
            main_menu: mainMenu,
            category_menu: categoryMenu,
            flow: {{
              ask_name: !!document.getElementById("waFlowAskName")?.checked,
              ask_fulfillment_type: !!document.getElementById("waFlowAskFulfillment")?.checked,
              ask_location_for_delivery: !!document.getElementById("waFlowAskLocation")?.checked,
              ask_written_address: !!document.getElementById("waFlowAskAddress")?.checked,
              ask_district: !!document.getElementById("waFlowAskDistrict")?.checked,
              ask_payment_method: !!document.getElementById("waFlowAskPayment")?.checked,
              ask_order_confirmation: !!document.getElementById("waFlowAskConfirm")?.checked,
            }},
            messages: {{
              welcome: document.getElementById("waMsgWelcome")?.value || "",
              choose_option: document.getElementById("waMsgChooseOption")?.value || "",
              choose_category: document.getElementById("waMsgChooseCategory")?.value || "",
              choose_product: document.getElementById("waMsgChooseProduct")?.value || "",
              cart_prefix: document.getElementById("waMsgCartPrefix")?.value || "",
              delivery_notice: document.getElementById("waMsgDeliveryNotice")?.value || "",
              ask_proceed_delivery: document.getElementById("waMsgAskProceedDelivery")?.value || "",
              ask_address: document.getElementById("waMsgAskAddress")?.value || "",
              ask_district: document.getElementById("waMsgAskDistrict")?.value || "",
              ask_payment_method: document.getElementById("waMsgAskPaymentMethod")?.value || "",
              confirm_order: document.getElementById("waMsgConfirmOrder")?.value || "",
              advisor: document.getElementById("waMsgAdvisor")?.value || "",
              cancel: document.getElementById("waMsgCancel")?.value || "",
              received: document.getElementById("waMsgReceived")?.value || "",
            }}
          }}
        }};

        const res = await fetch(`/v2/api/admin/config?restaurant=${{adminRestaurantSlug}}`, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify(payload)
        }});
        const data = await res.json();
 
        const status = document.getElementById("waProStatus");
        if (status) {{
          status.textContent = res.ok
            ? "WhatsApp Pro guardado correctamente."
            : (data.detail || "Error guardando WhatsApp Pro");
        }}

        if (res.ok) {{
          waProConfig = payload.whatsapp;
        }}
      }}

      async function saveTenantConfig() {{
        const payload = {{
          payment_methods: {{
            cash: document.getElementById("pm_cash").checked,
            card: document.getElementById("pm_card").checked,
            transfer: document.getElementById("pm_transfer").checked,
            credit: document.getElementById("pm_credit").checked,
          }},
          service_modes: {{
            table: document.getElementById("sm_table").checked,
            bar: document.getElementById("sm_bar").checked,
            quick: document.getElementById("sm_quick").checked,
            delivery: document.getElementById("sm_delivery").checked,
            pickup: document.getElementById("sm_pickup").checked,
            whatsapp: document.getElementById("sm_whatsapp").checked,
          }},
          whatsapp: {{
            welcome_message: document.getElementById("wa_welcome_message").value || "",
            menu_intro: document.getElementById("wa_menu_intro").value || "",
            cart_summary_prefix: document.getElementById("wa_cart_summary_prefix").value || "",
            confirm_message: document.getElementById("wa_confirm_message").value || "",
            order_received_message: document.getElementById("wa_order_received_message").value || "",
            advisor_message: document.getElementById("wa_advisor_message").value || "",
            cancel_message: document.getElementById("wa_cancel_message").value || "",
          }}
        }};

        const res = await fetch(`/v2/api/admin/config?restaurant=${{adminRestaurantSlug}}`, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify(payload)
        }});
        const data = await res.json();

        if (!res.ok) {{
          alert(data.detail || "No se pudo guardar la configuración.");
          return;
        }}

        document.getElementById("tenantConfigStatus").textContent = "Configuración guardada correctamente.";
      }}
     
      async function previewWhatsAppMenu() {{
      async function previewWhatsAppMenu() {{
        const res = await fetch(`/v2/api/admin/config?restaurant=${{adminRestaurantSlug}}`);
        const data = await res.json();

        if (!res.ok) {{
          alert(data.detail || "No se pudo generar la previsualización.");
          return;
        }}

        const cfg = data.config || {{}};
        const wa = cfg.whatsapp || {{}};
        const msgs = wa.messages || {{}};

        const menuText = (wa.main_menu || [])
          .filter(x => x.enabled)
          .map((x, idx) => `${{idx + 1}}) ${{x.title}}`)
          .join("\n");

        const box = document.getElementById("whatsAppPreviewBox");
        if (!box) return;

        box.innerHTML = `
          <div class="wa-bubble-row left">
            <div>
              <div class="wa-mini-label">Cliente</div>
              <div class="wa-bubble in">Hola</div>
            </div>
          </div>

          <div class="wa-bubble-row right">
            <div>
              <div class="wa-mini-label">Negocio</div>
              <div class="wa-bubble out">${{msgs.welcome || ""}}

      ${{msgs.choose_option || ""}}

      ${{menuText}}</div>
            </div>
          </div>
        `;
      }}

      async function loadWhatsAppProducts() {{
        const res = await fetch(`/v2/api/admin/whatsapp-products?restaurant=${{adminRestaurantSlug}}`);
        const data = await res.json();

        if (!res.ok) {{
          alert(data.detail || "No se pudo cargar el catálogo de WhatsApp.");
          return;
        }}

        whatsAppProducts = data.items || [];
        renderWhatsAppProducts();
      }}

      function renderWhatsAppProducts() {{
        const box = document.getElementById("whatsAppCatalogBox");
        const status = document.getElementById("whatsAppCatalogStatus");

        box.innerHTML = whatsAppProducts.length ? whatsAppProducts.map(p => `
          <div class="card">
            <div class="card-title">${{p.name}}</div>
            <div class="muted">Categoría: ${{p.category || "General"}}</div>
            <div class="muted">Precio: C$${{Number(p.price || 0).toFixed(2)}}</div>
            <div class="tag">${{p.is_active ? "Activo en POS" : "Inactivo en POS"}}</div>
            <div class="tag">${{p.whatsapp_visible ? "Visible en WhatsApp" : "Oculto en WhatsApp"}}</div>

            <div class="mini-actions">
              <button class="mini-btn" onclick="toggleWhatsAppProduct(${{p.id}}, ${{!p.whatsapp_visible}})">
                ${{p.whatsapp_visible ? "Ocultar en WhatsApp" : "Mostrar en WhatsApp"}}
              </button>
            </div>
          </div>
        `).join("") : `<div class="muted">No hay productos cargados.</div>`;

        const visibleCount = whatsAppProducts.filter(x => x.whatsapp_visible).length;
        status.textContent = `Productos visibles en WhatsApp: ${{visibleCount}} de ${{whatsAppProducts.length}}`;
      }}

      async function toggleWhatsAppProduct(productId, visible) {{
        const res = await fetch(`/v2/api/admin/whatsapp-products/${{productId}}?restaurant=${{adminRestaurantSlug}}`, {{
          method: "PATCH",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ visible: !!visible }})
        }});
        const data = await res.json();

        if (!res.ok) {{
          alert(data.detail || "No se pudo actualizar la visibilidad.");
          return;
        }}

        await loadWhatsAppProducts();
        await previewWhatsAppMenu();
      }}

      function getWaTestPhone() {{
        return (document.getElementById("waTestPhone")?.value || "").trim();
      }}

      async function startWhatsAppSession() {{
        const phone = getWaTestPhone();
        const customer_name = (document.getElementById("waTestName")?.value || "").trim();

        const res = await fetch(`/v2/api/whatsapp/session/start?restaurant=${{adminRestaurantSlug}}`, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ phone, customer_name }})
        }});
        const data = await res.json();

        if (!res.ok) {{
          alert(data.detail || "No se pudo iniciar la sesión WhatsApp.");
          return;
        }}

        waTestSession = data.session || null;
        waTestSession = data.session || null;
        document.getElementById("waSessionStatus").textContent =
          `Sesión iniciada.\n\nEstado: ${{waTestSession?.state || ""}}\n\n${{data.menu_text || ""}}`;

        await loadWhatsAppProductsForLab();
        document.getElementById("waLabCartBox").textContent = "Carrito vacío.";
      }}

      async function refreshWhatsAppSession() {{
        const phone = getWaTestPhone();
        if (!phone) {{
          alert("Ingresa un teléfono para consultar.");
          return;
        }}

        const res = await fetch(`/v2/api/whatsapp/session?restaurant=${{adminRestaurantSlug}}&phone=${{encodeURIComponent(phone)}}`);
        const data = await res.json();

        if (!res.ok) {{
          alert(data.detail || "No se pudo consultar la sesión.");
          return;
        }}

        waTestSession = data.session || null;
        document.getElementById("waSessionStatus").textContent =
          `Estado: ${{waTestSession?.state || "sin estado"}}\n\n${{data.cart?.text || ""}}`;

        document.getElementById("waLabCartBox").textContent = data.cart?.text || "Carrito vacío.";
      }}

      async function confirmWhatsAppCart() {{
        const phone = getWaTestPhone();
        if (!phone) {{
          alert("Ingresa un teléfono.");
          return;
        }}

        const res = await fetch(`/v2/api/whatsapp/cart/confirm?restaurant=${{adminRestaurantSlug}}`, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ phone }})
        }});
        const data = await res.json();

        if (!res.ok) {{
          alert(data.detail || "No se pudo confirmar el carrito.");
          return;
        }}

        document.getElementById("waSessionStatus").textContent =
          `${{data.summary?.text || ""}}\n\n${{data.confirm_message || ""}}`;
      }}

      async function loadWhatsAppProductsForLab() {{
        const res = await fetch(`/v2/api/admin/whatsapp-products?restaurant=${{adminRestaurantSlug}}`);
        const data = await res.json();

        if (!res.ok) {{
          alert(data.detail || "No se pudo cargar productos del laboratorio.");
          return;
        }}

        waLabProducts = (data.items || []).filter(x => x.is_active && x.whatsapp_visible);
        renderWhatsAppLabProducts();
      }}

      function renderWhatsAppLabProducts() {{
        const box = document.getElementById("waLabProductsBox");

        box.innerHTML = waLabProducts.length ? waLabProducts.map(p => `
          <div class="card">
            <div class="card-title">${{p.name}}</div>
            <div class="muted">Categoría: ${{p.category || "General"}}</div>
            <div class="muted">Precio: C$${{Number(p.price || 0).toFixed(2)}}</div>

            <div class="mini-actions">
              <button class="mini-btn" onclick="addWhatsAppLabProduct(${{p.id}}, 1)">+1</button>
              <button class="mini-btn" onclick="addWhatsAppLabProduct(${{p.id}}, 2)">+2</button>
              <button class="mini-btn" onclick="removeWhatsAppLabProduct(${{p.id}}, 1)">-1</button>
            </div>
          </div>
        `).join("") : `<div class="muted">No hay productos visibles para WhatsApp.</div>`;
      }}

      async function addWhatsAppLabProduct(productId, quantity) {{
        const phone = getWaTestPhone();
        if (!phone) {{
          alert("Primero ingresa un teléfono e inicia sesión.");
          return;
        }}

        const res = await fetch(`/v2/api/whatsapp/cart/add?restaurant=${{adminRestaurantSlug}}`, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{
            phone,
            product_id: Number(productId),
            quantity: Number(quantity || 1)
          }})
        }});
        const data = await res.json();

        if (!res.ok) {{
          alert(data.detail || "No se pudo agregar el producto.");
          return;
        }}

        renderWhatsAppLabCartSummary(data.summary);
      }}

      async function removeWhatsAppLabProduct(productId, quantity) {{
        const phone = getWaTestPhone();
        if (!phone) {{
          alert("Primero ingresa un teléfono.");
          return;
        }}

        const res = await fetch(`/v2/api/whatsapp/cart/remove?restaurant=${{adminRestaurantSlug}}`, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{
            phone,
            product_id: Number(productId),
            quantity: Number(quantity || 1)
          }})
        }});
        const data = await res.json();

        if (!res.ok) {{
          alert(data.detail || "No se pudo quitar el producto.");
          return;
        }}

        renderWhatsAppLabCartSummary(data.summary);
      }}

      function renderWhatsAppLabCartSummary(summary) {{
        document.getElementById("waLabCartBox").textContent = summary?.text || "Carrito vacío.";
        document.getElementById("waSessionStatus").textContent =
          `Estado: editing_cart\n\n${{summary?.text || ""}}`;
      }}

      async function setWhatsAppDelivery() {{
        const phone = getWaTestPhone();
        if (!phone) {{
          alert("Ingresa un teléfono.");
          return;
        }}

        const payload = {{
          phone: phone,
          lat: Number(document.getElementById("waDeliveryLat").value || 0),
          lng: Number(document.getElementById("waDeliveryLng").value || 0),
          address: document.getElementById("waDeliveryAddress").value || "",
          district: document.getElementById("waDeliveryDistrict").value || "",
        }};

        const res = await fetch(`/v2/api/whatsapp/delivery/set?restaurant=${{adminRestaurantSlug}}`, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify(payload)
        }});

        const data = await res.json();

        if (!res.ok) {{
          alert(data.detail || "No se pudo guardar delivery.");
          return;
        }}

        document.getElementById("waDeliverySummaryBox").textContent = data.summary?.text || "";
        document.getElementById("waSessionStatus").textContent =
          `Estado: ${{data.session?.state || "sin estado"}}\n\n${{data.summary?.text || ""}}`;
      }}

      async function createOrderFromWhatsAppCart() {{
        const phone = getWaTestPhone();
        if (!phone) {{
          alert("Ingresa un teléfono.");
          return;
        }}

        const res = await fetch(`/v2/api/whatsapp/cart/create-order?restaurant=${{adminRestaurantSlug}}`, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ phone }})
        }});
        const data = await res.json();

        if (!res.ok) {{
          alert(data.detail || "No se pudo crear la orden.");
          return;
        }}

        document.getElementById("waLabCartBox").textContent =
          `Orden creada correctamente.\nID orden: ${{data.order_id}}\n\n${{data.order_received_message || ""}}`;

        document.getElementById("waSessionStatus").textContent =
          `Estado: ${{data.session?.state || ""}}\nÚltima orden: ${{data.order_id}}`;

        await refreshWhatsAppSession();
      }}

      async function saveDeliveryConfig() {{
        const payload = {{
          origin_lat: Number(document.getElementById("originLat").value || 0),
          origin_lng: Number(document.getElementById("originLng").value || 0),
          origin_address: document.getElementById("originAddress").value || "",
          price_per_km: Number(document.getElementById("pricePerKm").value || 0)
        }};

        const res = await fetch(`/v2/api/admin/delivery-config?restaurant=${{adminRestaurantSlug}}`, {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify(payload)
        }});

        const data = await res.json();

        document.getElementById("deliveryStatus").textContent =
          res.ok ? "Configuración delivery guardada." : (data.detail || "Error guardando delivery");
      }}
 
      function ensureLeafletLoaded() {{
        return typeof L !== "undefined";
      }}

      function setOriginInputs(lat, lng) {{
        document.getElementById("originLat").value = Number(lat).toFixed(6);
        document.getElementById("originLng").value = Number(lng).toFixed(6);
      }}

      function setCustomerInputs(lat, lng) {{
        document.getElementById("waDeliveryLat").value = Number(lat).toFixed(6);
        document.getElementById("waDeliveryLng").value = Number(lng).toFixed(6);
      }}

      function initOriginMap(lat = 12.136389, lng = -86.251389) {{
        if (!ensureLeafletLoaded()) return;

        if (originMap) {{
          originMap.remove();
        }}

        originMap = L.map("originMap").setView([lat, lng], 15);

        L.tileLayer("https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{
          maxZoom: 19,
          attribution: "&copy; OpenStreetMap"
        }}).addTo(originMap);

        originMarker = L.marker([lat, lng], {{ draggable: true }}).addTo(originMap);

        setOriginInputs(lat, lng);

        originMap.on("click", function(e) {{
          const latlng = e.latlng;
          originMarker.setLatLng(latlng);
          setOriginInputs(latlng.lat, latlng.lng);
        }});

        originMarker.on("dragend", function() {{
          const pos = originMarker.getLatLng();
          setOriginInputs(pos.lat, pos.lng);
        }});
      }}

      function initCustomerMap(lat = 12.136389, lng = -86.251389) {{
        if (!ensureLeafletLoaded()) return;
 
        if (customerMap) {{
          customerMap.remove();
        }}

        customerMap = L.map("customerMap").setView([lat, lng], 14);

        L.tileLayer("https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{
          maxZoom: 19,
          attribution: "&copy; OpenStreetMap"
        }}).addTo(customerMap);

        customerMarker = L.marker([lat, lng], {{ draggable: true }}).addTo(customerMap);

        setCustomerInputs(lat, lng);

        customerMap.on("click", function(e) {{
          const latlng = e.latlng;
          customerMarker.setLatLng(latlng);
          setCustomerInputs(latlng.lat, latlng.lng);
        }});

        customerMarker.on("dragend", function() {{
          const pos = customerMarker.getLatLng();
          setCustomerInputs(pos.lat, pos.lng);
        }});
      }}

      async function loadDeliveryConfig() {{
        const res = await fetch(`/v2/api/admin/delivery-config?restaurant=${{adminRestaurantSlug}}`);
        const data = await res.json();

        if (!res.ok) {{
          console.error(data.detail || "No se pudo cargar delivery config.");
          initOriginMap();
          initCustomerMap();
          return;
        }}

        const cfg = data.config || {{}};

        document.getElementById("originLat").value = cfg.origin_lat ?? "";
        document.getElementById("originLng").value = cfg.origin_lng ?? "";
        document.getElementById("originAddress").value = cfg.origin_address || "";
        document.getElementById("pricePerKm").value = cfg.price_per_km ?? "";

        const lat = Number(cfg.origin_lat || 12.136389);
        const lng = Number(cfg.origin_lng || -86.251389);

        initOriginMap(lat, lng);
        initCustomerMap(lat, lng);
      }}

      function useCurrentOriginLocation() {{
        if (!navigator.geolocation) {{
          alert("Tu navegador no soporta geolocalización.");
          return;
        }}

        navigator.geolocation.getCurrentPosition(
          function(pos) {{
            const lat = pos.coords.latitude;
            const lng = pos.coords.longitude;

            setOriginInputs(lat, lng);

            if (originMarker) {{
              originMarker.setLatLng([lat, lng]);
              originMap.setView([lat, lng], 16);
            }} else {{
              initOriginMap(lat, lng);
            }}
          }},
          function() {{
            alert("No se pudo obtener la ubicación actual.");
          }}
        );
      }}

      function useCurrentCustomerLocation() {{
        if (!navigator.geolocation) {{
          alert("Tu navegador no soporta geolocalización.");
          return;
        }}

        navigator.geolocation.getCurrentPosition(
          function(pos) {{
            const lat = pos.coords.latitude;
            const lng = pos.coords.longitude;

            setCustomerInputs(lat, lng);

            if (customerMarker) {{
              customerMarker.setLatLng([lat, lng]);
              customerMap.setView([lat, lng], 16);
            }} else {{
              initCustomerMap(lat, lng);
            }}
          }},
          function() {{
            alert("No se pudo obtener la ubicación actual del cliente.");
          }}
        );
      }}

      function setDistrictQuick(value) {{
        document.getElementById("waDeliveryDistrict").value = value;
      }}
   
      function renderWaMainMenu(items) {{
        const box = document.getElementById("waMainMenuBox");
        box.innerHTML = (items || []).map((item, idx) => `
          <div class="card">
            <div class="card-title">#${{idx + 1}} · ${{item.title || ""}}</div>
            <div class="muted">ID: ${{item.id || ""}}</div>
            <input class="input" id="waMainMenuTitle_${{idx}}" value="${{item.title || ""}}" placeholder="Título" />
            <input class="input" id="waMainMenuDesc_${{idx}}" value="${{item.description || ""}}" placeholder="Descripción" />
            <label><input type="checkbox" id="waMainMenuEnabled_${{idx}}" ${{item.enabled ? "checked" : ""}} /> Habilitado</label>
          </div>
        `).join("");
      }}

      function renderWaCategoryMenu(items) {{
        const box = document.getElementById("waCategoryMenuBox");
        if (!box) return;

        box.innerHTML = (items || []).map((item, idx) => `
          <div class="card">
            <div class="card-title">#${{idx + 1}} · ${{item.title || ""}}</div>
            <div class="muted">ID: ${{item.id || ""}}</div>
            <input class="input" id="waCategoryTitle_${{idx}}" value="${{item.title || ""}}" placeholder="Título categoría" />
            <input class="input" id="waCategoryDesc_${{idx}}" value="${{item.description || ""}}" placeholder="Descripción" />
            <input class="input" id="waCategoryImage_${{idx}}" value="${{item.image_url || ""}}" placeholder="Image URL" />
            <label><input type="checkbox" id="waCategoryEnabled_${{idx}}" ${{item.enabled ? "checked" : ""}} /> Habilitada</label>
          </div>
        `).join("");
      }}

    (async function bootAdmin() {{
      try {{
        await loadZones();
        await loadTables();
        await loadTenantConfig();
        await loadWhatsAppProducts();
        await loadDeliveryConfig();
        setTimeout(previewWhatsAppMenu, 300);
      }} catch (e) {{
        console.error("bootAdmin error:", e);
      }}
    }})();
    </script>
    """

    body = body.replace("__REST_SLUG__", str(rest.slug or ""))
    return html_shell("Admin", body)

# =========================
# API V2
# =========================

def serialize_product_row(p: Product) -> dict:
    return {
        "id": p.id,
        "name": p.name or "",
        "category": p.category or "",
        "price": float(p.price or 0),
        "description": p.description or "",
        "image_url": p.image_url or "",
        "is_active": bool(p.is_active),
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }

def normalize_category_name(value: str) -> str:
    name = (value or "").strip()
    return name if name else "General"

@app.get("/v2/api/restaurants")
def v2_api_restaurants(db: Session = Depends(get_db)):
    rows = db.query(Restaurant).order_by(Restaurant.id.asc()).all()
    return {
        "ok": True,
        "items": [
            {
                "id": r.id,
                "name": r.name,
                "slug": r.slug,
                "brand_name": r.brand_name,
                "tagline": r.tagline,
                "is_active": r.is_active,
            }
            for r in rows
        ],
    }


@app.get("/v2/api/modules")
def v2_api_modules(
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)
    rows = (
        db.query(RestaurantModule)
        .filter(RestaurantModule.restaurant_id == rest.id)
        .order_by(RestaurantModule.module_code.asc())
        .all()
    )
    return {
        "ok": True,
        "restaurant": {
            "id": rest.id,
            "name": rest.name,
            "slug": rest.slug,
        },
        "modules": [
            {
                "module_code": row.module_code,
                "is_enabled": row.is_enabled,
            }
            for row in rows
        ],
    }

@app.get("/v2/api/products")
def v2_api_products(
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    rows = (
        db.query(Product)
        .filter(
            Product.restaurant_id == rest.id,
            Product.is_active == True,  # noqa: E712
        )
        .order_by(Product.category.asc(), Product.name.asc())
        .all()
    )

    return {
        "ok": True,
        "restaurant": rest.slug,
        "items": [
            {
                "id": p.id,
                "name": p.name,
                "category": normalize_category_name(p.category),
                "price": float(p.price or 0),
                "description": p.description or "",
                "image_url": p.image_url or "",
            }
            for p in rows
        ],
    }

@app.get("/v2/api/admin/products")
def v2_api_admin_products(
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    rows = (
        db.query(Product)
        .filter(Product.restaurant_id == rest.id)
        .order_by(Product.category.asc(), Product.name.asc(), Product.id.asc())
        .all()
    )

    return {
        "ok": True,
        "restaurant": rest.slug,
        "items": [serialize_product_row(p) for p in rows],
    }


@app.post("/v2/api/products")
def v2_api_create_product(
    payload: ProductCreateInput,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="El nombre es obligatorio.")

    if Decimal(payload.price or 0) < 0:
        raise HTTPException(status_code=400, detail="El precio no puede ser negativo.")

    exists = (
        db.query(Product)
        .filter(
            Product.restaurant_id == rest.id,
            Product.name == name,
        )
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="Ya existe un producto con ese nombre.")

    product = Product(
        restaurant_id=rest.id,
        name=name,
        category=(payload.category or "").strip(),
        price=Decimal(payload.price or 0),
        description=(payload.description or "").strip(),
        image_url=(payload.image_url or "").strip(),
        is_active=bool(payload.is_active),
    )

    db.add(product)
    db.commit()
    db.refresh(product)

    return {
        "ok": True,
        "message": "Producto creado correctamente.",
        "product": serialize_product_row(product),
    }


@app.put("/v2/api/products/{product_id}")
def v2_api_update_product(
    product_id: int,
    payload: ProductUpdateInput,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    product = (
        db.query(Product)
        .filter(
            Product.id == product_id,
            Product.restaurant_id == rest.id,
        )
        .first()
    )

    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")

    if payload.name is not None:
        new_name = payload.name.strip()
        if not new_name:
            raise HTTPException(status_code=400, detail="El nombre no puede ir vacío.")

        duplicate = (
            db.query(Product)
            .filter(
                Product.restaurant_id == rest.id,
                Product.name == new_name,
                Product.id != product.id,
            )
            .first()
        )
        if duplicate:
            raise HTTPException(status_code=400, detail="Ya existe otro producto con ese nombre.")

        product.name = new_name

    if payload.category is not None:
        product.category = payload.category.strip()

    if payload.price is not None:
        if Decimal(payload.price) < 0:
            raise HTTPException(status_code=400, detail="El precio no puede ser negativo.")
        product.price = Decimal(payload.price)

    if payload.description is not None:
        product.description = payload.description.strip()

    if payload.image_url is not None:
        product.image_url = payload.image_url.strip()

    if payload.is_active is not None:
        product.is_active = bool(payload.is_active)

    db.commit()
    db.refresh(product)

    return {
        "ok": True,
        "message": "Producto actualizado correctamente.",
        "product": serialize_product_row(product),
    }


@app.patch("/v2/api/products/{product_id}/toggle")
def v2_api_toggle_product(
    product_id: int,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    product = (
        db.query(Product)
        .filter(
            Product.id == product_id,
            Product.restaurant_id == rest.id,
        )
        .first()
    )

    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")

    product.is_active = not bool(product.is_active)
    db.commit()
    db.refresh(product)

    return {
        "ok": True,
        "message": "Estado del producto actualizado.",
        "product": serialize_product_row(product),
    }


@app.delete("/v2/api/products/{product_id}")
def v2_api_delete_product(
    product_id: int,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    product = (
        db.query(Product)
        .filter(
            Product.id == product_id,
            Product.restaurant_id == rest.id,
        )
        .first()
    )

    if not product:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")

    used_in_orders = (
        db.query(OrderItem)
        .filter(OrderItem.product_id == product.id)
        .first()
    )

    if used_in_orders:
        product.is_active = False
        db.commit()
        db.refresh(product)
        return {
            "ok": True,
            "mode": "deactivated",
            "message": "El producto ya tiene historial. Se desactivó en lugar de eliminarse.",
            "product": serialize_product_row(product),
        }

    db.delete(product)
    db.commit()

    return {
        "ok": True,
        "mode": "deleted",
        "message": "Producto eliminado correctamente.",
    }

@app.get("/v2/api/categories")
def v2_api_categories(
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    rows = (
        db.query(Product.category)
        .filter(Product.restaurant_id == rest.id)
        .all()
    )

    raw_names = [normalize_category_name(r[0] if isinstance(r, tuple) else r.category) for r in rows]
    unique_names = sorted(set(raw_names), key=lambda x: x.lower())

    return {
        "ok": True,
        "restaurant": rest.slug,
        "items": unique_names,
    }


@app.patch("/v2/api/categories/rename")
def v2_api_rename_category(
    payload: CategoryRenameInput,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    old_name = normalize_category_name(payload.old_name)
    new_name = normalize_category_name(payload.new_name)

    if not new_name:
        raise HTTPException(status_code=400, detail="La nueva categoría es obligatoria.")

    rows = (
        db.query(Product)
        .filter(Product.restaurant_id == rest.id)
        .all()
    )

    updated = 0
    for p in rows:
        current = normalize_category_name(p.category)
        if current.lower() == old_name.lower():
            p.category = new_name
            updated += 1

    db.commit()

    return {
        "ok": True,
        "message": f"Categoría actualizada en {updated} producto(s).",
        "updated": updated,
        "old_name": old_name,
        "new_name": new_name,
    }


@app.patch("/v2/api/categories/delete")
def v2_api_delete_category(
    payload: CategoryDeleteInput,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    target_name = normalize_category_name(payload.name)
    replacement = normalize_category_name(payload.replacement)

    rows = (
        db.query(Product)
        .filter(Product.restaurant_id == rest.id)
        .all()
    )

    updated = 0
    for p in rows:
        current = normalize_category_name(p.category)
        if current.lower() == target_name.lower():
            p.category = replacement
            updated += 1

    db.commit()

    return {
        "ok": True,
        "message": f"Categoría reasignada en {updated} producto(s).",
        "updated": updated,
        "deleted_name": target_name,
        "replacement": replacement,
    }

@app.post("/v2/api/orders/create")
def v2_api_create_order(
    payload: CreateOrderInput,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    if not payload.items:
        raise HTTPException(status_code=400, detail="No hay items en la orden.")

    channel = (payload.channel or "").strip().lower()
    if channel not in ("local", "delivery", "pickup", "whatsapp"):
        raise HTTPException(status_code=400, detail="Canal inválido.")

    ids = [int(it.product_id) for it in payload.items]
    products = db.query(Product).filter(Product.restaurant_id == rest.id, Product.id.in_(ids)).all()
    product_map = {p.id: p for p in products}

    if len(product_map) != len(set(ids)):
        raise HTTPException(status_code=400, detail="Hay productos inválidos o que no pertenecen al restaurante.")

    base_subtotal = Decimal("0")
    line_items = []

    for it in payload.items:
        product = product_map.get(int(it.product_id))
        qty = to_decimal(getattr(it, "quantity", 0))
        if qty <= 0:
            raise HTTPException(status_code=400, detail="Cantidad inválida.")
        price = to_decimal(product.price or 0)
        line_total = price * qty
        base_subtotal += line_total
        line_items.append(
            {
                "product": product,
                "qty": qty,
                "price": price,
                "line_total": line_total,
            }
        )

    meta = parse_pipe_notes_meta(payload.notes or "")
    discount_percent = Decimal(str(meta.get("discountpercent", "0") or "0"))
    if discount_percent < 0:
        discount_percent = Decimal("0")
    if discount_percent > 100:
        discount_percent = Decimal("100")

    discount_amount = (base_subtotal * discount_percent) / Decimal("100")
    taxable_subtotal = base_subtotal - discount_amount
    if taxable_subtotal < 0:
        taxable_subtotal = Decimal("0")

    tax_rate = get_tax_rate_decimal(db, rest.id)
    tax = Decimal("0")
    if tax_rate > 0:
        tax = (taxable_subtotal * tax_rate) / Decimal("100")

    total = taxable_subtotal + tax

    order = Order(
        restaurant_id=rest.id,
        channel=channel,
        status="pending",
        customer_name=(payload.customer_name or "").strip(),
        customer_phone=(payload.customer_phone or "").strip(),
        table_number=(payload.table_number or "").strip(),
        subtotal=taxable_subtotal,
        tax=tax,
        total=total,
        payment_status="pending",
        notes=(payload.notes or "").strip(),
    )
    db.add(order)
    db.flush()

    for li in line_items:
        db.add(
            OrderItem(
                order_id=order.id,
                product_id=li["product"].id,
                product_name_snapshot=li["product"].name,
                quantity=li["qty"],
                unit_price=li["price"],
                total_price=li["qty"] * li["price"],
                notes=None
            )
        )

    db.commit()
    db.refresh(order)

    return {
        "ok": True,
        "order": {
            "id": order.id,
            "channel": order.channel,
            "status": order.status,
            "subtotal": float(order.subtotal or 0),
            "tax": float(order.tax or 0),
            "total": float(order.total or 0),
            "payment_status": order.payment_status or "",
            "discount_percent": float(discount_percent),
            "discount_amount": float(discount_amount),
        },
    }

def serialize_zone_row(z: RestaurantZone) -> dict:
    return {
        "id": z.id,
        "restaurant_id": z.restaurant_id,
        "name": z.name,
        "sort_order": z.sort_order or 0,
        "is_active": bool(z.is_active),
        "created_at": str(z.created_at or ""),
    }


def serialize_table_row(t: RestaurantTable) -> dict:
    return {
        "id": t.id,
        "restaurant_id": t.restaurant_id,
        "zone_id": t.zone_id,
        "code": t.code,
        "display_name": t.display_name,
        "capacity": t.capacity or 4,
        "sort_order": t.sort_order or 0,
        "is_active": bool(t.is_active),
        "created_at": str(t.created_at or ""),
    }


def serialize_local_order_item_row(it: OrderItem) -> dict:
    return {
        "id": it.id,
        "order_id": it.order_id,
        "product_id": it.product_id,
        "product_name_snapshot": it.product_name_snapshot or "",
        "quantity": float(it.quantity or 0),
        "unit_price": float(it.unit_price or 0),
        "total_price": float(it.total_price or 0),
        "notes": it.notes or "",
        "sent_to_kitchen": bool(getattr(it, "sent_to_kitchen", False)),
        "sent_at": str(getattr(it, "sent_at", "") or ""),
        "kitchen_status": getattr(it, "kitchen_status", "draft") or "draft",
        "voided": bool(getattr(it, "voided", False)),
        "paid_quantity": float(getattr(it, "paid_quantity", 0) or 0),
        "pending_quantity": float(get_order_item_pending_quantity(it)),
    }


def serialize_local_order_row(order: Order, db: Session) -> dict:
    items = (
        db.query(OrderItem)
        .filter(OrderItem.order_id == order.id)
        .order_by(OrderItem.id.asc())
        .all()
    )

    active_items = [it for it in items if not bool(getattr(it, "voided", False))]
    unsent_items = [it for it in active_items if not bool(getattr(it, "sent_to_kitchen", False))]
    sent_items = [it for it in active_items if bool(getattr(it, "sent_to_kitchen", False))]

    subtotal = float(order.subtotal or 0)
    tax = float(order.tax or 0)
    total = float(order.total or 0)

    return {
        "id": order.id,
        "restaurant_id": order.restaurant_id,
        "channel": order.channel or "",
        "status": order.status or "",
        "service_mode": getattr(order, "service_mode", "quick") or "quick",
        "table_id": getattr(order, "table_id", None),
        "zone_id": getattr(order, "zone_id", None),
        "is_open": bool(getattr(order, "is_open", True)),
        "customer_name": order.customer_name or "",
        "customer_phone": order.customer_phone or "",
        "table_number": order.table_number or "",
        "payment_status": order.payment_status or "",
        "notes": order.notes or "",
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
        "created_at": str(order.created_at or ""),
        "closed_at": str(getattr(order, "closed_at", "") or ""),
        "items": [serialize_local_order_item_row(it) for it in active_items],
        "unsent_items": [serialize_local_order_item_row(it) for it in unsent_items],
        "sent_items": [serialize_local_order_item_row(it) for it in sent_items],
        "counts": {
            "all": len(active_items),
            "unsent": len(unsent_items),
            "sent": len(sent_items),
        }
    }


@app.get("/v2/api/zones")
def v2_api_zones(
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    rows = (
        db.query(RestaurantZone)
        .filter(RestaurantZone.restaurant_id == rest.id)
        .order_by(RestaurantZone.sort_order.asc(), RestaurantZone.id.asc())
        .all()
    )

    return {
        "ok": True,
        "restaurant": rest.slug,
        "items": [serialize_zone_row(z) for z in rows],
    }


@app.post("/v2/api/zones")
def v2_api_create_zone(
    payload: ZoneCreateInput,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="El nombre de la zona es obligatorio.")

    exists = (
        db.query(RestaurantZone)
        .filter(
            RestaurantZone.restaurant_id == rest.id,
            RestaurantZone.name == name,
        )
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="Ya existe una zona con ese nombre.")

    row = RestaurantZone(
        restaurant_id=rest.id,
        name=name,
        sort_order=payload.sort_order or 0,
        is_active=bool(payload.is_active),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return {
        "ok": True,
        "item": serialize_zone_row(row),
    }


@app.put("/v2/api/zones/{zone_id}")
def v2_api_update_zone(
    zone_id: int,
    payload: ZoneUpdateInput,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    row = (
        db.query(RestaurantZone)
        .filter(
            RestaurantZone.id == zone_id,
            RestaurantZone.restaurant_id == rest.id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Zona no encontrada.")

    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="El nombre de la zona es obligatorio.")
        row.name = name

    if payload.sort_order is not None:
        row.sort_order = payload.sort_order

    if payload.is_active is not None:
        row.is_active = bool(payload.is_active)

    db.commit()
    db.refresh(row)

    return {
        "ok": True,
        "item": serialize_zone_row(row),
    }


@app.patch("/v2/api/zones/{zone_id}/toggle")
def v2_api_toggle_zone(
    zone_id: int,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    row = (
        db.query(RestaurantZone)
        .filter(
            RestaurantZone.id == zone_id,
            RestaurantZone.restaurant_id == rest.id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Zona no encontrada.")

    row.is_active = not bool(row.is_active)
    db.commit()
    db.refresh(row)

    return {
        "ok": True,
        "item": serialize_zone_row(row),
    }


@app.get("/v2/api/tables")
def v2_api_tables(
    restaurant: Optional[str] = Query(None),
    zone_id: Optional[int] = Query(None),
    active_only: bool = Query(False),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    query = db.query(RestaurantTable).filter(RestaurantTable.restaurant_id == rest.id)

    if zone_id is not None:
        query = query.filter(RestaurantTable.zone_id == zone_id)

    if active_only:
        query = query.filter(RestaurantTable.is_active == True)  # noqa: E712

    rows = query.order_by(RestaurantTable.sort_order.asc(), RestaurantTable.id.asc()).all()

    return {
        "ok": True,
        "restaurant": rest.slug,
        "items": [serialize_table_row(t) for t in rows],
    }


@app.post("/v2/api/tables")
def v2_api_create_table(
    payload: TableCreateInput,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    code = (payload.code or "").strip()
    display_name = (payload.display_name or "").strip()

    if not code:
        raise HTTPException(status_code=400, detail="El código de la mesa es obligatorio.")
    if not display_name:
        raise HTTPException(status_code=400, detail="El nombre visible de la mesa es obligatorio.")

    if payload.zone_id is not None:
        zone = (
            db.query(RestaurantZone)
            .filter(
                RestaurantZone.id == payload.zone_id,
                RestaurantZone.restaurant_id == rest.id,
            )
            .first()
        )
        if not zone:
            raise HTTPException(status_code=400, detail="La zona seleccionada no existe.")

    exists = (
        db.query(RestaurantTable)
        .filter(
            RestaurantTable.restaurant_id == rest.id,
            RestaurantTable.code == code,
        )
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="Ya existe una mesa con ese código.")

    row = RestaurantTable(
        restaurant_id=rest.id,
        zone_id=payload.zone_id,
        code=code,
        display_name=display_name,
        capacity=payload.capacity or 4,
        sort_order=payload.sort_order or 0,
        is_active=bool(payload.is_active),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return {
        "ok": True,
        "item": serialize_table_row(row),
    }


@app.put("/v2/api/tables/{table_id}")
def v2_api_update_table(
    table_id: int,
    payload: TableUpdateInput,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    row = (
        db.query(RestaurantTable)
        .filter(
            RestaurantTable.id == table_id,
            RestaurantTable.restaurant_id == rest.id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Mesa no encontrada.")

    if payload.zone_id is not None:
        zone = (
            db.query(RestaurantZone)
            .filter(
                RestaurantZone.id == payload.zone_id,
                RestaurantZone.restaurant_id == rest.id,
            )
            .first()
        )
        if not zone:
            raise HTTPException(status_code=400, detail="La zona seleccionada no existe.")
        row.zone_id = payload.zone_id

    if payload.code is not None:
        code = payload.code.strip()
        if not code:
            raise HTTPException(status_code=400, detail="El código de la mesa es obligatorio.")
        row.code = code

    if payload.display_name is not None:
        display_name = payload.display_name.strip()
        if not display_name:
            raise HTTPException(status_code=400, detail="El nombre visible de la mesa es obligatorio.")
        row.display_name = display_name

    if payload.capacity is not None:
        row.capacity = payload.capacity

    if payload.sort_order is not None:
        row.sort_order = payload.sort_order

    if payload.is_active is not None:
        row.is_active = bool(payload.is_active)

    db.commit()
    db.refresh(row)

    return {
        "ok": True,
        "item": serialize_table_row(row),
    }


@app.patch("/v2/api/tables/{table_id}/toggle")
def v2_api_toggle_table(
    table_id: int,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    row = (
        db.query(RestaurantTable)
        .filter(
            RestaurantTable.id == table_id,
            RestaurantTable.restaurant_id == rest.id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Mesa no encontrada.")

    row.is_active = not bool(row.is_active)
    db.commit()
    db.refresh(row)

    return {
        "ok": True,
        "item": serialize_table_row(row),
    }


@app.delete("/v2/api/tables/{table_id}")
def v2_api_delete_table(
    table_id: int,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    row = (
        db.query(RestaurantTable)
        .filter(
            RestaurantTable.id == table_id,
            RestaurantTable.restaurant_id == rest.id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Mesa no encontrada.")

    open_order = (
        db.query(Order)
        .filter(
            Order.restaurant_id == rest.id,
            Order.table_id == row.id,
            Order.is_open == True,  # noqa: E712
        )
        .first()
    )
    if open_order:
        raise HTTPException(status_code=400, detail="No puedes eliminar una mesa con cuenta abierta.")

    db.delete(row)
    db.commit()

    return {
        "ok": True,
        "deleted_id": table_id,
    }


@app.get("/v2/api/floor")
def v2_api_floor(
    restaurant: Optional[str] = Query(None),
    zone_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    zone_query = db.query(RestaurantZone).filter(RestaurantZone.restaurant_id == rest.id)
    if zone_id is not None:
        zone_query = zone_query.filter(RestaurantZone.id == zone_id)
    zones = zone_query.order_by(RestaurantZone.sort_order.asc(), RestaurantZone.id.asc()).all()

    tables_query = db.query(RestaurantTable).filter(
        RestaurantTable.restaurant_id == rest.id,
        RestaurantTable.is_active == True,  # noqa: E712
    )
    if zone_id is not None:
        tables_query = tables_query.filter(RestaurantTable.zone_id == zone_id)
    tables = tables_query.order_by(RestaurantTable.sort_order.asc(), RestaurantTable.id.asc()).all()

    open_orders = (
        db.query(Order)
        .filter(
            Order.restaurant_id == rest.id,
            Order.is_open == True,  # noqa: E712
            Order.service_mode.in_(["table", "bar"]),
        )
        .order_by(Order.id.desc())
        .all()
    )

    open_by_table_id = {}
    for order in open_orders:
        if getattr(order, "table_id", None) and order.table_id not in open_by_table_id:
            open_by_table_id[order.table_id] = order

    table_cards = []
    for t in tables:
        active_order = open_by_table_id.get(t.id)
        status = "free"
        total = 0.0
        unsent_count = 0
        order_id = None

        if active_order:
            order_id = active_order.id
            total = float(active_order.total or 0)
            status = active_order.status or "open"

            unsent_count = (
                db.query(OrderItem)
                .filter(
                    OrderItem.order_id == active_order.id,
                    OrderItem.voided == False,  # noqa: E712
                    OrderItem.sent_to_kitchen == False,  # noqa: E712
                )
                .count()
            )

        table_cards.append({
            "table": serialize_table_row(t),
            "zone_name": next((z.name for z in zones if z.id == t.zone_id), ""),
            "active_order_id": order_id,
            "status": status,
            "total": total,
            "unsent_count": unsent_count,
        })

    bar_open_order = (
        db.query(Order)
        .filter(
            Order.restaurant_id == rest.id,
            Order.is_open == True,  # noqa: E712
            Order.service_mode == "bar",
            Order.table_id == None,  # noqa: E711
        )
        .order_by(Order.id.desc())
        .first()
    )

    return {
        "ok": True,
        "restaurant": rest.slug,
        "zones": [serialize_zone_row(z) for z in zones],
        "tables": table_cards,
        "bar": {
            "active_order_id": bar_open_order.id if bar_open_order else None,
            "status": (bar_open_order.status or "free") if bar_open_order else "free",
            "total": float(bar_open_order.total or 0) if bar_open_order else 0.0,
        }
    }


@app.post("/v2/api/local/open-ticket")
def v2_api_open_local_ticket(
    payload: OpenLocalTicketInput,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    service_mode = (payload.service_mode or "").strip().lower()
    if service_mode not in {"table", "bar", "quick"}:
        raise HTTPException(status_code=400, detail="Modo de servicio inválido.")

    table = None
    zone_id = payload.zone_id

    if service_mode == "table":
        if not payload.table_id:
            raise HTTPException(status_code=400, detail="Debes seleccionar una mesa.")
        table = (
            db.query(RestaurantTable)
            .filter(
                RestaurantTable.id == payload.table_id,
                RestaurantTable.restaurant_id == rest.id,
                RestaurantTable.is_active == True,  # noqa: E712
            )
            .first()
        )
        if not table:
            raise HTTPException(status_code=404, detail="Mesa no encontrada.")
        zone_id = table.zone_id

        existing_open = (
            db.query(Order)
            .filter(
                Order.restaurant_id == rest.id,
                Order.table_id == table.id,
                Order.is_open == True,  # noqa: E712
            )
            .order_by(Order.id.desc())
            .first()
        )
        if existing_open:
            return {
                "ok": True,
                "existing": True,
                "ticket": serialize_local_order_row(existing_open, db),
            }

    if service_mode == "bar":
        existing_bar = (
            db.query(Order)
            .filter(
                Order.restaurant_id == rest.id,
                Order.service_mode == "bar",
                Order.is_open == True,  # noqa: E712
                Order.table_id == None,  # noqa: E711
            )
            .order_by(Order.id.desc())
            .first()
        )
        if existing_bar:
            return {
                "ok": True,
                "existing": True,
                "ticket": serialize_local_order_row(existing_bar, db),
            }

    order = Order(
        restaurant_id=rest.id,
        channel="local",
        status="open",
        service_mode=service_mode,
        table_id=payload.table_id if service_mode == "table" else None,
        zone_id=zone_id,
        is_open=True,
        customer_name=(payload.customer_name or "").strip(),
        customer_phone=(payload.customer_phone or "").strip(),
        table_number=(table.display_name if table else ""),
        subtotal=Decimal("0"),
        tax=Decimal("0"),
        total=Decimal("0"),
        payment_status="pending",
        notes=(payload.notes or "").strip(),
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    return {
        "ok": True,
        "existing": False,
        "ticket": serialize_local_order_row(order, db),
    }


@app.get("/v2/api/local/ticket/{order_id}")
def v2_api_local_ticket_detail(
    order_id: int,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    order = (
        db.query(Order)
        .filter(
            Order.id == order_id,
            Order.restaurant_id == rest.id,
        )
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Ticket no encontrado.")

    return {
        "ok": True,
        "ticket": serialize_local_order_row(order, db),
    }


@app.get("/v2/api/tables/{table_id}/active-ticket")
def v2_api_table_active_ticket(
    table_id: int,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    table = (
        db.query(RestaurantTable)
        .filter(
            RestaurantTable.id == table_id,
            RestaurantTable.restaurant_id == rest.id,
        )
        .first()
    )
    if not table:
        raise HTTPException(status_code=404, detail="Mesa no encontrada.")

    order = (
        db.query(Order)
        .filter(
            Order.restaurant_id == rest.id,
            Order.table_id == table.id,
            Order.is_open == True,  # noqa: E712
        )
        .order_by(Order.id.desc())
        .first()
    )

    return {
        "ok": True,
        "table": serialize_table_row(table),
        "ticket": serialize_local_order_row(order, db) if order else None,
    }


@app.post("/v2/api/local/ticket/{order_id}/items/add")
def v2_api_add_items_to_open_ticket(
    order_id: int,
    payload: AddItemsToOpenTicketInput,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    order = (
        db.query(Order)
        .filter(
            Order.id == order_id,
            Order.restaurant_id == rest.id,
            Order.is_open == True,  # noqa: E712
        )
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Ticket abierto no encontrado.")

    if not payload.items:
        raise HTTPException(status_code=400, detail="Debes agregar al menos un producto.")

    ids = [int(it.product_id) for it in payload.items]
    products = (
        db.query(Product)
        .filter(
            Product.restaurant_id == rest.id,
            Product.id.in_(ids),
            Product.is_active == True,  # noqa: E712
        )
        .all()
    )
    product_map = {p.id: p for p in products}

    if len(product_map) != len(set(ids)):
        raise HTTPException(status_code=400, detail="Hay productos inválidos o inactivos.")

    running_subtotal = Decimal(str(order.subtotal or 0))

    for it in payload.items:
        product = product_map.get(int(it.product_id))
        qty = Decimal(str(it.quantity or 0))
        if qty <= 0:
            raise HTTPException(status_code=400, detail="La cantidad debe ser mayor que cero.")

        unit_price = to_decimal(product.price or 0)
        line_total = unit_price * qty

        row = OrderItem(
            order_id=order.id,
            product_id=product.id,
            product_name_snapshot=product.name,
            quantity=qty,
            unit_price=unit_price,
            total_price=line_total,
            notes=(it.notes or "").strip() or None,
            sent_to_kitchen=False,
            sent_at=None,
            kitchen_status="draft",
            voided=False,
            paid_quantity=Decimal("0"),
        )
        db.add(row)
        running_subtotal += line_total

    order.subtotal = running_subtotal
    tax_rate = get_tax_rate_decimal(db, rest.id)
    tax = Decimal("0")
    if tax_rate > 0:
        tax = (running_subtotal * tax_rate) / Decimal("100")
    order.tax = tax
    order.total = running_subtotal + tax

    if order.status in ("paid", "closed", "cancelled"):
        order.status = "open"
    if not order.payment_status:
        order.payment_status = "pending"

    db.commit()
    db.refresh(order)

    return {
        "ok": True,
        "ticket": serialize_local_order_row(order, db),
    }


@app.post("/v2/api/local/ticket/{order_id}/send-new-items")
def v2_api_send_new_items_to_kitchen(
    order_id: int,
    payload: SendNewItemsInput,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    order = (
        db.query(Order)
        .filter(
            Order.id == order_id,
            Order.restaurant_id == rest.id,
            Order.is_open == True,  # noqa: E712
        )
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Ticket abierto no encontrado.")

    query = db.query(OrderItem).filter(
        OrderItem.order_id == order.id,
        OrderItem.voided == False,  # noqa: E712
        OrderItem.sent_to_kitchen == False,  # noqa: E712
    )

    if payload.item_ids:
        query = query.filter(OrderItem.id.in_(payload.item_ids))

    rows = query.order_by(OrderItem.id.asc()).all()

    if not rows:
        raise HTTPException(status_code=400, detail="No hay productos nuevos para enviar a cocina.")

    now_dt = datetime.utcnow()
    for row in rows:
        row.sent_to_kitchen = True
        row.sent_at = now_dt
        row.kitchen_status = "sent"

    if order.status in ("open", "pending", ""):
        order.status = "preparing"

    db.commit()
    db.refresh(order)

    return {
        "ok": True,
        "sent_count": len(rows),
        "ticket": serialize_local_order_row(order, db),
    }

@app.get("/v2/api/orders")
def v2_api_orders(
    restaurant: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    query = db.query(Order).filter(Order.restaurant_id == rest.id)

    if channel:
        query = query.filter(Order.channel == channel)

    rows = query.order_by(Order.id.desc()).limit(100).all()

    return {
        "ok": True,
        "restaurant": rest.slug,
        "items": [
            {
                "id": o.id,
                "channel": o.channel,
                "status": o.status,
                "customer_name": o.customer_name or "",
                "customer_phone": o.customer_phone or "",
                "table_number": o.table_number or "",
                "subtotal": float(o.subtotal or 0),
                "tax": float(o.tax or 0),
                "total": float(o.total or 0),
                "payment_status": o.payment_status or "",
                "notes": o.notes or "",
                "created_at": str(o.created_at or ""),
            }
            for o in rows
        ],
    }

@app.post("/v2/api/orders/{order_id}/status")
def update_order_status(
    order_id: int,
    status: str,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    order = db.query(Order).filter(
        Order.id == order_id,
        Order.restaurant_id == rest.id
    ).first()

    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada")

    allowed = ["pending", "in_kitchen", "ready", "delivered", "cancelled"]

    if status not in allowed:
        raise HTTPException(status_code=400, detail="Estado inválido")

    order.status = status

    db.commit()
    db.refresh(order)

    return {
        "ok": True,
        "order_id": order.id,
        "new_status": order.status
    }

@app.get("/v2/api/users")
def v2_api_users(
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)
    return {
        "ok": True,
        "restaurant": rest.slug,
        "users": [],
        "message": "Migración de usuarios pendiente en siguiente bloque."
    }

def get_order_paid_amount(db: Session, order_id: int) -> Decimal:
    rows = (
        db.query(OrderPayment)
        .filter(OrderPayment.order_id == order_id)
        .all()
    )
    total = Decimal("0")
    for r in rows:
        total += Decimal(str(r.amount or 0))
    return total


def get_order_balance_due(db: Session, order: Order) -> Decimal:
    total = Decimal(str(order.total or 0))
    paid = get_order_paid_amount(db, order.id)
    balance = total - paid
    if balance < 0:
        balance = Decimal("0")
    return balance


@app.get("/v2/api/local/ticket/{order_id}/payments")
def v2_api_local_ticket_payments(
    order_id: int,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    order = (
        db.query(Order)
        .filter(
            Order.id == order_id,
            Order.restaurant_id == rest.id,
        )
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Ticket no encontrado.")

    rows = (
        db.query(OrderPayment)
        .filter(OrderPayment.order_id == order.id)
        .order_by(OrderPayment.id.asc())
        .all()
    )

    paid_amount = get_order_paid_amount(db, order.id)
    balance_due = get_order_balance_due(db, order)

    return {
        "ok": True,
        "order_id": order.id,
        "paid_amount": float(paid_amount),
        "balance_due": float(balance_due),
        "items": [
            {
                "id": r.id,
                "method": r.method or "",
                "status": r.status or "",
                "amount": float(r.amount or 0),
                "reference": r.reference or "",
                "bank_name": r.bank_name or "",
                "terminal_id": r.terminal_id or "",
                "authorization_code": r.authorization_code or "",
                "card_brand": r.card_brand or "",
                "card_last4": r.card_last4 or "",
            }
            for r in rows
        ]
    }

def allocate_payment_to_order_items(db: Session, order: Order, payment_amount: Decimal) -> None:
    remaining = Decimal(str(payment_amount or 0))
    if remaining <= 0:
        return

    items = (
        db.query(OrderItem)
        .filter(
            OrderItem.order_id == order.id,
            OrderItem.voided == False,  # noqa: E712
        )
        .order_by(OrderItem.id.asc())
        .all()
    )

    for it in items:
        if remaining <= 0:
            break

        pending_qty = get_order_item_pending_quantity(it)
        if pending_qty <= 0:
            continue

        unit_price = Decimal(str(it.unit_price or 0))
        if unit_price <= 0:
            continue

        pending_amount = pending_qty * unit_price
        if pending_amount <= 0:
            continue

        if remaining >= pending_amount:
            qty_to_apply = pending_qty
            remaining -= pending_amount
        else:
            qty_to_apply = remaining / unit_price
            remaining = Decimal("0")

        current_paid = Decimal(str(getattr(it, "paid_quantity", 0) or 0))
        it.paid_quantity = current_paid + qty_to_apply

@app.post("/v2/api/local/ticket/{order_id}/pay-split")
def v2_api_local_ticket_pay_split(
    order_id: int,
    payload: SplitPaymentInput,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    order = (
        db.query(Order)
        .filter(
            Order.id == order_id,
            Order.restaurant_id == rest.id,
        )
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Ticket no encontrado.")

    if not payload.payments:
        raise HTTPException(status_code=400, detail="Debes enviar al menos un pago.")

    balance_before = get_order_balance_due(db, order)
    if balance_before <= 0:
        raise HTTPException(status_code=400, detail="El ticket ya está completamente pagado.")

    incoming_total = Decimal("0")
    created = []

    for p in payload.payments:
        method = (p.method or "").strip().lower()
        if not method:
            raise HTTPException(status_code=400, detail="Cada pago debe tener método.")
        amount = Decimal(str(p.amount or 0))
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Cada pago debe ser mayor que cero.")

        incoming_total += amount

        row = OrderPayment(
            order_id=order.id,
            method=method,
            status="approved",
            amount=amount,
            reference=(p.reference or "").strip(),
            bank_name=(p.bank_name or "").strip(),
            terminal_id=(p.terminal_id or "").strip(),
            authorization_code=(p.authorization_code or "").strip(),
            card_brand=(p.card_brand or "").strip(),
            card_last4=(p.card_last4 or "").strip(),
        )
        db.add(row)
        created.append(row)

    if incoming_total > balance_before:
        raise HTTPException(
            status_code=400,
            detail=f"Los pagos enviados ({float(incoming_total):.2f}) superan el saldo pendiente ({float(balance_before):.2f})."
        )
    
    allocate_payment_to_order_items(db, order, incoming_total)

    db.commit()

    paid_amount = get_order_paid_amount(db, order.id)
    balance_due = get_order_balance_due(db, order)

    if balance_due <= 0:
        order.payment_status = "paid"
        order.status = "paid"
        if getattr(order, "is_open", True):
            order.is_open = False
        order.closed_at = datetime.utcnow()
    else:
        order.payment_status = "partial"
        if order.status in ("", None, "open"):
            order.status = "open"

    db.commit()
    db.refresh(order)

    return {
        "ok": True,
        "order_id": order.id,
        "paid_amount": float(paid_amount),
        "balance_due": float(balance_due),
        "ticket_status": order.status or "",
        "payment_status": order.payment_status or "",
        "closed_at": str(getattr(order, "closed_at", "") or ""),
    }

def get_order_item_pending_quantity(it: OrderItem) -> Decimal:
    qty = Decimal(str(it.quantity or 0))
    paid_qty = Decimal(str(getattr(it, "paid_quantity", 0) or 0))
    pending = qty - paid_qty
    if pending < 0:
        pending = Decimal("0")
    return pending


def get_order_item_pending_amount(it: OrderItem) -> Decimal:
    pending_qty = get_order_item_pending_quantity(it)
    unit_price = Decimal(str(it.unit_price or 0))
    total = pending_qty * unit_price
    if total < 0:
        total = Decimal("0")
    return total


@app.get("/v2/api/local/ticket/{order_id}/split-preview")
def v2_api_local_ticket_split_preview(
    order_id: int,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    order = (
        db.query(Order)
        .filter(
            Order.id == order_id,
            Order.restaurant_id == rest.id,
        )
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Ticket no encontrado.")

    items = (
        db.query(OrderItem)
        .filter(
            OrderItem.order_id == order.id,
            OrderItem.voided == False,  # noqa: E712
        )
        .order_by(OrderItem.id.asc())
        .all()
    )

    preview_items = []
    split_total = Decimal("0")

    for it in items:
        pending_qty = get_order_item_pending_quantity(it)
        if pending_qty <= 0:
            continue

        pending_amount = get_order_item_pending_amount(it)
        split_total += pending_amount

        preview_items.append({
            "order_item_id": it.id,
            "product_id": it.product_id,
            "product_name_snapshot": it.product_name_snapshot or "",
            "quantity": float(it.quantity or 0),
            "paid_quantity": float(getattr(it, "paid_quantity", 0) or 0),
            "pending_quantity": float(pending_qty),
            "unit_price": float(it.unit_price or 0),
            "pending_amount": float(pending_amount),
            "notes": it.notes or "",
            "sent_to_kitchen": bool(getattr(it, "sent_to_kitchen", False)),
        })

    return {
        "ok": True,
        "order_id": order.id,
        "items": preview_items,
        "pending_total": float(split_total),
    }


@app.post("/v2/api/local/ticket/{order_id}/pay-items")
def v2_api_local_ticket_pay_items(
    order_id: int,
    payload: SplitItemsInput,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    order = (
        db.query(Order)
        .filter(
            Order.id == order_id,
            Order.restaurant_id == rest.id,
        )
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Ticket no encontrado.")

    if not payload.items:
        raise HTTPException(status_code=400, detail="Debes seleccionar al menos una línea.")

    requested_ids = [int(x.order_item_id) for x in payload.items]
    rows = (
        db.query(OrderItem)
        .filter(
            OrderItem.order_id == order.id,
            OrderItem.id.in_(requested_ids),
            OrderItem.voided == False,  # noqa: E712
        )
        .all()
    )
    row_map = {r.id: r for r in rows}

    if len(row_map) != len(set(requested_ids)):
        raise HTTPException(status_code=400, detail="Hay líneas inválidas en la selección.")

    selected_items = []
    split_total = Decimal("0")

    for x in payload.items:
        row = row_map.get(int(x.order_item_id))
        if not row:
            raise HTTPException(status_code=400, detail="Línea inválida.")

        req_qty = Decimal(str(x.quantity or 0))
        if req_qty <= 0:
            raise HTTPException(status_code=400, detail="La cantidad a pagar debe ser mayor que cero.")

        pending_qty = get_order_item_pending_quantity(row)
        if req_qty > pending_qty:
            raise HTTPException(
                status_code=400,
                detail=f"La línea {row.product_name_snapshot or row.id} solo tiene {float(pending_qty):.2f} pendiente(s)."
            )

        unit_price = Decimal(str(row.unit_price or 0))
        line_total = req_qty * unit_price
        split_total += line_total

        selected_items.append({
            "row": row,
            "requested_qty": req_qty,
            "unit_price": unit_price,
            "line_total": line_total,
        })

    balance_due = get_order_balance_due(db, order)
    if split_total > balance_due:
        raise HTTPException(
            status_code=400,
            detail=f"La selección ({float(split_total):.2f}) supera el saldo pendiente ({float(balance_due):.2f})."
        )

    return {
        "ok": True,
        "order_id": order.id,
        "items": [
            {
                "order_item_id": s["row"].id,
                "product_name_snapshot": s["row"].product_name_snapshot or "",
                "requested_quantity": float(s["requested_qty"]),
                "unit_price": float(s["unit_price"]),
                "line_total": float(s["line_total"]),
            }
            for s in selected_items
        ],
        "split_total": float(split_total),
        "balance_before": float(balance_due),
        "balance_after": float(balance_due - split_total),
    }


class SplitItemsPaymentInput(BaseModel):
    items: List[SplitItemLineInput]
    method: str
    reference: str = ""
    bank_name: str = ""
    terminal_id: str = ""
    authorization_code: str = ""
    card_brand: str = ""
    card_last4: str = ""


@app.post("/v2/api/local/ticket/{order_id}/pay-selected-items")
def v2_api_local_ticket_pay_selected_items(
    order_id: int,
    payload: SplitItemsPaymentInput,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    order = (
        db.query(Order)
        .filter(
            Order.id == order_id,
            Order.restaurant_id == rest.id,
        )
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Ticket no encontrado.")

    if not payload.items:
        raise HTTPException(status_code=400, detail="Debes seleccionar al menos una línea.")

    method = (payload.method or "").strip().lower()
    if not method:
        raise HTTPException(status_code=400, detail="El método de pago es obligatorio.")

    requested_ids = [int(x.order_item_id) for x in payload.items]
    rows = (
        db.query(OrderItem)
        .filter(
            OrderItem.order_id == order.id,
            OrderItem.id.in_(requested_ids),
            OrderItem.voided == False,  # noqa: E712
        )
        .all()
    )
    row_map = {r.id: r for r in rows}

    if len(row_map) != len(set(requested_ids)):
        raise HTTPException(status_code=400, detail="Hay líneas inválidas en la selección.")

    split_total = Decimal("0")
    applied = []

    for x in payload.items:
        row = row_map.get(int(x.order_item_id))
        req_qty = Decimal(str(x.quantity or 0))
        if req_qty <= 0:
            raise HTTPException(status_code=400, detail="La cantidad a pagar debe ser mayor que cero.")

        pending_qty = get_order_item_pending_quantity(row)
        if req_qty > pending_qty:
            raise HTTPException(
                status_code=400,
                detail=f"La línea {row.product_name_snapshot or row.id} solo tiene {float(pending_qty):.2f} pendiente(s)."
            )

        unit_price = Decimal(str(row.unit_price or 0))
        line_total = req_qty * unit_price
        split_total += line_total

        applied.append({
            "row": row,
            "requested_qty": req_qty,
            "line_total": line_total,
        })

    balance_due = get_order_balance_due(db, order)
    if split_total > balance_due:
        raise HTTPException(
            status_code=400,
            detail=f"La selección ({float(split_total):.2f}) supera el saldo pendiente ({float(balance_due):.2f})."
        )

    payment = OrderPayment(
        order_id=order.id,
        method=method,
        status="approved",
        amount=split_total,
        reference=(payload.reference or "").strip(),
        bank_name=(payload.bank_name or "").strip(),
        terminal_id=(payload.terminal_id or "").strip(),
        authorization_code=(payload.authorization_code or "").strip(),
        card_brand=(payload.card_brand or "").strip(),
        card_last4=(payload.card_last4 or "").strip(),
    )
    db.add(payment)

    for a in applied:
        row = a["row"]
        current_paid = Decimal(str(getattr(row, "paid_quantity", 0) or 0))
        row.paid_quantity = current_paid + a["requested_qty"]

    db.commit()

    paid_amount = get_order_paid_amount(db, order.id)
    balance_after = get_order_balance_due(db, order)

    if balance_after <= 0:
        order.payment_status = "paid"
        order.status = "paid"
        order.is_open = False
        order.closed_at = datetime.utcnow()
    else:
        order.payment_status = "partial"
        if order.status in ("", None, "open"):
            order.status = "open"

    db.commit()
    db.refresh(order)

    return {
        "ok": True,
        "order_id": order.id,
        "split_total": float(split_total),
        "paid_amount": float(paid_amount),
        "balance_due": float(balance_after),
        "ticket_status": order.status or "",
        "payment_status": order.payment_status or "",
        "applied_items": [
            {
                "order_item_id": a["row"].id,
                "product_name_snapshot": a["row"].product_name_snapshot or "",
                "quantity_paid_now": float(a["requested_qty"]),
                "line_total": float(a["line_total"]),
            }
            for a in applied
        ],
    }

@app.post("/v2/api/local/ticket/{order_id}/close")
def v2_api_local_ticket_close(
    order_id: int,
    payload: CloseLocalTicketInput,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    order = (
        db.query(Order)
        .filter(
            Order.id == order_id,
            Order.restaurant_id == rest.id,
        )
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Ticket no encontrado.")

    balance_due = get_order_balance_due(db, order)
    if balance_due > 0 and not bool(payload.force_close):
        raise HTTPException(
            status_code=400,
            detail=f"No puedes cerrar el ticket. Saldo pendiente: {float(balance_due):.2f}"
        )

    order.is_open = False
    if balance_due <= 0:
        order.payment_status = "paid"
        order.status = "closed"
    else:
        order.payment_status = order.payment_status or "pending"
        order.status = "closed"
    order.closed_at = datetime.utcnow()

    db.commit()
    db.refresh(order)

    return {
        "ok": True,
        "order_id": order.id,
        "status": order.status,
        "payment_status": order.payment_status,
        "closed_at": str(order.closed_at or ""),
    }

@app.post("/v2/api/orders/{order_id}/pay")
def v2_api_pay_order(
    order_id: int,
    payload: PayOrderInput,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):

    rest = get_restaurant_or_404(db, restaurant)

    order = (
        db.query(Order)
        .filter(
            Order.id == order_id,
            Order.restaurant_id == rest.id,
        )
        .first()
    )

    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada.")

    if (order.payment_status or "").lower() == "paid":
        raise HTTPException(status_code=400, detail="La orden ya fue pagada.")

    method = (payload.method or "").strip().lower()

    amount = Decimal(str(payload.amount or 0))
    order_total = Decimal(str(order.total or 0))

    payment = OrderPayment(
        order_id=order.id,
        method=method,
        status="approved",
        amount=amount,
        reference=(payload.reference or "").strip(),
        bank_name=(payload.bank_name or "").strip(),
        terminal_id=(payload.terminal_id or "").strip(),
        authorization_code=(payload.authorization_code or "").strip(),
        card_brand=(payload.card_brand or "").strip(),
        card_last4=(payload.card_last4 or "").strip(),
    )

    db.add(payment)

    order.payment_status = "paid"
    order.status = "paid"

    db.commit()
    db.refresh(payment)

    change = amount - order_total

    return {
        "ok": True,
        "order_id": order.id,
        "method": method,
        "paid_amount": float(amount),
        "order_total": float(order_total),
        "change": float(change),
        "payment_id": payment.id,
    }

@app.get("/v2/api/orders/{order_id}/payments")
def v2_api_order_payments(
    order_id: int,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    order = (
        db.query(Order)
        .filter(Order.id == order_id, Order.restaurant_id == rest.id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada.")

    rows = (
        db.query(OrderPayment)
        .filter(OrderPayment.order_id == order.id)
        .order_by(OrderPayment.id.asc())
        .all()
    )

    return {
        "ok": True,
        "order_id": order.id,
        "items": [
            {
                "id": p.id,
                "method": p.method,
                "status": p.status,
                "amount": float(p.amount or 0),
                "reference": p.reference or "",
                "bank_name": p.bank_name or "",
                "terminal_id": p.terminal_id or "",
                "authorization_code": p.authorization_code or "",
                "card_brand": p.card_brand or "",
                "card_last4": p.card_last4 or "",
                "created_at": str(p.created_at or ""),
            }
            for p in rows
        ],
    }

@app.get("/v2/api/delivery/pending")
def v2_api_delivery_pending(
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    rows = (
        db.query(Order)
        .filter(
            Order.restaurant_id == rest.id,
            Order.channel == "delivery",
            Order.payment_status != "paid",
        )
        .order_by(Order.id.desc())
        .limit(100)
        .all()
    )

    items = []
    for o in rows:
        meta = parse_pipe_notes_meta(o.notes or "")
        items.append(
            {
                "id": o.id,
                "status": o.status or "",
                "customer_name": o.customer_name or "",
                "customer_phone": o.customer_phone or "",
                "total": float(o.total or 0),
                "created_at": str(o.created_at or ""),
                "district_group": meta.get("zona", ""),
                "driver_name": meta.get("repartidor", ""),
                "payment_method": meta.get("pago", ""),
                "promo_code": meta.get("promocode", ""),
                "discount_percent": meta.get("discountpercent", ""),
            }
        )

    return {"ok": True, "items": items}


@app.get("/v2/api/orders/{order_id}/detail")
def v2_api_order_detail(
    order_id: int,
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    order = (
        db.query(Order)
        .filter(Order.id == order_id, Order.restaurant_id == rest.id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Orden no encontrada.")

    meta = parse_pipe_notes_meta(order.notes or "")

    order_items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
    product_ids = [getattr(it, "product_id", None) for it in order_items if getattr(it, "product_id", None)]
    product_rows = db.query(Product).filter(Product.id.in_(product_ids)).all() if product_ids else []
    product_map = {p.id: p for p in product_rows}

    items = []
    for it in order_items:
        pid = getattr(it, "product_id", None)
        product = product_map.get(pid)
        qty = getattr(it, "quantity", getattr(it, "qty", 1))
        unit_price = getattr(it, "unit_price", getattr(it, "price", 0))
        line_total = getattr(it, "line_total", None)
        if line_total is None:
            line_total = to_decimal(qty) * to_decimal(unit_price)

        items.append(
            {
                "product_id": pid,
                "name": getattr(product, "name", f"Producto #{pid}"),
                "category": getattr(product, "category", ""),
                "price": float(unit_price or 0),
                "quantity": float(qty or 0),
                "line_total": float(line_total or 0),
            }
        )

    return {
        "ok": True,
        "order": {
            "id": order.id,
            "channel": order.channel or "",
            "status": order.status or "",
            "customer_name": order.customer_name or "",
            "customer_phone": order.customer_phone or "",
            "table_number": order.table_number or "",
            "subtotal": float(order.subtotal or 0),
            "tax": float(order.tax or 0),
            "total": float(order.total or 0),
            "payment_status": order.payment_status or "",
            "notes": order.notes or "",
            "delivery_address": meta.get("dirección", meta.get("direccion", "")),
            "district_group": meta.get("zona", ""),
            "payment_method": meta.get("pago", "cash"),
            "driver_name": meta.get("repartidor", ""),
            "operator_name": meta.get("operador", ""),
            "promo_code": meta.get("promocode", ""),
            "discount_percent": meta.get("discountpercent", "0"),
        },
        "items": items,
    }

@app.get("/v2/api/summary")
def v2_api_summary(
    restaurant: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    rest = get_restaurant_or_404(db, restaurant)

    total_orders = db.query(Order).filter(Order.restaurant_id == rest.id).count()
    total_products = db.query(Product).filter(Product.restaurant_id == rest.id).count()
    total_inventory_items = db.query(InventoryItem).filter(InventoryItem.restaurant_id == rest.id).count()
    total_employees = db.query(Employee).filter(Employee.restaurant_id == rest.id).count()
    total_users = db.query(RestaurantUser).filter(RestaurantUser.restaurant_id == rest.id).count()

    open_cash_session = (
        db.query(CashSession)
        .filter(
            CashSession.restaurant_id == rest.id,
            CashSession.is_open == True,  # noqa: E712
        )
        .order_by(CashSession.id.desc())
        .first()
    )

    return {
        "ok": True,
        "restaurant": {
            "id": rest.id,
            "name": rest.name,
            "slug": rest.slug,
        },
        "summary": {
            "orders": total_orders,
            "products": total_products,
            "inventory_items": total_inventory_items,
            "employees": total_employees,
            "users": total_users,
            "cash_open": bool(open_cash_session),
        },
    }
