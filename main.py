import os
import time
import re
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

import requests
from sqlalchemy import func as sa_func, desc, asc
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from db import engine, SessionLocal
from models import Base, Order, OrderItem

# =========================
# ADMIN
# =========================
ADMIN_PHONE = os.getenv("ADMIN_PHONE", "").strip()
ADMIN_API_TOKEN = os.getenv("ADMIN_API_TOKEN", "").strip()
ADMIN_PIN = os.getenv("ADMIN_PIN", "").strip()

# ticket_asesor -> cliente_wa_id
ACTIVE_TICKETS: Dict[str, str] = {}
# cliente_wa_id -> ticket_asesor
CLIENT_TICKET: Dict[str, str] = {}

# =========================
# APP
# =========================
app = FastAPI(title="DEACA POS")

templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

Base.metadata.create_all(bind=engine)

# =========================
# ENV WhatsApp
# =========================
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "lux_verify_123")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "")
GRAPH_URL = "https://graph.facebook.com/v22.0"

# =========================
# CONFIG NEGOCIO
# =========================
DIRECCION = "De la entrada de las fuentes 5c y media al sur mano izquierda"
HORARIO = "9:00 a.m. a 10:00 p.m."
SESSION_TTL_SEC = 20 * 60
LOGO_URL = "/static/logo.png"

DELIVERY_GROUPS = [
    ("G1", "Distrito I / V / VII", 40),
    ("G2", "Distrito II / III / IV", 65),
    ("G3", "Distrito VI", 95),
]
OUTSIDE_MANAGUA_LABEL = "Fuera de Managua"

ORDER_STATUSES = {
    "pendiente",
    "preparando",
    "en_camino",
    "listo_retirar",
    "entregado",
    "cancelado",
}

ACTIVE_KITCHEN_STATUSES = {
    "pendiente",
    "preparando",
    "en_camino",
    "listo_retirar",
}

# =========================
# MENÚS
# =========================
DESAYUNOS: List[Tuple[str, int]] = [
    ("Madroño", 150),
    ("Guegüense", 150),
    ("El viejo y la vieja", 150),
    ("Orgullo nica", 120),
    ("Solar de monimbó", 100),
]

ALMUERZOS: List[Tuple[str, int]] = [
    ("Pollo frito", 200),
    ("Pollo jalapeño", 200),
    ("Pollo tapado", 200),
    ("Pollo al vino", 200),
    ("Costillas cerdo BBQ", 200),
    ("Carne desmenuzada", 200),
    ("Bistec", 200),
    ("Arroz a la valenciana", 200),
]

FRITANGAS: List[Tuple[str, int]] = [
    ("Carne asada", 250),
    ("Cerdo asado", 250),
    ("Pollo asado", 150),
    ("Dos enchiladas", 130),
    ("Dos tacos", 130),
    ("Tajadas con queso", 80),
    ("Maduro con queso", 80),
    ("Torta de papa", 80),
    ("Fritangazo", 1800),
]

BEBIDAS: List[Tuple[str, int]] = [
    ("Guayaba", 40),
    ("Jamaica", 40),
    ("Naranja", 40),
    ("Cebada", 40),
    ("Cálala", 40),
    ("Cacao", 80),
    ("Café negro", 10),
]

EXTRAS: List[Tuple[str, int]] = [
    ("Ensalada", 10),
    ("Queso", 10),
    ("Gallo pinto", 10),
    ("Arroz", 10),
    ("Frijoles", 10),
    ("Tortilla", 10),
    ("Chile", 10),
    ("Maduro", 10),
    ("Tajadas", 10),
    ("Chorizo", 10),
    ("Huevo entero", 10),
]

# =========================
# SESIONES (RAM)
# =========================
sessions: Dict[str, Dict[str, Any]] = {}


def now() -> int:
    return int(time.time())


def get_session(user_id: str) -> Dict[str, Any]:
    s = sessions.get(user_id)
    if not s or now() - s.get("ts", 0) > SESSION_TTL_SEC:
        s = {"ts": now(), "state": "HOME", "cart": [], "tmp": {}}
        sessions[user_id] = s
        return s
    s["ts"] = now()
    return s


def reset_session(user_id: str):
    sessions[user_id] = {"ts": now(), "state": "HOME", "cart": [], "tmp": {}}


# =========================
# WhatsApp helpers
# =========================
def wa_headers():
    return {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}


def wa_post(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        print("ERROR: Missing WHATSAPP_TOKEN or PHONE_NUMBER_ID")
        return {"error": "Missing WHATSAPP_TOKEN or PHONE_NUMBER_ID"}

    url = f"{GRAPH_URL}/{PHONE_NUMBER_ID}/messages"
    r = requests.post(url, headers=wa_headers(), json=payload, timeout=25)

    if r.status_code >= 300:
        try:
            print("WA_SEND_ERROR", r.status_code, r.text)
        except Exception:
            pass

    try:
        return r.json()
    except Exception:
        return {"status_code": r.status_code, "text": r.text}


def send_text(to: str, text: str):
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": text}}
    return wa_post(payload)


def send_buttons(to: str, body: str, buttons: list):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body},
            "action": {
                "buttons": [{"type": "reply", "reply": {"id": b["id"], "title": b["title"]}} for b in buttons]
            },
        },
    }
    return wa_post(payload)


def send_list(to: str, body: str, button_text: str, sections: list):
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": body},
            "action": {"button": button_text, "sections": sections},
        },
    }
    return wa_post(payload)


def notify_customer_order_status(order: Order):
    if not order.wa_id:
        return

    status = (order.status or "").strip()

    if status == "pendiente":
        msg = (
            f"🧾 Recibimos tu pedido *{order.ticket}*.\n"
            "Está pendiente de validación y en breve te confirmamos."
        )
    elif status == "preparando":
        msg = (
            f"👨‍🍳 Tu pedido *{order.ticket}* ya está siendo preparado.\n"
            "Te avisaremos cuando avance al siguiente paso."
        )
    elif status == "en_camino":
        msg = (
            f"🛵 Tu pedido *{order.ticket}* va en camino.\n"
            "Pronto llegará a tu dirección."
        )
    elif status == "listo_retirar":
        msg = f"📦 Tu pedido *{order.ticket}* ya está listo para retirar en el local."
    elif status == "entregado":
        msg = (
            f"✅ Tu pedido *{order.ticket}* fue entregado.\n"
            "Gracias por comprar con nosotros 🙌"
        )
    elif status == "cancelado":
        msg = (
            f"❌ Tu pedido *{order.ticket}* fue cancelado.\n"
            "Si necesitas ayuda, escríbenos por este mismo chat."
        )
    else:
        return

    send_text(order.wa_id, msg)


# =========================
# Admin helpers
# =========================
def require_admin_token(token: str):
    if ADMIN_API_TOKEN and token != ADMIN_API_TOKEN:
        raise HTTPException(status_code=401, detail="invalid token")


def require_admin_pin(pin: str):
    if not ADMIN_PIN:
        raise HTTPException(status_code=500, detail="ADMIN_PIN no configurado en Render")
    if (pin or "").strip() != ADMIN_PIN:
        raise HTTPException(status_code=401, detail="pin incorrecto")


def serialize_order(order: Order) -> Dict[str, Any]:
    items = []
    for it in getattr(order, "items", []) or []:
        items.append(
            {
                "id": it.id,
                "name": it.name,
                "config": it.config,
                "price": int(it.price),
                "qty": int(it.qty),
            }
        )

    return {
        "id": order.id,
        "ticket": order.ticket,
        "wa_id": order.wa_id,
        "customer_name": order.customer_name,
        "delivery_mode": order.delivery_mode,
        "address": order.address,
        "district_group": order.district_group,
        "payment_method": order.payment_method,
        "status": order.status,
        "hidden_from_kds": bool(order.hidden_from_kds),
        "subtotal": int(order.subtotal),
        "delivery_fee": int(order.delivery_fee),
        "total": int(order.total),
        "created_at": order.created_at.isoformat() if getattr(order, "created_at", None) else None,
        "items": items,
    }


# =========================
# Utilidades UI
# =========================
def short_title(name: str, max_len: int = 22) -> str:
    s = name.strip()
    return s if len(s) <= max_len else s[:max_len].rstrip() + "…"


def home_menu(to: str):
    body = (
        "👋 *Bienvenido a DEACA POS*\n\n"
        "Elegí una opción:\n"
        "1) Menú\n"
        "2) Pedir\n"
        "3) Carrito\n"
        "4) Ubicación y horario\n"
        "5) Asesor\n"
        "6) Borrar orden"
    )
    send_buttons(
        to,
        body,
        [
            {"id": "HOME_MENU", "title": "1) Menú"},
            {"id": "HOME_PEDIR", "title": "2) Pedir"},
            {"id": "HOME_CART", "title": "3) Carrito"},
        ],
    )
    send_buttons(
        to,
        "Más:",
        [
            {"id": "HOME_UBI", "title": "4) Ubicación"},
            {"id": "HOME_ASESOR", "title": "5) Asesor"},
            {"id": "HOME_CLEAR", "title": "6) Borrar"},
        ],
    )


def menu_categorias(to: str, title: str = "Elegí una categoría"):
    rows = [
        {"id": "CAT_DESAYUNOS", "title": "1) Desayunos", "description": "Ver opciones"},
        {"id": "CAT_ALMUERZOS", "title": "2) Almuerzos", "description": "Elegí plato + acompañamientos"},
        {"id": "CAT_FRITANGAS", "title": "3) Fritangas", "description": "Elegí plato + acompañamientos"},
        {"id": "CAT_BEBIDAS", "title": "4) Bebidas", "description": "Frescos, cacao y café"},
    ]
    if EXTRAS:
        rows.append({"id": "CAT_EXTRAS", "title": "5) Extras", "description": "Agregar adicionales"})

    sections = [{"title": "Categorías", "rows": rows}]
    send_list(to, f"📋 *{title}*", "Ver categorías", sections)


def productos_list(to: str, cat_key: str, items: List[Tuple[str, int]]):
    rows = []
    for i, (name, price) in enumerate(items, start=1):
        rows.append({"id": f"PROD_{cat_key}_{i}", "title": f"{i}) {short_title(name)}", "description": f"C${price}"})

    label = {
        "DES": "Desayunos",
        "ALM": "Almuerzos",
        "FRI": "Fritangas",
        "BEB": "Bebidas",
        "EXT": "Extras",
    }.get(cat_key, "Productos")
    sections = [{"title": label, "rows": rows}]
    send_list(to, f"🍽️ *{label}* (tocá para elegir)", "Ver", sections)


def show_ubi(to: str):
    send_text(to, f"📍 *Ubicación*\n{DIRECCION}\n\n🕘 *Horario*\n{HORARIO}")


# =========================
# Tickets (Asesor)
# =========================
def gen_asesor_ticket() -> str:
    return "A" + str(uuid.uuid4()).replace("-", "").upper()[:4]


def close_asesor_ticket_for_client(client_id: str):
    tk = CLIENT_TICKET.pop(client_id, None)
    if tk:
        ACTIVE_TICKETS.pop(tk, None)


def show_asesor(user_id: str, session: Dict[str, Any], last_message: str = ""):
    session["state"] = "ASESOR"

    if user_id in CLIENT_TICKET:
        ticket = CLIENT_TICKET[user_id]
    else:
        ticket = gen_asesor_ticket()
        CLIENT_TICKET[user_id] = ticket
        ACTIVE_TICKETS[ticket] = user_id

    send_text(
        user_id,
        "👨‍💼 Perfecto. Un asesor te atiende por este mismo número.\n"
        f"Tu ticket es: *{ticket}*\n"
        "Escribí tu consulta aquí 👇\n\n"
        "Para volver al menú en cualquier momento: escribí *Menú*",
    )

    if ADMIN_PHONE:
        admin_msg = (
            "🆘 NUEVO ASESOR\n\n"
            f"Ticket: {ticket}\n"
            f"Número: {user_id}\n"
            f"Mensaje:\n{last_message or '(sin mensaje)'}\n\n"
            "Responder así:\n"
            f"{ticket} Hola! 👋"
        )
        send_text(ADMIN_PHONE, admin_msg)
    else:
        print("WARN: ADMIN_PHONE vacío, no se notificó al admin.")


def forward_client_to_admin(client_id: str, client_name: str, text: str):
    ticket = CLIENT_TICKET.get(client_id)
    if not ticket or not ADMIN_PHONE:
        return

    msg = (
        "💬 MENSAJE CLIENTE\n\n"
        f"Ticket: {ticket}\n"
        f"Cliente: {client_name}\n"
        f"Número: {client_id}\n\n"
        f"Mensaje:\n{text}\n\n"
        f"Responder así:\n{ticket} <tu respuesta>"
    )
    send_text(ADMIN_PHONE, msg)


def handle_admin_reply(text: str):
    parts = text.strip().split(maxsplit=1)
    if not parts:
        return

    ticket = parts[0].upper()

    if not re.match(r"^A[0-9A-F]{4}$", ticket):
        if ADMIN_PHONE:
            send_text(
                ADMIN_PHONE,
                "ℹ️ Para responder a un cliente usá:\n"
                "A1B2 tu mensaje\n\n"
                "Para cerrar:\n"
                "A1B2 cerrar\n",
            )
        return

    body = parts[1] if len(parts) > 1 else ""

    if ticket not in ACTIVE_TICKETS:
        if ADMIN_PHONE:
            send_text(ADMIN_PHONE, "❌ Ticket no válido o ya cerrado.")
        return

    client_id = ACTIVE_TICKETS[ticket]

    if body.lower() in ("cerrar", "close", "cerrado"):
        ACTIVE_TICKETS.pop(ticket, None)
        CLIENT_TICKET.pop(client_id, None)
        if ADMIN_PHONE:
            send_text(ADMIN_PHONE, f"✅ Ticket {ticket} cerrado.")
        send_text(client_id, "✅ Listo. Cerré el chat con asesor. Si necesitás algo más, escribí *Menú*.")
        return

    if not body:
        if ADMIN_PHONE:
            send_text(ADMIN_PHONE, "📩 Escribí tu mensaje después del ticket. Ej: A1B2 Hola!")
        return

    send_text(client_id, f"💬 Asesor: {body}")
    if ADMIN_PHONE:
        send_text(ADMIN_PHONE, "✅ Enviado al cliente.")


# =========================
# UI flujo
# =========================
def qty_stepper(to: str, summary: str, qty: int):
    body = f"{summary}\n\nCantidad: *{qty}*"
    send_buttons(
        to,
        body,
        [
            {"id": "QTY_MINUS", "title": "➖"},
            {"id": "QTY_ADD", "title": "✅ Agregar"},
            {"id": "QTY_PLUS", "title": "➕"},
        ],
    )


def after_add_actions(to: str):
    send_buttons(
        to,
        "¿Cómo querés continuar?",
        [
            {"id": "AFTER_OTHER_PLATE", "title": "➕ Otro plato"},
            {"id": "AFTER_SAME_PLATE", "title": "🔁 Mismo plato"},
            {"id": "AFTER_CART", "title": "🧺 Carrito"},
        ],
    )


# =========================
# Carrito
# =========================
def cart_total(cart: List[Dict[str, Any]]) -> int:
    return sum(it["qty"] * it["price"] for it in cart)


def cart_lines(cart: List[Dict[str, Any]]) -> str:
    if not cart:
        return "🧺 Tu carrito está vacío."
    out = ["🧺 *Tu carrito:*"]
    for idx, it in enumerate(cart, start=1):
        conf = it.get("config", "")
        if conf:
            out.append(f"{idx}) {it['qty']} x {it['name']} ({conf}) — C${it['price']} c/u")
        else:
            out.append(f"{idx}) {it['qty']} x {it['name']} — C${it['price']} c/u")
    out.append(f"\n*Subtotal: C${cart_total(cart)}*")
    return "\n".join(out)


def cart_actions(to: str, session: Dict[str, Any]):
    send_text(to, cart_lines(session["cart"]))
    send_buttons(
        to,
        "Acciones:",
        [
            {"id": "CART_EDIT", "title": "1) Editar"},
            {"id": "CART_CLEAR", "title": "2) Vaciar"},
            {"id": "CART_PAY", "title": "3) Pagar"},
        ],
    )


def cart_pick_item(to: str, session: Dict[str, Any]):
    cart = session["cart"]
    if not cart:
        send_text(to, "Tu carrito está vacío.")
        home_menu(to)
        return

    rows = []
    for idx, it in enumerate(cart, start=1):
        conf = it.get("config", "")
        title = f"{idx}) {short_title(it['name'], 18)}"
        desc = f"Cantidad: {it['qty']}" + (f" | {conf}" if conf else "")
        rows.append({"id": f"EDIT_{idx}", "title": title, "description": desc})

    sections = [{"title": "Elegí un item para ajustar", "rows": rows}]
    send_list(to, "✏️ Editar carrito", "Ver", sections)


# =========================
# Reglas acompañamientos
# =========================
def lunch_side2_fixed() -> str:
    return "Arroz blanco"


def needs_fritanga_sides(item_name: str) -> bool:
    return item_name.lower() in {"carne asada", "cerdo asado", "pollo asado"}


def ask_side1(to: str, title: str):
    send_buttons(
        to,
        f"Elegí acompañamiento para *{title}*:",
        [
            {"id": "SIDE1_TAJADAS", "title": "1) Tajadas"},
            {"id": "SIDE1_MADURO", "title": "2) Maduro"},
            {"id": "CANCEL_FLOW", "title": "Cancelar"},
        ],
    )


def ask_side2_fritanga(to: str):
    send_buttons(
        to,
        "Elegí base:",
        [
            {"id": "SIDE2_GALLOPINTO", "title": "1) Gallo pinto"},
            {"id": "SIDE2_ARROZ", "title": "2) Arroz blanco"},
            {"id": "CANCEL_FLOW", "title": "Cancelar"},
        ],
    )


# =========================
# Parser
# =========================
def norm(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").strip().lower())


def get_item_by_cat_index(cat_key: str, idx: int) -> Optional[Tuple[str, int]]:
    items = {
        "DES": DESAYUNOS,
        "ALM": ALMUERZOS,
        "FRI": FRITANGAS,
        "BEB": BEBIDAS,
        "EXT": EXTRAS,
    }.get(cat_key)
    if not items:
        return None
    if 1 <= idx <= len(items):
        return items[idx - 1]
    return None


# =========================
# Ticket de pedido (DB)
# =========================
def make_order_ticket(order_id: int) -> str:
    date_str = datetime.utcnow().strftime("%Y%m%d")
    return f"P-{date_str}-{order_id:04d}"


# =========================
# ADMIN API
# =========================
@app.get("/admin")
def admin_home(request: Request, token: str = ""):
    require_admin_token(token)
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "admin_token": ADMIN_API_TOKEN,
            "logo_url": LOGO_URL,
        },
    )

@app.get("/admin/api/orders")
def admin_list_orders(limit: int = 100, token: str = ""):
    require_admin_token(token)
    limit = max(1, min(200, int(limit)))

    db = SessionLocal()
    try:
        orders = db.query(Order).order_by(Order.id.asc()).limit(limit).all()
        return {"ok": True, "orders": [serialize_order(o) for o in orders]}
    finally:
        db.close()


@app.post("/admin/api/orders/{order_id}/status")
async def admin_update_order_status(order_id: int, request: Request, token: str = ""):
    require_admin_token(token)

    payload = await request.json()
    new_status = str(payload.get("status", "")).strip()

    if new_status not in ORDER_STATUSES:
        raise HTTPException(status_code=400, detail="invalid status")

    db = SessionLocal()
    try:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="order not found")

        order.status = new_status
        db.commit()
        db.refresh(order)

        notify_customer_order_status(order)

        return {
            "ok": True,
            "order": {
                "id": order.id,
                "ticket": order.ticket,
                "status": order.status,
                "hidden_from_kds": bool(order.hidden_from_kds),
            },
        }
    finally:
        db.close()


@app.post("/admin/api/orders/{order_id}/hide")
async def admin_hide_order_from_kds(order_id: int, request: Request, token: str = ""):
    require_admin_token(token)

    payload = await request.json()
    require_admin_pin(str(payload.get("pin", "")))

    db = SessionLocal()
    try:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="order not found")

        if order.status != "entregado":
            raise HTTPException(status_code=400, detail="solo se pueden retirar pedidos entregados")

        order.hidden_from_kds = True
        db.commit()
        db.refresh(order)

        return {
            "ok": True,
            "order": {
                "id": order.id,
                "ticket": order.ticket,
                "hidden_from_kds": True,
            },
        }
    finally:
        db.close()


@app.post("/admin/api/orders/{order_id}/delete-cancelled")
async def admin_delete_cancelled_order(order_id: int, request: Request, token: str = ""):
    require_admin_token(token)

    payload = await request.json()
    require_admin_pin(str(payload.get("pin", "")))

    db = SessionLocal()
    try:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="order not found")

        if order.status != "cancelado":
            raise HTTPException(status_code=400, detail="solo se pueden eliminar pedidos cancelados")

        ticket = order.ticket
        db.delete(order)
        db.commit()

        return {"ok": True, "deleted_ticket": ticket}
    finally:
        db.close()


@app.get("/admin/api/history")
def admin_history(date: str = "", token: str = ""):
    require_admin_token(token)

    date_value = (date or datetime.utcnow().strftime("%Y-%m-%d")).strip()

    db = SessionLocal()
    try:
        orders = (
            db.query(Order)
            .filter(sa_func.date(Order.created_at) == date_value)
            .order_by(Order.id.asc())
            .all()
        )

        # cancelados eliminados ya no existirán; los entregados ocultos sí cuentan
        total_orders = len(orders)
        total_revenue = sum(int(o.total or 0) for o in orders)

        delivery_count = sum(1 for o in orders if (o.delivery_mode or "").lower() == "delivery")
        pickup_count = sum(1 for o in orders if (o.delivery_mode or "").lower() != "delivery")

        return {
            "ok": True,
            "date": date_value,
            "summary": {
                "total_orders": total_orders,
                "total_revenue": total_revenue,
                "delivery_count": delivery_count,
                "pickup_count": pickup_count,
            },
            "orders": [serialize_order(o) for o in orders],
        }
    finally:
        db.close()


@app.get("/admin/api/metrics")
def admin_metrics(token: str = ""):
    require_admin_token(token)

    db = SessionLocal()
    try:
        total_orders = db.query(sa_func.count(Order.id)).scalar() or 0
        total_revenue = int(
            db.query(sa_func.coalesce(sa_func.sum(Order.total), 0)).scalar() or 0
        )

        top_products_rows = (
            db.query(
                OrderItem.name,
                sa_func.coalesce(sa_func.sum(OrderItem.qty), 0).label("qty_sum"),
            )
            .join(Order, Order.id == OrderItem.order_id)
            .group_by(OrderItem.name)
            .order_by(desc("qty_sum"), asc(OrderItem.name))
            .limit(5)
            .all()
        )

        low_products_rows = (
            db.query(
                OrderItem.name,
                sa_func.coalesce(sa_func.sum(OrderItem.qty), 0).label("qty_sum"),
            )
            .join(Order, Order.id == OrderItem.order_id)
            .group_by(OrderItem.name)
            .order_by(asc("qty_sum"), asc(OrderItem.name))
            .limit(5)
            .all()
        )

        top_district_rows = (
            db.query(
                Order.district_group,
                sa_func.count(Order.id).label("order_count"),
            )
            .filter(Order.district_group.isnot(None))
            .filter(Order.district_group != "")
            .group_by(Order.district_group)
            .order_by(desc("order_count"), asc(Order.district_group))
            .limit(5)
            .all()
        )

        low_district_rows = (
            db.query(
                Order.district_group,
                sa_func.count(Order.id).label("order_count"),
            )
            .filter(Order.district_group.isnot(None))
            .filter(Order.district_group != "")
            .group_by(Order.district_group)
            .order_by(asc("order_count"), asc(Order.district_group))
            .limit(5)
            .all()
        )

        return {
            "ok": True,
            "summary": {
                "total_orders": int(total_orders),
                "total_revenue": total_revenue,
            },
            "top_products": [{"name": row[0], "qty": int(row[1] or 0)} for row in top_products_rows],
            "low_products": [{"name": row[0], "qty": int(row[1] or 0)} for row in low_products_rows],
            "top_districts": [{"district": row[0], "orders": int(row[1] or 0)} for row in top_district_rows],
            "low_districts": [{"district": row[0], "orders": int(row[1] or 0)} for row in low_district_rows],
        }
    finally:
        db.close()

@app.post("/admin/api/pin-check")
async def admin_pin_check(request: Request, token: str = ""):
    require_admin_token(token)
    payload = await request.json()
    require_admin_pin(str(payload.get("pin", "")))
    return {"ok": True}

# =========================
# WEBHOOK
# =========================
@app.get("/health")
def health():
    return {"ok": True}


@app.get("/orders")
def orders_page(request: Request):
    return templates.TemplateResponse(
        "orders.html",
        {
            "request": request,
            "admin_token": ADMIN_API_TOKEN,
            "logo_url": LOGO_URL,
        },
    )


@app.get("/webhook/whatsapp")
async def whatsapp_verify(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN and challenge:
        return PlainTextResponse(challenge, status_code=200)

    return PlainTextResponse("forbidden", status_code=403)


@app.post("/webhook/whatsapp")
async def webhook(request: Request):
    data = await request.json()

    try:
        entry = data.get("entry", [])[0]
        change = entry.get("changes", [])[0]
        value = change.get("value", {})
        messages = value.get("messages", [])

        if not messages:
            return JSONResponse({"ok": True})

        msg = messages[0]
        from_id = msg.get("from")
        if not from_id:
            return JSONResponse({"ok": True})

        session = get_session(from_id)

        mtype = msg.get("type")
        text = ""
        interactive_id = None

        if mtype == "text":
            text = msg.get("text", {}).get("body", "")
        elif mtype == "interactive":
            inter = msg.get("interactive", {})
            itype = inter.get("type")
            if itype == "button_reply":
                interactive_id = inter.get("button_reply", {}).get("id")
            elif itype == "list_reply":
                interactive_id = inter.get("list_reply", {}).get("id")

        await handle_message(from_id, session, text=text, interactive_id=interactive_id)
        return JSONResponse({"ok": True})

    except Exception as e:
        print("WEBHOOK_ERROR", str(e))
        return JSONResponse({"ok": False, "error": str(e)}, status_code=200)


# =========================
# FLOW HANDLERS
# =========================
async def handle_message(user_id: str, session: Dict[str, Any], text: str = "", interactive_id: Optional[str] = None):
    t = norm(text)

    if user_id == ADMIN_PHONE and text:
        handle_admin_reply(text)
        return

    if t in ("menu", "menú", "inicio", "salir", "cancelar", "fin"):
        session["state"] = "HOME"
        close_asesor_ticket_for_client(user_id)
        send_text(user_id, "✅ Listo. Volviste al menú.")
        home_menu(user_id)
        return

    if t == "carrito":
        cart_actions(user_id, session)
        return
    if t == "pagar":
        await pay_start(user_id, session)
        return
    if t == "borrar":
        reset_session(user_id)
        send_text(user_id, "🗑️ Orden borrada.")
        home_menu(user_id)
        return

    if interactive_id:
        await handle_interactive(user_id, session, interactive_id)
        return

    if session.get("state") == "ASESOR" and text:
        client_name = session.get("tmp", {}).get("name") or "Cliente"
        forward_client_to_admin(user_id, client_name, text)
        send_text(user_id, "✅ Recibido. Un asesor te responde por aquí.")
        return

    state = session.get("state", "HOME")
    if state == "HOME":
        home_menu(user_id)
        return

    if state == "PAY_NAME":
        if len(t) < 2:
            send_text(user_id, "Decime tu nombre, por favor 🙂")
            return
        session["tmp"]["name"] = text.strip()
        session["state"] = "PAY_DELIVERY_OR_PICKUP"
        send_buttons(
            user_id,
            "¿Cómo deseas recibir tu pedido?",
            [
                {"id": "PAY_DELIVERY", "title": "1) Delivery"},
                {"id": "PAY_PICKUP", "title": "2) Retiro"},
                {"id": "CANCEL_PAY", "title": "Cancelar"},
            ],
        )
        return

    if state == "PAY_ADDRESS":
        if len(t) < 5:
            send_text(user_id, "Pasame tu dirección completa, por favor.")
            return
        session["tmp"]["address"] = text.strip()
        session["state"] = "PAY_DISTRICT_GROUP"
        await ask_district_group(user_id)
        return

    home_menu(user_id)


async def handle_interactive(user_id: str, session: Dict[str, Any], iid: str):
    if iid == "HOME_ASESOR":
        show_asesor(user_id, session)
        return

    if iid in ("HOME_MENU", "HOME_PEDIR", "HOME_CART", "HOME_UBI", "HOME_CLEAR"):
        if iid == "HOME_MENU":
            menu_categorias(user_id, "Menú — elegí categoría")
            return
        if iid == "HOME_PEDIR":
            menu_categorias(user_id, "Pedir — elegí categoría")
            return
        if iid == "HOME_CART":
            cart_actions(user_id, session)
            return
        if iid == "HOME_UBI":
            show_ubi(user_id)
            return
        if iid == "HOME_CLEAR":
            reset_session(user_id)
            send_text(user_id, "🗑️ Orden borrada.")
            home_menu(user_id)
            return

    if iid.startswith("CAT_"):
        if iid == "CAT_DESAYUNOS":
            session["tmp"]["category"] = "DES"
            session["state"] = "PICK_PRODUCT"
            productos_list(user_id, "DES", DESAYUNOS)
        elif iid == "CAT_ALMUERZOS":
            session["tmp"]["category"] = "ALM"
            session["state"] = "PICK_PRODUCT"
            productos_list(user_id, "ALM", ALMUERZOS)
        elif iid == "CAT_FRITANGAS":
            session["tmp"]["category"] = "FRI"
            session["state"] = "PICK_PRODUCT"
            productos_list(user_id, "FRI", FRITANGAS)
        elif iid == "CAT_BEBIDAS":
            session["tmp"]["category"] = "BEB"
            session["state"] = "PICK_PRODUCT"
            productos_list(user_id, "BEB", BEBIDAS)
        elif iid == "CAT_EXTRAS":
            session["tmp"]["category"] = "EXT"
            session["state"] = "PICK_PRODUCT"
            productos_list(user_id, "EXT", EXTRAS)
        else:
            home_menu(user_id)
        return

    if iid.startswith("PROD_"):
        parts = iid.split("_")
        if len(parts) != 3:
            home_menu(user_id)
            return

        cat_key = parts[1]
        try:
            idx = int(parts[2])
        except ValueError:
            home_menu(user_id)
            return

        item = get_item_by_cat_index(cat_key, idx)
        if not item:
            send_text(user_id, "Ese producto no está disponible.")
            home_menu(user_id)
            return

        name, price = item
        session["tmp"]["picked"] = {"cat": cat_key, "name": name, "price": price}
        session["tmp"]["qty"] = 1
        session["tmp"]["side1"] = None
        session["tmp"]["side2"] = None

        if cat_key == "ALM":
            session["state"] = "ALM_SIDE1"
            ask_side1(user_id, name)
            return

        if cat_key == "FRI" and needs_fritanga_sides(name):
            session["state"] = "FRI_SIDE1"
            ask_side1(user_id, name)
            return

        session["state"] = "QTY"
        qty_stepper(user_id, f"✅ *{name}* — C${price}", 1)
        return

    if iid == "CANCEL_FLOW":
        session["state"] = "HOME"
        send_text(user_id, "Listo. Volvamos al menú 🙂")
        home_menu(user_id)
        return

    if iid in ("SIDE1_TAJADAS", "SIDE1_MADURO"):
        picked = session["tmp"].get("picked")
        if not picked:
            home_menu(user_id)
            return

        side1 = "Tajadas" if iid == "SIDE1_TAJADAS" else "Maduro"
        session["tmp"]["side1"] = side1

        if session.get("state") == "ALM_SIDE1":
            session["tmp"]["side2"] = lunch_side2_fixed()
            session["state"] = "QTY"
            conf = f"{side1} + {session['tmp']['side2']}"
            qty_stepper(user_id, f"✅ *{picked['name']}* ({conf}) — C${picked['price']}", session["tmp"]["qty"])
            return

        if session.get("state") == "FRI_SIDE1":
            session["state"] = "FRI_SIDE2"
            ask_side2_fritanga(user_id)
            return

        home_menu(user_id)
        return

    if iid in ("SIDE2_GALLOPINTO", "SIDE2_ARROZ"):
        picked = session["tmp"].get("picked")
        if not picked:
            home_menu(user_id)
            return

        side2 = "Gallo pinto" if iid == "SIDE2_GALLOPINTO" else "Arroz blanco"
        session["tmp"]["side2"] = side2
        session["state"] = "QTY"
        conf = f"{session['tmp']['side1']} + {side2}"
        qty_stepper(user_id, f"✅ *{picked['name']}* ({conf}) — C${picked['price']}", session["tmp"]["qty"])
        return

    if iid in ("QTY_MINUS", "QTY_PLUS", "QTY_ADD"):
        picked = session["tmp"].get("picked")
        if not picked:
            home_menu(user_id)
            return

        qty = int(session["tmp"].get("qty", 1))

        if iid == "QTY_MINUS":
            session["tmp"]["qty"] = max(1, qty - 1)
            await resend_qty(user_id, session)
            return

        if iid == "QTY_PLUS":
            session["tmp"]["qty"] = min(9, qty + 1)
            await resend_qty(user_id, session)
            return

        if iid == "QTY_ADD":
            side1 = session["tmp"].get("side1")
            side2 = session["tmp"].get("side2")

            config = ""
            if side1 and side2:
                config = f"{side1} + {side2}"
            elif side1:
                config = f"{side1}"

            session["cart"].append(
                {"name": picked["name"], "price": int(picked["price"]), "qty": int(qty), "config": config}
            )
            send_text(user_id, f"✅ Agregado: {qty} x {picked['name']}" + (f" ({config})" if config else ""))
            session["state"] = "HOME"
            after_add_actions(user_id)
            return

    if iid in ("AFTER_OTHER_PLATE", "AFTER_SAME_PLATE", "AFTER_CART"):
        if iid == "AFTER_OTHER_PLATE":
            menu_categorias(user_id, "Elegí categoría para seguir agregando")
            return
        if iid == "AFTER_CART":
            cart_actions(user_id, session)
            return

        if iid == "AFTER_SAME_PLATE":
            if not session["cart"]:
                menu_categorias(user_id, "Elegí categoría")
                return

            last = session["cart"][-1]
            base_name = last["name"]
            alm_names = {n for n, _ in ALMUERZOS}
            fri_names = {n for n, _ in FRITANGAS}

            if base_name in alm_names:
                price = next(p for n, p in ALMUERZOS if n == base_name)
                session["tmp"]["picked"] = {"cat": "ALM", "name": base_name, "price": price}
                session["tmp"]["qty"] = 1
                session["tmp"]["side1"] = None
                session["tmp"]["side2"] = None
                session["state"] = "ALM_SIDE1"
                ask_side1(user_id, base_name)
                return

            if base_name in fri_names and needs_fritanga_sides(base_name):
                price = next(p for n, p in FRITANGAS if n == base_name)
                session["tmp"]["picked"] = {"cat": "FRI", "name": base_name, "price": price}
                session["tmp"]["qty"] = 1
                session["tmp"]["side1"] = None
                session["tmp"]["side2"] = None
                session["state"] = "FRI_SIDE1"
                ask_side1(user_id, base_name)
                return

            menu_categorias(user_id, "Elegí categoría")
            return

    if iid in ("CART_EDIT", "CART_CLEAR", "CART_PAY"):
        if iid == "CART_EDIT":
            cart_pick_item(user_id, session)
            return
        if iid == "CART_CLEAR":
            session["cart"] = []
            send_text(user_id, "🗑️ Carrito vaciado.")
            home_menu(user_id)
            return
        if iid == "CART_PAY":
            await pay_start(user_id, session)
            return

    if iid.startswith("EDIT_"):
        try:
            idx = int(iid.split("_")[1])
        except Exception:
            cart_actions(user_id, session)
            return

        cart = session["cart"]
        if not (1 <= idx <= len(cart)):
            cart_actions(user_id, session)
            return

        session["tmp"]["edit_idx"] = idx - 1
        session["tmp"]["edit_qty"] = cart[idx - 1]["qty"]
        it = cart[idx - 1]
        label = f"{it['name']}" + (f" ({it['config']})" if it.get("config") else "")
        send_buttons(
            user_id,
            f"✏️ {label}\nCantidad: *{session['tmp']['edit_qty']}*",
            [
                {"id": "EDIT_MINUS", "title": "➖"},
                {"id": "EDIT_DONE", "title": "✅ Listo"},
                {"id": "EDIT_PLUS", "title": "➕"},
            ],
        )
        session["state"] = "EDIT_QTY"
        return

    if iid in ("EDIT_MINUS", "EDIT_PLUS", "EDIT_DONE"):
        if "edit_idx" not in session["tmp"]:
            cart_actions(user_id, session)
            return

        eidx = int(session["tmp"]["edit_idx"])
        cart = session["cart"]
        if not (0 <= eidx < len(cart)):
            cart_actions(user_id, session)
            return

        qty = int(session["tmp"].get("edit_qty", cart[eidx]["qty"]))

        if iid == "EDIT_MINUS":
            session["tmp"]["edit_qty"] = max(0, qty - 1)
        elif iid == "EDIT_PLUS":
            session["tmp"]["edit_qty"] = min(9, qty + 1)
        elif iid == "EDIT_DONE":
            qty = int(session["tmp"].get("edit_qty", 1))
            if qty <= 0:
                cart.pop(eidx)
                send_text(user_id, "🗑️ Item eliminado.")
            else:
                cart[eidx]["qty"] = qty
                send_text(user_id, "✅ Cantidad actualizada.")
            session["state"] = "HOME"
            cart_actions(user_id, session)
            return

        it = cart[eidx]
        label = f"{it['name']}" + (f" ({it['config']})" if it.get("config") else "")
        send_buttons(
            user_id,
            f"✏️ {label}\nCantidad: *{session['tmp']['edit_qty']}*",
            [
                {"id": "EDIT_MINUS", "title": "➖"},
                {"id": "EDIT_DONE", "title": "✅ Listo"},
                {"id": "EDIT_PLUS", "title": "➕"},
            ],
        )
        return

    if iid in ("PAY_DELIVERY", "PAY_PICKUP", "CANCEL_PAY"):
        if iid == "CANCEL_PAY":
            session["state"] = "HOME"
            send_text(user_id, "Pago cancelado.")
            home_menu(user_id)
            return

        if iid == "PAY_PICKUP":
            session["tmp"]["delivery_mode"] = "Retiro"
            session["tmp"]["delivery_fee"] = 0
            session["tmp"]["address"] = "Retiro en local"
            await ask_payment_method(user_id, session)
            return

        if iid == "PAY_DELIVERY":
            session["tmp"]["delivery_mode"] = "Delivery"
            send_buttons(
                user_id,
                "🚚 El envío tiene un costo adicional.\n\n¿Procedemos con tus datos?",
                [
                    {"id": "DELIVERY_PROCEED", "title": "1) Sí, proceder"},
                    {"id": "CANCEL_PAY", "title": "Cancelar"},
                    {"id": "HOME_ASESOR", "title": "Asesor"},
                ],
            )
            session["state"] = "PAY_DELIVERY_NOTICE"
            return

    if iid == "DELIVERY_PROCEED":
        session["state"] = "PAY_ADDRESS"
        send_text(user_id, "📍 Escribí tu *dirección completa* (y referencia si querés):")
        return

    if iid.startswith("DG_"):
        dg = iid.replace("DG_", "")
        if dg == "OUT":
            show_asesor(user_id, session, last_message="Cotizar envío fuera de Managua")
            return

        match = next((g for g in DELIVERY_GROUPS if g[0] == dg), None)
        if not match:
            home_menu(user_id)
            return

        _, label, fee = match
        session["tmp"]["district_group"] = label
        session["tmp"]["delivery_fee"] = fee
        await ask_payment_method(user_id, session)
        return

    if iid in ("PAY_CASH", "PAY_TRANSFER"):
        method = {"PAY_CASH": "Efectivo", "PAY_TRANSFER": "Transferencia"}[iid]
        session["tmp"]["payment_method"] = method
        await send_invoice_and_confirm(user_id, session)
        return

    if iid in ("CONFIRM_ORDER", "CANCEL_ORDER"):
        if iid == "CANCEL_ORDER":
            session["state"] = "HOME"
            send_text(user_id, "Pedido cancelado. Podés volver a armarlo cuando quieras 🙂")
            home_menu(user_id)
            return

        db = SessionLocal()
        try:
            name = session["tmp"].get("name", "Cliente")
            mode = session["tmp"].get("delivery_mode", "Retiro")
            address = session["tmp"].get("address", "")
            dg = session["tmp"].get("district_group", "")
            fee = int(session["tmp"].get("delivery_fee", 0))
            pay_method = session["tmp"].get("payment_method", "")

            subtotal = cart_total(session["cart"])
            total = subtotal + fee

            order = Order(
                ticket="",
                wa_id=user_id,
                customer_name=name,
                delivery_mode=mode,
                address=address,
                district_group=dg,
                payment_method=pay_method,
                status="pendiente",
                hidden_from_kds=False,
                subtotal=subtotal,
                delivery_fee=fee,
                total=total,
            )

            for it in session["cart"]:
                order.items.append(
                    OrderItem(
                        name=it["name"],
                        config=it.get("config") or "",
                        price=int(it["price"]),
                        qty=int(it["qty"]),
                    )
                )

            db.add(order)
            db.flush()

            order.ticket = make_order_ticket(order.id)
            db.commit()
            db.refresh(order)

            send_text(
                user_id,
                f"✅ Pedido recibido y guardado. Ticket: *{order.ticket}*.\n"
                "Tu pedido está pendiente de validación. En breve te confirmamos por aquí 🙌"
            )

            if ADMIN_PHONE:
                items_txt = []
                for it in session["cart"]:
                    conf = it.get("config") or ""
                    line = f"- {it['qty']} x {it['name']} ({conf})" if conf else f"- {it['qty']} x {it['name']}"
                    items_txt.append(line)

                admin_order_msg = (
                    "🧾 NUEVO PEDIDO\n\n"
                    f"Ticket: {order.ticket}\n"
                    f"Estado: {order.status}\n"
                    f"Cliente: {name}\n"
                    f"Número: {user_id}\n"
                    f"Entrega: {mode}\n"
                    f"Distrito: {dg or '-'}\n"
                    f"Dirección: {address or '-'}\n"
                    f"Pago: {pay_method}\n\n"
                    "Items:\n" + "\n".join(items_txt) + "\n\n"
                    f"Subtotal: C${subtotal}\n"
                    f"Envío: C${fee}\n"
                    f"Total: C${total}"
                )
                send_text(ADMIN_PHONE, admin_order_msg)
            else:
                print("WARN: ADMIN_PHONE vacío, pedido guardado sin notificar.")

        except Exception as e:
            db.rollback()
            print("DB_SAVE_ERROR", str(e))
            send_text(user_id, "⚠️ Tu pedido se recibió, pero hubo un problema guardándolo. Un asesor te ayuda.")
            show_asesor(user_id, session, last_message="Error guardando pedido en DB")
        finally:
            db.close()

        reset_session(user_id)
        home_menu(user_id)
        return

    home_menu(user_id)


async def resend_qty(user_id: str, session: Dict[str, Any]):
    picked = session["tmp"].get("picked")
    if not picked:
        home_menu(user_id)
        return

    side1 = session["tmp"].get("side1")
    side2 = session["tmp"].get("side2")
    qty = int(session["tmp"].get("qty", 1))

    if side1 and side2:
        conf = f"{side1} + {side2}"
        summary = f"✅ *{picked['name']}* ({conf}) — C${picked['price']}"
    elif side1:
        summary = f"✅ *{picked['name']}* ({side1}) — C${picked['price']}"
    else:
        summary = f"✅ *{picked['name']}* — C${picked['price']}"

    qty_stepper(user_id, summary, qty)


async def pay_start(user_id: str, session: Dict[str, Any]):
    if not session["cart"]:
        send_text(user_id, "🧺 Tu carrito está vacío. Primero agregá algo 🙂")
        home_menu(user_id)
        return
    session["state"] = "PAY_NAME"
    send_text(user_id, "🧾 Para registrar tu pedido: ¿Cuál es tu *nombre*?")


async def ask_district_group(to: str):
    rows = []
    for gkey, label, _fee in DELIVERY_GROUPS:
        rows.append({"id": f"DG_{gkey}", "title": short_title(label, 24), "description": "Seleccionar"})
    rows.append({"id": "DG_OUT", "title": short_title(OUTSIDE_MANAGUA_LABEL, 24), "description": "Cotiza con asesor"})
    sections = [{"title": "Distritos", "rows": rows}]
    send_list(to, "📍 ¿A qué distrito pertenece tu dirección?", "Elegir", sections)


async def ask_payment_method(to: str, session: Dict[str, Any]):
    session["state"] = "PAY_METHOD"
    send_buttons(
        to,
        "Método de pago:",
        [
            {"id": "PAY_CASH", "title": "1) Efectivo"},
            {"id": "PAY_TRANSFER", "title": "2) Transferencia"},
        ],
    )


async def send_invoice_and_confirm(to: str, session: Dict[str, Any]):
    name = session["tmp"].get("name", "Cliente")
    mode = session["tmp"].get("delivery_mode", "Retiro")
    address = session["tmp"].get("address", "")
    dg = session["tmp"].get("district_group", "")
    fee = int(session["tmp"].get("delivery_fee", 0))
    pay_method = session["tmp"].get("payment_method", "")

    subtotal = cart_total(session["cart"])
    total = subtotal + fee

    lines = [
        "🧾 *Resumen de tu pedido*",
        f"Nombre: {name}",
        "",
        cart_lines(session["cart"]),
        "",
        f"Entrega: {mode}",
    ]

    if mode == "Delivery":
        if dg:
            lines.append(f"Distrito: {dg}")
        if address:
            lines.append(f"Dirección: {address}")
        lines.append(f"Envío: *C${fee}*")

    lines.append(f"\nMétodo de pago: {pay_method}")
    lines.append(f"\n💰 *Total a pagar: C${total}*")

    send_buttons(
        to,
        "\n".join(lines) + "\n\n¿Confirmás el pedido?",
        [
            {"id": "CONFIRM_ORDER", "title": "1) Confirmar"},
            {"id": "CANCEL_ORDER", "title": "2) Cancelar"},
            {"id": "HOME_ASESOR", "title": "Asesor"},
        ],
    )
    session["state"] = "CONFIRM"
