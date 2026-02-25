import os
import time
import re
import json
import requests
from typing import Dict, Any, Optional, List, Tuple

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, JSONResponse

app = FastAPI(title="WhatsApp Orders API")

# =========================
# ENV
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

SESSION_TTL_SEC = 20 * 60  # 20 minutos

# Delivery por grupos (NO se muestra al cliente hasta la factura)
DELIVERY_GROUPS = [
    ("G1", "Distrito I / V / VII", 40),
    ("G2", "Distrito II / III / IV", 65),
    ("G3", "Distrito VI", 95),
]
OUTSIDE_MANAGUA_LABEL = "Fuera de Managua (Asesor)"

# =========================
# MENÚS
# =========================
# Desayunos
DESAYUNOS: List[Tuple[str, int]] = [
    ("Madroño", 150),
    ("Guegüense", 150),
    ("El viejo y la vieja", 150),
    ("Orgullo nica", 120),
    ("Solar de monimbó", 100),
]

# Almuerzos (todos C$200)
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

# Fritangas (antes “Cenas”)
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

# Bebidas
BEBIDAS: List[Tuple[str, int]] = [
    ("Guayaba", 40),
    ("Jamaica", 40),
    ("Naranja", 40),
    ("Cebada", 40),
    ("Cálala", 40),
    ("Cacao", 80),
]

# Extras (por ahora vacío; si después me pasás la lista, lo llenamos)
EXTRAS: List[Tuple[str, int]] = []


# =========================
# SESIONES (memoria RAM)
# =========================
# sessions[wa_id] = {
#   "ts": last_update,
#   "state": "...",
#   "cart": [ {item}, {item} ... ],  # cada item es una CONFIGURACIÓN (plato + sides)
#   "tmp": {...}
# }
sessions: Dict[str, Dict[str, Any]] = {}


def now() -> int:
    return int(time.time())


def get_session(user_id: str) -> Dict[str, Any]:
    s = sessions.get(user_id)
    if not s:
        s = {"ts": now(), "state": "HOME", "cart": [], "tmp": {}}
        sessions[user_id] = s
        return s

    if now() - s.get("ts", 0) > SESSION_TTL_SEC:
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
    return {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }


def wa_post(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        print("ERROR: Missing WHATSAPP_TOKEN or PHONE_NUMBER_ID")
        return {"error": "Missing WHATSAPP_TOKEN or PHONE_NUMBER_ID"}

    url = f"{GRAPH_URL}/{PHONE_NUMBER_ID}/messages"
    r = requests.post(url, headers=wa_headers(), json=payload, timeout=25)

    # Log útil en Render si Meta rechaza (aquí fue donde te “no salía” menú)
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
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
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
                "buttons": [
                    {"type": "reply", "reply": {"id": b["id"], "title": b["title"]}}
                    for b in buttons
                ]
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


# =========================
# Utilidades UI
# =========================
def short_title(name: str, max_len: int = 22) -> str:
    s = name.strip()
    if len(s) <= max_len:
        return s
    return s[:max_len].rstrip() + "…"


def home_menu(to: str):
    body = (
        "👋 *Bienvenido*\n\n"
        "Elegí una opción:\n"
        "1) Menú\n"
        "2) Pedir\n"
        "3) Carrito\n"
        "4) Ubicación y horario\n"
        "5) Asesor\n"
        "6) Borrar orden"
    )
    send_buttons(to, body, [
        {"id": "HOME_MENU", "title": "1) Menú"},
        {"id": "HOME_PEDIR", "title": "2) Pedir"},
        {"id": "HOME_CART", "title": "3) Carrito"},
    ])
    send_buttons(to, "Más:", [
        {"id": "HOME_UBI", "title": "4) Ubicación"},
        {"id": "HOME_ASESOR", "title": "5) Asesor"},
        {"id": "HOME_CLEAR", "title": "6) Borrar"},
    ])


def menu_categorias(to: str, title: str = "Elegí una categoría"):
    rows = [
        {"id": "CAT_DESAYUNOS", "title": "1) Desayunos", "description": "Ver opciones"},
        {"id": "CAT_ALMUERZOS", "title": "2) Almuerzos", "description": "Elegí plato + acompañamientos"},
        {"id": "CAT_FRITANGAS", "title": "3) Fritangas", "description": "Elegí plato + acompañamientos"},
        {"id": "CAT_BEBIDAS", "title": "4) Bebidas", "description": "Frescos y cacao"},
    ]
    if EXTRAS:
        rows.append({"id": "CAT_EXTRAS", "title": "5) Extras", "description": "Agregar adicionales"})

    sections = [{"title": "Categorías", "rows": rows}]
    send_list(to, f"📋 *{title}*", "Ver categorías", sections)


def productos_list(to: str, cat_key: str, items: List[Tuple[str, int]]):
    # IMPORTANTE: title corto, precio en description (evita que Meta rechace)
    rows = []
    for i, (name, price) in enumerate(items, start=1):
        rows.append({
            "id": f"PROD_{cat_key}_{i}",
            "title": f"{i}) {short_title(name)}",
            "description": f"C${price}",
        })

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


def show_asesor(to: str):
    send_text(to, "🧑‍💼 Perfecto. Un asesor te atiende por este mismo número.\nEscribí tu consulta aquí 👇")


def qty_stepper(to: str, summary: str, qty: int):
    body = f"{summary}\n\nCantidad: *{qty}*"
    send_buttons(to, body, [
        {"id": "QTY_MINUS", "title": "➖"},
        {"id": "QTY_ADD", "title": "✅ Agregar"},
        {"id": "QTY_PLUS", "title": "➕"},
    ])


def after_add_actions(to: str):
    # Upgrade pro: mismo plato diferente acompañamiento
    send_buttons(to, "¿Cómo querés continuar?", [
        {"id": "AFTER_OTHER_PLATE", "title": "➕ Otro plato"},
        {"id": "AFTER_SAME_PLATE", "title": "🔁 Mismo plato"},
        {"id": "AFTER_CART", "title": "🧺 Carrito"},
    ])


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
    send_buttons(to, "Acciones:", [
        {"id": "CART_EDIT", "title": "1) Editar"},
        {"id": "CART_CLEAR", "title": "2) Vaciar"},
        {"id": "CART_PAY", "title": "3) Pagar"},
    ])


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
        desc = f"Cantidad: {it['qty']}"
        if conf:
            desc += f" | {conf}"
        rows.append({"id": f"EDIT_{idx}", "title": title, "description": desc})

    sections = [{"title": "Elegí un item para ajustar", "rows": rows}]
    send_list(to, "✏️ Editar carrito", "Ver", sections)


# =========================
# Reglas acompañamientos
# =========================
def needs_lunch_side1(item_name: str) -> bool:
    # Almuerzos: todos piden Tajadas/Maduro
    return True


def lunch_side2_fixed() -> str:
    # Almuerzos: arroz blanco fijo según tu especificación
    return "Arroz blanco"


def needs_fritanga_sides(item_name: str) -> bool:
    # Solo estos 3 llevan (Tajadas/Maduro) + (Gallo pinto)
    return item_name.lower() in {"carne asada", "cerdo asado", "pollo asado"}


def ask_side1(to: str, title: str):
    send_buttons(to, f"Elegí acompañamiento para *{title}*:", [
        {"id": "SIDE1_TAJADAS", "title": "1) Tajadas"},
        {"id": "SIDE1_MADURO", "title": "2) Maduro"},
        {"id": "CANCEL_FLOW", "title": "Cancelar"},
    ])


def ask_side2_fritanga(to: str):
    send_buttons(to, "Elegí base:", [
        {"id": "SIDE2_GALLOPINTO", "title": "1) Gallo pinto"},
        {"id": "SIDE2_ARROZ", "title": "2) Arroz blanco"},
        {"id": "CANCEL_FLOW", "title": "Cancelar"},
    ])


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
# WEBHOOK
# =========================
@app.get("/health")
def health():
    return {"ok": True}


@app.get("/webhook/whatsapp")
def verify(mode: str = "", challenge: str = "", verify_token: str = ""):
    if mode == "subscribe" and verify_token == VERIFY_TOKEN:
        return PlainTextResponse(challenge)
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

    # Atajos por texto
    if t in ("menu", "menú", "inicio"):
        session["state"] = "HOME"
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

    # Si el usuario escribe libre en estados de pago
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
        send_buttons(user_id, "¿Cómo deseas recibir tu pedido?", [
            {"id": "PAY_DELIVERY", "title": "1) Delivery"},
            {"id": "PAY_PICKUP", "title": "2) Retiro"},
            {"id": "CANCEL_PAY", "title": "Cancelar"},
        ])
        return

    if state == "PAY_ADDRESS":
        if len(t) < 5:
            send_text(user_id, "Pasame tu dirección completa, por favor.")
            return
        session["tmp"]["address"] = text.strip()
        session["state"] = "PAY_DISTRICT_GROUP"
        await ask_district_group(user_id)
        return

    # fallback
    home_menu(user_id)


async def handle_interactive(user_id: str, session: Dict[str, Any], iid: str):
    # HOME
    if iid in ("HOME_MENU", "HOME_PEDIR", "HOME_CART", "HOME_UBI", "HOME_ASESOR", "HOME_CLEAR"):
        if iid == "HOME_MENU":
            menu_categorias(user_id, "Menú — elegí categoría")
        elif iid == "HOME_PEDIR":
            menu_categorias(user_id, "Pedir — elegí categoría")
        elif iid == "HOME_CART":
            cart_actions(user_id, session)
        elif iid == "HOME_UBI":
            show_ubi(user_id)
        elif iid == "HOME_ASESOR":
            show_asesor(user_id)
        elif iid == "HOME_CLEAR":
            reset_session(user_id)
            send_text(user_id, "🗑️ Orden borrada.")
            home_menu(user_id)
        return

    # CATEGORÍAS
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
        return

    # Elegir producto
    if iid.startswith("PROD_"):
        # PROD_{CAT}_{i}
        parts = iid.split("_")
        if len(parts) != 3:
            home_menu(user_id)
            return

        cat_key = parts[1]
        idx = int(parts[2])
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

        # Upgrade: si venimos de "mismo plato", mantenemos base y saltamos a acompañamientos
        # (simplemente lo manejamos por estado normal)

        # Ruteo por categoría y si necesita acompañamientos
        if cat_key == "ALM":
            # Almuerzos: siempre Tajadas/Maduro, y arroz blanco fijo
            session["state"] = "ALM_SIDE1"
            ask_side1(user_id, name)
            return

        if cat_key == "FRI" and needs_fritanga_sides(name):
            session["state"] = "FRI_SIDE1"
            ask_side1(user_id, name)
            return

        # Desayunos / Bebidas / Extras / Fritangas sin sides -> directo regleta
        session["state"] = "QTY"
        summary = f"✅ *{name}* — C${price}"
        qty_stepper(user_id, summary, 1)
        return

    # Cancelar flujo
    if iid == "CANCEL_FLOW":
        session["state"] = "HOME"
        send_text(user_id, "Listo. Volvamos al menú 🙂")
        home_menu(user_id)
        return

    # Acompañamiento 1 (tajadas/maduro)
    if iid in ("SIDE1_TAJADAS", "SIDE1_MADURO"):
        picked = session["tmp"].get("picked")
        if not picked:
            home_menu(user_id)
            return

        side1 = "Tajadas" if iid == "SIDE1_TAJADAS" else "Maduro"
        session["tmp"]["side1"] = side1

        if session["state"] == "ALM_SIDE1":
            # Almuerzos: side2 fijo arroz blanco
            session["tmp"]["side2"] = lunch_side2_fixed()
            session["state"] = "QTY"
            name = picked["name"]
            price = picked["price"]
            conf = f"{side1} + {session['tmp']['side2']}"
            summary = f"✅ *{name}* ({conf}) — C${price}"
            qty_stepper(user_id, summary, session["tmp"]["qty"])
            return

        if session["state"] == "FRI_SIDE1":
            # Fritangas: ahora preguntar gallo pinto / arroz
            session["state"] = "FRI_SIDE2"
            ask_side2_fritanga(user_id)
            return

        home_menu(user_id)
        return

    # Acompañamiento 2 (fritangas)
    if iid in ("SIDE2_GALLOPINTO", "SIDE2_ARROZ"):
        picked = session["tmp"].get("picked")
        if not picked:
            home_menu(user_id)
            return

        side2 = "Gallo pinto" if iid == "SIDE2_GALLOPINTO" else "Arroz blanco"
        session["tmp"]["side2"] = side2

        # a regleta
        session["state"] = "QTY"
        name = picked["name"]
        price = picked["price"]
        conf = f"{session['tmp']['side1']} + {side2}"
        summary = f"✅ *{name}* ({conf}) — C${price}"
        qty_stepper(user_id, summary, session["tmp"]["qty"])
        return

    # Regleta cantidad
    if iid in ("QTY_MINUS", "QTY_PLUS", "QTY_ADD"):
        picked = session["tmp"].get("picked")
        if not picked:
            home_menu(user_id)
            return

        qty = int(session["tmp"].get("qty", 1))

        if iid == "QTY_MINUS":
            qty = max(1, qty - 1)
            session["tmp"]["qty"] = qty
            await resend_qty(user_id, session)
            return

        if iid == "QTY_PLUS":
            qty = min(9, qty + 1)
            session["tmp"]["qty"] = qty
            await resend_qty(user_id, session)
            return

        if iid == "QTY_ADD":
            # Guardar como CONFIGURACIÓN independiente (esto permite 2 pollos con configuraciones distintas)
            name = picked["name"]
            price = picked["price"]
            side1 = session["tmp"].get("side1")
            side2 = session["tmp"].get("side2")

            config = ""
            if side1 and side2:
                config = f"{side1} + {side2}"
            elif side1 and not side2:
                config = f"{side1}"

            session["cart"].append({
                "name": name,
                "price": int(price),
                "qty": int(qty),
                "config": config,
            })

            send_text(user_id, f"✅ Agregado: {qty} x {name}" + (f" ({config})" if config else ""))
            session["state"] = "HOME"
            after_add_actions(user_id)
            return

    # Post-add upgrade
    if iid in ("AFTER_OTHER_PLATE", "AFTER_SAME_PLATE", "AFTER_CART"):
        if iid == "AFTER_OTHER_PLATE":
            menu_categorias(user_id, "Elegí categoría para seguir agregando")
            return

        if iid == "AFTER_SAME_PLATE":
            # Mismo plato, diferente acompañamiento:
            # Si el último agregado fue almuerzo o fritanga con sides, repetimos base y vamos directo a sides
            if not session["cart"]:
                menu_categorias(user_id, "Elegí categoría")
                return

            last = session["cart"][-1]
            base_name = last["name"]

            # Determinar si ese plato existe en almuerzos o fritangas con sides
            alm_names = {n for n, _ in ALMUERZOS}
            fri_names = {n for n, _ in FRITANGAS}

            if base_name in alm_names:
                # set picked como almuerzo
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

            # si no aplica, lo mandamos a categorías
            menu_categorias(user_id, "Elegí categoría")
            return

        if iid == "AFTER_CART":
            cart_actions(user_id, session)
            return

    # Carrito
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

    # Editar item específico
    if iid.startswith("EDIT_"):
        idx = int(iid.split("_")[1])
        cart = session["cart"]
        if not (1 <= idx <= len(cart)):
            cart_actions(user_id, session)
            return

        session["tmp"]["edit_idx"] = idx - 1
        session["tmp"]["edit_qty"] = cart[idx - 1]["qty"]
        it = cart[idx - 1]
        label = f"{it['name']}" + (f" ({it['config']})" if it.get("config") else "")
        send_buttons(user_id, f"✏️ {label}\nCantidad: *{session['tmp']['edit_qty']}*", [
            {"id": "EDIT_MINUS", "title": "➖"},
            {"id": "EDIT_DONE", "title": "✅ Listo"},
            {"id": "EDIT_PLUS", "title": "➕"},
        ])
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
            qty = max(0, qty - 1)
            session["tmp"]["edit_qty"] = qty
        elif iid == "EDIT_PLUS":
            qty = min(9, qty + 1)
            session["tmp"]["edit_qty"] = qty
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
        send_buttons(user_id, f"✏️ {label}\nCantidad: *{qty}*", [
            {"id": "EDIT_MINUS", "title": "➖"},
            {"id": "EDIT_DONE", "title": "✅ Listo"},
            {"id": "EDIT_PLUS", "title": "➕"},
        ])
        return

    # Pago
    if iid == "PAY_START":
        await pay_start(user_id, session)
        return

    if iid == "PAY_DELIVERY" or iid == "PAY_PICKUP" or iid == "CANCEL_PAY":
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
            # NO mostramos precio, solo avisamos que es adicional
            send_buttons(user_id, "🚚 El envío tiene un costo adicional.\n\n¿Procedemos con tus datos?", [
                {"id": "DELIVERY_PROCEED", "title": "1) Sí, proceder"},
                {"id": "CANCEL_PAY", "title": "Cancelar"},
                {"id": "HOME_ASESOR", "title": "Asesor"},
            ])
            session["state"] = "PAY_DELIVERY_NOTICE"
            return

    if iid == "DELIVERY_PROCEED":
        session["state"] = "PAY_ADDRESS"
        send_text(user_id, "📍 Escribí tu *dirección completa* (y referencia si querés):")
        return

    # Selección de grupo/distrito
    if iid.startswith("DG_"):
        dg = iid.replace("DG_", "")
        if dg == "OUT":
            # fuera de managua -> asesor
            send_text(user_id, "📌 Esta dirección está fuera de Managua.\nUn asesor te cotiza el envío por aquí 🙂")
            show_asesor(user_id)
            session["state"] = "HOME"
            return

        # set fee
        match = next((g for g in DELIVERY_GROUPS if g[0] == dg), None)
        if not match:
            home_menu(user_id)
            return

        _, label, fee = match
        session["tmp"]["district_group"] = label
        session["tmp"]["delivery_fee"] = fee

        await ask_payment_method(user_id, session)
        return

    # Método de pago
    if iid in ("PAY_CASH", "PAY_CARD", "PAY_TRANSFER"):
        method = {"PAY_CASH": "Efectivo", "PAY_CARD": "Tarjeta", "PAY_TRANSFER": "Transferencia"}[iid]
        session["tmp"]["payment_method"] = method
        await send_invoice_and_confirm(user_id, session)
        return

    if iid in ("CONFIRM_ORDER", "CANCEL_ORDER"):
        if iid == "CANCEL_ORDER":
            session["state"] = "HOME"
            send_text(user_id, "Pedido cancelado. Podés volver a armarlo cuando quieras 🙂")
            home_menu(user_id)
            return

        # confirmado
        send_text(user_id, "✅ Pedido recibido. En breve te confirmamos por aquí 🙌")
        reset_session(user_id)
        home_menu(user_id)
        return

    # fallback
    home_menu(user_id)


async def resend_qty(user_id: str, session: Dict[str, Any]):
    picked = session["tmp"].get("picked")
    if not picked:
        home_menu(user_id)
        return
    name = picked["name"]
    price = picked["price"]
    side1 = session["tmp"].get("side1")
    side2 = session["tmp"].get("side2")
    qty = int(session["tmp"].get("qty", 1))

    if side1 and side2:
        conf = f"{side1} + {side2}"
        summary = f"✅ *{name}* ({conf}) — C${price}"
    elif side1 and not side2:
        summary = f"✅ *{name}* ({side1}) — C${price}"
    else:
        summary = f"✅ *{name}* — C${price}"

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
        rows.append({"id": f"DG_{gkey}", "title": label, "description": "Seleccionar"})
    rows.append({"id": "DG_OUT", "title": OUTSIDE_MANAGUA_LABEL, "description": "Cotiza con asesor"})

    sections = [{"title": "Distritos", "rows": rows}]
    send_list(to, "📍 ¿A qué distrito pertenece tu dirección?", "Elegir", sections)


async def ask_payment_method(to: str, session: Dict[str, Any]):
    session["state"] = "PAY_METHOD"
    send_buttons(to, "Método de pago:", [
        {"id": "PAY_CASH", "title": "1) Efectivo"},
        {"id": "PAY_CARD", "title": "2) Tarjeta"},
        {"id": "PAY_TRANSFER", "title": "3) Transferencia"},
    ])


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

    send_buttons(to, "\n".join(lines) + "\n\n¿Confirmás el pedido?", [
        {"id": "CONFIRM_ORDER", "title": "1) Confirmar"},
        {"id": "CANCEL_ORDER", "title": "2) Cancelar"},
        {"id": "HOME_ASESOR", "title": "Asesor"},
    ])
    session["state"] = "CONFIRM"
