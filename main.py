
import os
import time
import re
import requests
from typing import Dict, Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, JSONResponse

app = FastAPI()

# =========================
# ENV
# =========================
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "lux_verify_123")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "")  # Meta -> "Identificador de número de teléfono"
GRAPH_URL = "https://graph.facebook.com/v22.0"

# =========================
# MENÚ
# =========================
MENU_COMIDA = [
    ("Pollo tapado", 150),
    ("Bisteck", 180),
    ("Carne desmenuzada", 180),
    ("Pollo asado", 200),
    ("Nacatamal", 80),
    ("Carne asada", 200),
    ("Arroz a la valenciana", 150),
    ("Baho", 200),
]

MENU_BEBIDAS = [
    ("Jamaica", 35),
    ("Guayaba", 35),
    ("Cálala", 35),
    ("Naranja", 35),
    ("Cebada", 35),
    ("Cacao", 60),
]

DIRECCION = "De la entrada de las fuentes 5c y media al sur mano izquierda"
HORARIO = "9:00 a.m. a 10:00 p.m."

# =========================
# SESIONES (memoria en RAM)
# =========================
SESSION_TTL_SEC = 20 * 60  # 20 min

# sessions[wa_id] = {
#   "ts": last_update,
#   "state": "...",
#   "cart": { "c1": {"name":..., "price":..., "qty":...}, ... },
#   "tmp": {...}
# }
sessions: Dict[str, Dict[str, Any]] = {}


def now() -> int:
    return int(time.time())


def get_session(user_id: str) -> Dict[str, Any]:
    s = sessions.get(user_id)
    if not s:
        s = {"ts": now(), "state": "HOME", "cart": {}, "tmp": {}}
        sessions[user_id] = s
        return s

    # Expiración
    if now() - s.get("ts", 0) > SESSION_TTL_SEC:
        s = {"ts": now(), "state": "HOME", "cart": {}, "tmp": {}}
        sessions[user_id] = s
        return s

    s["ts"] = now()
    return s


def reset_session(user_id: str):
    sessions[user_id] = {"ts": now(), "state": "HOME", "cart": {}, "tmp": {}}


# =========================
# WhatsApp SEND helpers
# =========================
def wa_headers():
    return {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }


def wa_post(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        return {"error": "Missing WHATSAPP_TOKEN or PHONE_NUMBER_ID"}
    url = f"{GRAPH_URL}/{PHONE_NUMBER_ID}/messages"
    r = requests.post(url, headers=wa_headers(), json=payload, timeout=20)
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
    # buttons: [{"id": "...", "title": "..."}] max 3
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
    # sections = [{"title": "...", "rows":[{"id":"...", "title":"...", "description":"..."}]}]
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
# UI builders
# =========================
def home_menu(to: str):
    body = (
        "👋 *Bienvenido a El Merol de Pancho.*\n\n"
        "Opciones (tocá o escribí el número):\n"
        "1) Menú\n"
        "2) Pedir\n"
        "3) Carrito\n"
        "4) Ubicación y horario\n"
        "5) Asesor\n"
        "6) Borrar orden"
    )
    # Botones (3 máx) -> mandamos 2 tandas para cubrir todo sin saturar
    send_buttons(to, body, [
        {"id": "HOME_MENU", "title": "1) Menú"},
        {"id": "HOME_PEDIR", "title": "2) Pedir"},
        {"id": "HOME_CARRITO", "title": "3) Carrito"},
    ])
    send_buttons(to, "Más opciones:", [
        {"id": "HOME_UBI", "title": "4) Ubicación"},
        {"id": "HOME_ASESOR", "title": "5) Asesor"},
        {"id": "HOME_BORRAR", "title": "6) Borrar"},
    ])


def categorias_menu(to: str, title: str = "Elegí categoría"):
    # Un solo list, sin texto duplicado
    sections = [{
        "title": "Categorías",
        "rows": [
            {"id": "CAT_COMIDA", "title": "1) Comida", "description": "Platos principales"},
            {"id": "CAT_BEBIDAS", "title": "2) Bebidas", "description": "Frescos y cacao"},
        ]
    }]
    send_list(to, f"📋 *{title}*", "Ver categorías", sections)


def productos_list(to: str, categoria: str):
    if categoria == "COMIDA":
        items = MENU_COMIDA
        prefix = "c"
        title = "📌 COMIDA (tocá un producto)"
    else:
        items = MENU_BEBIDAS
        prefix = "b"
        title = "📌 BEBIDAS (tocá un producto)"

    rows = []
    for i, (name, price) in enumerate(items, start=1):
        rows.append({
            "id": f"PROD_{prefix}{i}",
            "title": f"{i}) {name} — C${price}",
            "description": f"Escribí: {i} (o {prefix}{i})"
        })

    sections = [{"title": "Productos", "rows": rows}]
    send_list(to, title, "Ver productos", sections)


def qty_stepper(to: str, product_name: str, qty: int, hint: str = ""):
    # Regleta con 3 botones
    body = f"🧮 *{product_name}*\nCantidad: *{qty}*"
    if hint:
        body += f"\n{hint}"
    send_buttons(to, body, [
        {"id": "QTY_MINUS", "title": "➖"},
        {"id": "QTY_ADD", "title": "✅ Agregar"},
        {"id": "QTY_PLUS", "title": "➕"},
    ])


def post_add_actions(to: str):
    send_buttons(to, "✅ Agregado.\n¿Qué hacemos ahora?", [
        {"id": "AFTER_ADD_MORE", "title": "➕ Agregar otro"},
        {"id": "AFTER_ADD_CART", "title": "🧺 Ver carrito"},
        {"id": "AFTER_ADD_PAY", "title": "💳 Pagar"},
    ])


def show_ubi(to: str):
    send_text(to, f"📍 *Ubicación*\n{DIRECCION}\n\n🕘 *Horario*\n{HORARIO}")


def show_asesor(to: str):
    # Esto no transfiere “realmente” el chat, solo avisa y deja al humano responder manualmente.
    send_text(to, "🧑‍💼 Perfecto. Un asesor te escribe en breve por este mismo número.\n\n(Escribí tu consulta aquí 👇)")


def cart_text(session: Dict[str, Any]) -> str:
    cart = session["cart"]
    if not cart:
        return "🧺 Tu carrito está vacío.\n\nPodés tocar *2) Pedir* para iniciar."
    lines = ["🧺 *Tu carrito:*"]
    total = 0
    idx = 1
    for code, it in cart.items():
        qty = it["qty"]
        price = it["price"]
        subtotal = qty * price
        total += subtotal
        lines.append(f"{idx}) {qty} x {it['name']} — C${price} c/u")
        idx += 1
    lines.append(f"\n*Total: C${total}*")
    return "\n".join(lines)


def cart_actions(to: str, session: Dict[str, Any]):
    send_text(to, cart_text(session))
    send_buttons(to, "Acciones del carrito:", [
        {"id": "CART_EDIT", "title": "1) Editar"},
        {"id": "CART_CLEAR", "title": "2) Vaciar"},
        {"id": "CART_PAY", "title": "3) Pagar"},
    ])
    send_buttons(to, "Más:", [
        {"id": "CART_MENU", "title": "4) Menú"},
        {"id": "HOME_ASESOR", "title": "Asesor"},
        {"id": "HOME_BORRAR", "title": "Borrar"},
    ])


def cart_pick_item(to: str, session: Dict[str, Any]):
    cart = session["cart"]
    if not cart:
        send_text(to, "Tu carrito está vacío.")
        home_menu(to)
        return

    rows = []
    idx_map = []
    idx = 1
    for code, it in cart.items():
        rows.append({
            "id": f"EDIT_{code}",
            "title": f"{idx}) {it['name']}",
            "description": f"Cantidad actual: {it['qty']}"
        })
        idx_map.append(code)
        idx += 1

    sections = [{"title": "Elegí un item para ajustar", "rows": rows}]
    send_list(to, "✏️ Editar carrito (tocá un item)", "Ver items", sections)


def pay_start(to: str, session: Dict[str, Any]):
    if not session["cart"]:
        send_text(to, "🧺 Tu carrito está vacío. Primero agregá algo 🙂")
        home_menu(to)
        return
    session["state"] = "PAY_NAME"
    send_text(to, "🧾 Para registrar tu pedido: ¿Cuál es tu *nombre*?")


def total_cart(session: Dict[str, Any]) -> int:
    total = 0
    for it in session["cart"].values():
        total += it["qty"] * it["price"]
    return total


# =========================
# PARSERS
# =========================
def normalize_text(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").strip().lower())


def parse_product_code_from_text(t: str, current_category: Optional[str]) -> Optional[str]:
    # Permite: "1", "c1", "b6", etc.
    tt = normalize_text(t)

    # Si escribe "c1" o "b2"
    m = re.fullmatch(r"([cb])\s*([1-9])", tt)
    if m:
        prefix = m.group(1)
        num = int(m.group(2))
        return f"{prefix}{num}"

    # Si escribe solo número, usamos la categoría actual
    m2 = re.fullmatch(r"([1-9])", tt)
    if m2 and current_category in ("COMIDA", "BEBIDAS"):
        num = int(m2.group(1))
        prefix = "c" if current_category == "COMIDA" else "b"
        return f"{prefix}{num}"

    return None


def get_product_by_code(code: str):
    # code "c1".."c9" o "b1".."b9"
    prefix = code[0]
    idx = int(code[1:]) - 1
    if prefix == "c" and 0 <= idx < len(MENU_COMIDA):
        name, price = MENU_COMIDA[idx]
        return {"code": code, "name": name, "price": price}
    if prefix == "b" and 0 <= idx < len(MENU_BEBIDAS):
        name, price = MENU_BEBIDAS[idx]
        return {"code": code, "name": name, "price": price}
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
        from_id = msg.get("from")  # wa_id del cliente
        session = get_session(from_id)

        # Captura texto o botón o lista
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

        # ROUTER
        await handle_message(from_id, session, text=text, interactive_id=interactive_id)
        return JSONResponse({"ok": True})

    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=200)


async def handle_message(user_id: str, session: Dict[str, Any], text: str = "", interactive_id: Optional[str] = None):
    t = normalize_text(text)

    # Atajos por texto
    if t in ("menu", "menú"):
        session["state"] = "HOME"
        home_menu(user_id)
        return
    if t == "carrito":
        session["state"] = "HOME"
        cart_actions(user_id, session)
        return
    if t == "pagar":
        pay_start(user_id, session)
        return
    if t == "borrar":
        reset_session(user_id)
        send_text(user_id, "🗑️ Orden borrada. Empecemos de nuevo 🙂")
        home_menu(user_id)
        return

    # Si viene por botones/lista
    if interactive_id:
        await handle_interactive(user_id, session, interactive_id)
        return

    # Si viene texto normal, depende del estado
    state = session.get("state", "HOME")

    if state == "HOME":
        # Permitir 1..6 por texto
        if t == "1":
            categorias_menu(user_id, "Menú — elegí categoría")
        elif t == "2":
            categorias_menu(user_id, "Pedir — elegí categoría")
            session["tmp"]["intent"] = "ORDER"
        elif t == "3":
            cart_actions(user_id, session)
        elif t == "4":
            show_ubi(user_id)
        elif t == "5":
            show_asesor(user_id)
        elif t == "6":
            reset_session(user_id)
            send_text(user_id, "🗑️ Orden borrada.")
            home_menu(user_id)
        else:
            home_menu(user_id)
        return

    if state in ("PICK_PRODUCT",):
        # Permitir selección por texto "1" o "c1"/"b2"
        cat = session["tmp"].get("category")
        code = parse_product_code_from_text(t, cat)
        prod = get_product_by_code(code) if code else None
        if not prod:
            send_text(user_id, "No entendí. Tocá un producto en la lista o escribí su número/código.")
            return
        # Ir a regleta
        session["tmp"]["current_product"] = prod
        session["tmp"]["qty"] = 1
        session["state"] = "QTY"
        qty_stepper(user_id, prod["name"], 1, hint="Usá ➖/➕ y luego ✅ Agregar.")
        return

    if state == "PAY_NAME":
        if len(t) < 2:
            send_text(user_id, "Decime tu nombre, por favor 🙂")
            return
        session["tmp"]["name"] = text.strip()
        session["state"] = "PAY_DELIVERY_TYPE"
        send_buttons(user_id, "¿Entrega o retiro?", [
            {"id": "DELIVERY", "title": "Delivery"},
            {"id": "PICKUP", "title": "Retiro"},
            {"id": "CANCEL_PAY", "title": "Cancelar"},
        ])
        return

    if state == "PAY_ADDRESS":
        if len(t) < 5:
            send_text(user_id, "Pasame la dirección completa, por favor.")
            return
        session["tmp"]["address"] = text.strip()
        session["state"] = "PAY_METHOD"
        send_buttons(user_id, "Método de pago:", [
            {"id": "PAY_CASH", "title": "Efectivo"},
            {"id": "PAY_CARD", "title": "Tarjeta"},
            {"id": "PAY_TRANSFER", "title": "Transferencia"},
        ])
        return

    # Fallback general
    home_menu(user_id)


async def handle_interactive(user_id: str, session: Dict[str, Any], iid: str):
    # HOME
    if iid in ("HOME_MENU", "HOME_PEDIR", "HOME_CARRITO", "HOME_UBI", "HOME_ASESOR", "HOME_BORRAR"):
        session["state"] = "HOME"
        if iid == "HOME_MENU":
            categorias_menu(user_id, "Menú — elegí categoría")
        elif iid == "HOME_PEDIR":
            categorias_menu(user_id, "Pedir — elegí categoría")
            session["tmp"]["intent"] = "ORDER"
        elif iid == "HOME_CARRITO":
            cart_actions(user_id, session)
        elif iid == "HOME_UBI":
            show_ubi(user_id)
        elif iid == "HOME_ASESOR":
            show_asesor(user_id)
        elif iid == "HOME_BORRAR":
            reset_session(user_id)
            send_text(user_id, "🗑️ Orden borrada.")
            home_menu(user_id)
        return

    # Categorías
    if iid in ("CAT_COMIDA", "CAT_BEBIDAS"):
        cat = "COMIDA" if iid == "CAT_COMIDA" else "BEBIDAS"
        session["tmp"]["category"] = cat
        session["state"] = "PICK_PRODUCT"
        productos_list(user_id, cat)
        return

    # Selección producto desde lista
    if iid.startswith("PROD_"):
        code = iid.replace("PROD_", "")  # c1 / b2
        prod = get_product_by_code(code)
        if not prod:
            send_text(user_id, "Ese producto ya no está disponible.")
            return
        session["tmp"]["current_product"] = prod
        session["tmp"]["qty"] = 1
        session["state"] = "QTY"
        qty_stepper(user_id, prod["name"], 1, hint="Usá ➖/➕ y luego ✅ Agregar.")
        return

    # Regleta cantidad
    if iid in ("QTY_MINUS", "QTY_PLUS", "QTY_ADD"):
        prod = session["tmp"].get("current_product")
        if not prod:
            session["state"] = "HOME"
            home_menu(user_id)
            return

        qty = int(session["tmp"].get("qty", 1))

        if iid == "QTY_MINUS":
            qty = max(1, qty - 1)
            session["tmp"]["qty"] = qty
            qty_stepper(user_id, prod["name"], qty)
            return

        if iid == "QTY_PLUS":
            qty = min(9, qty + 1)
            session["tmp"]["qty"] = qty
            qty_stepper(user_id, prod["name"], qty)
            return

        if iid == "QTY_ADD":
            cart = session["cart"]
            code = prod["code"]
            if code not in cart:
                cart[code] = {"name": prod["name"], "price": prod["price"], "qty": 0}
            cart[code]["qty"] += qty

            total = total_cart(session)
            send_text(user_id, f"✅ Agregado: {qty} x {prod['name']}\nTotal: C${total}")
            session["state"] = "HOME"
            post_add_actions(user_id)
            return

    # Después de agregar
    if iid in ("AFTER_ADD_MORE", "AFTER_ADD_CART", "AFTER_ADD_PAY"):
        if iid == "AFTER_ADD_MORE":
            categorias_menu(user_id, "Elegí categoría para seguir agregando")
        elif iid == "AFTER_ADD_CART":
            cart_actions(user_id, session)
        elif iid == "AFTER_ADD_PAY":
            pay_start(user_id, session)
        return

    # Carrito
    if iid in ("CART_EDIT", "CART_CLEAR", "CART_PAY", "CART_MENU"):
        if iid == "CART_EDIT":
            cart_pick_item(user_id, session)
        elif iid == "CART_CLEAR":
            session["cart"] = {}
            send_text(user_id, "🗑️ Carrito vaciado.")
            home_menu(user_id)
        elif iid == "CART_PAY":
            pay_start(user_id, session)
        elif iid == "CART_MENU":
            categorias_menu(user_id, "Menú — elegí categoría")
        return

    # Elegir item a editar
    if iid.startswith("EDIT_"):
        code = iid.replace("EDIT_", "")
        it = session["cart"].get(code)
        if not it:
            send_text(user_id, "Ese item ya no está en el carrito.")
            cart_actions(user_id, session)
            return

        session["tmp"]["edit_code"] = code
        session["tmp"]["edit_qty"] = it["qty"]
        session["state"] = "EDIT_QTY"
        send_buttons(user_id, f"✏️ *{it['name']}*\nCantidad: *{it['qty']}*", [
            {"id": "EDIT_MINUS", "title": "➖"},
            {"id": "EDIT_DONE", "title": "✅ Listo"},
            {"id": "EDIT_PLUS", "title": "➕"},
        ])
        return

    if iid in ("EDIT_MINUS", "EDIT_PLUS", "EDIT_DONE"):
        code = session["tmp"].get("edit_code")
        if not code or code not in session["cart"]:
            cart_actions(user_id, session)
            return

        qty = int(session["tmp"].get("edit_qty", session["cart"][code]["qty"]))

        if iid == "EDIT_MINUS":
            qty = max(0, qty - 1)
            session["tmp"]["edit_qty"] = qty
            nm = session["cart"][code]["name"]
            send_buttons(user_id, f"✏️ *{nm}*\nCantidad: *{qty}*", [
                {"id": "EDIT_MINUS", "title": "➖"},
                {"id": "EDIT_DONE", "title": "✅ Listo"},
                {"id": "EDIT_PLUS", "title": "➕"},
            ])
            return

        if iid == "EDIT_PLUS":
            qty = min(9, qty + 1)
            session["tmp"]["edit_qty"] = qty
            nm = session["cart"][code]["name"]
            send_buttons(user_id, f"✏️ *{nm}*\nCantidad: *{qty}*", [
                {"id": "EDIT_MINUS", "title": "➖"},
                {"id": "EDIT_DONE", "title": "✅ Listo"},
                {"id": "EDIT_PLUS", "title": "➕"},
            ])
            return

        if iid == "EDIT_DONE":
            qty = int(session["tmp"].get("edit_qty", 1))
            if qty <= 0:
                session["cart"].pop(code, None)
                send_text(user_id, "🗑️ Item eliminado.")
            else:
                session["cart"][code]["qty"] = qty
                send_text(user_id, "✅ Cantidad actualizada.")

            session["state"] = "HOME"
            cart_actions(user_id, session)
            return

    # Pago
    if iid in ("DELIVERY", "PICKUP", "CANCEL_PAY"):
        if iid == "CANCEL_PAY":
            session["state"] = "HOME"
            send_text(user_id, "Pago cancelado.")
            home_menu(user_id)
            return

        if iid == "DELIVERY":
            session["tmp"]["delivery"] = "delivery"
            session["state"] = "PAY_ADDRESS"
            send_text(user_id, "📍 Pasame tu *dirección* para delivery:")
            return

        if iid == "PICKUP":
            session["tmp"]["delivery"] = "retiro"
            session["tmp"]["address"] = "Retiro en local"
            session["state"] = "PAY_METHOD"
            send_buttons(user_id, "Método de pago:", [
                {"id": "PAY_CASH", "title": "Efectivo"},
                {"id": "PAY_CARD", "title": "Tarjeta"},
                {"id": "PAY_TRANSFER", "title": "Transferencia"},
            ])
            return

    if iid in ("PAY_CASH", "PAY_CARD", "PAY_TRANSFER"):
        method = {"PAY_CASH": "efectivo", "PAY_CARD": "tarjeta", "PAY_TRANSFER": "transferencia"}[iid]
        session["tmp"]["payment"] = method

        # Resumen
        name = session["tmp"].get("name", "Cliente")
        phone = user_id
        total = total_cart(session)
        delivery = session["tmp"].get("delivery", "")
        address = session["tmp"].get("address", "")

        summary_lines = [
            f"🧾 *Nuevo pedido*",
            f"Nombre: {name}",
            f"Cliente: {phone}",
            "",
            cart_text(session),
            "",
            f"Entrega: {delivery}",
            f"Dirección: {address}",
            f"Pago: {method}",
        ]
        summary = "\n".join(summary_lines)

        send_buttons(user_id, summary + "\n\n¿Confirmás el pedido?", [
            {"id": "CONFIRM_ORDER", "title": "1) Confirmar"},
            {"id": "CANCEL_ORDER", "title": "2) Cancelar"},
            {"id": "HOME_CARRITO", "title": "Carrito"},
        ])
        session["state"] = "CONFIRM"
        return

    if iid in ("CONFIRM_ORDER", "CANCEL_ORDER"):
        if iid == "CANCEL_ORDER":
            session["state"] = "HOME"
            send_text(user_id, "Pedido cancelado. Podés volver a armarlo cuando quieras 🙂")
            home_menu(user_id)
            return

        # Confirmado
        send_text(user_id, "✅ Pedido recibido. En breve te confirmamos por aquí 🙌")
        # Aquí podrías enviar el resumen a un número interno del restaurante (cuando ya tengan número real)
        session["state"] = "HOME"
        reset_session(user_id)
        return

    # Fallback
    home_menu(user_id)
