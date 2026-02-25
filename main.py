from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
import os, time, re, unicodedata
import requests

app = FastAPI(title="WhatsApp Orders API")

# ===== ENV (Render) =====
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "lux_verify_123")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "")
ADMIN_PHONE = os.getenv("ADMIN_PHONE", "")  # ej: 50586907134 (sin +)
GRAPH_VERSION = os.getenv("GRAPH_VERSION", "v22.0")
SESSION_TTL_MIN = int(os.getenv("SESSION_TTL_MIN", "20"))

# ===== INFO NEGOCIO =====
BUSINESS_LOCATION = "De la entrada de las fuentes 5c y media al sur mano izquierda"
BUSINESS_HOURS = "9:00 a.m. a 10:00 p.m."

# ===== MENÚ REAL =====
MENU = {
    "comida": [
        {"id": "c1", "name": "Pollo tapado", "price": 150},
        {"id": "c2", "name": "Bisteck", "price": 180},
        {"id": "c3", "name": "Carne desmenuzada", "price": 180},
        {"id": "c4", "name": "Pollo asado", "price": 200},
        {"id": "c5", "name": "Nacatamal", "price": 80},
        {"id": "c6", "name": "Carne asada", "price": 200},
        {"id": "c7", "name": "Arroz a la valenciana", "price": 150},
        {"id": "c8", "name": "Baho", "price": 200},
    ],
    "bebidas": [
        {"id": "b1", "name": "Jamaica", "price": 35},
        {"id": "b2", "name": "Guayaba", "price": 35},
        {"id": "b3", "name": "Cálala", "price": 35},
        {"id": "b4", "name": "Naranja", "price": 35},
        {"id": "b5", "name": "Cebada", "price": 35},
        {"id": "b6", "name": "Cacao", "price": 60},
    ],
}

# ===== Sesiones en memoria (demo) =====
# SESSIONS[sender] = {
#   step, expires_at, warned_expiry,
#   cart: [{id,name,price,qty}],
#   current_map: { "1": item_id, ... },  # para selección por número
#   pending_item_id, pending_item_name,
#   customer_name, delivery, address, pay_method,
#   human_mode
# }
SESSIONS = {}

# ---------- Utils ----------
def now_ts():
    return time.time()

def ttl_seconds():
    return SESSION_TTL_MIN * 60

def normalize(s: str) -> str:
    s = s.lower().strip()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s

def money(n: int) -> str:
    return f"C${n}"

def cart_total(cart) -> int:
    return sum(i["price"] * i["qty"] for i in cart)

def find_item_by_id(item_id: str):
    for cat in MENU.values():
        for it in cat:
            if it["id"] == item_id:
                return it
    return None

def search_items_in_text(text: str):
    """Detecta nombres de productos dentro del texto (muy simple)."""
    t = normalize(text)
    hits = []
    for cat in MENU.values():
        for it in cat:
            name_norm = normalize(it["name"])
            if name_norm in t:
                hits.append(it)
    # quitar duplicados por id
    uniq = {}
    for h in hits:
        uniq[h["id"]] = h
    return list(uniq.values())

def extract_qty(text: str):
    """Si el usuario escribe '2 baho', intenta sacar el 2."""
    m = re.search(r"\b(\d{1,2})\b", normalize(text))
    if not m:
        return None
    q = int(m.group(1))
    return q if 1 <= q <= 50 else None

# ---------- WhatsApp API helpers ----------
def wa_url(path: str) -> str:
    return f"https://graph.facebook.com/{GRAPH_VERSION}/{path}"

def wa_headers():
    return {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}

def send_text(to: str, body: str):
    url = wa_url(f"{PHONE_NUMBER_ID}/messages")
    data = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": body}}
    r = requests.post(url, headers=wa_headers(), json=data)
    print("SEND_TEXT:", r.status_code, r.text)

def send_buttons(to: str, body: str, buttons: list):
    """buttons: [{"id": "...", "title": "..."}] (máx 3 botones por mensaje en WhatsApp Cloud)"""
    url = wa_url(f"{PHONE_NUMBER_ID}/messages")
    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {"text": body},
            "action": {"buttons": [{"type": "reply", "reply": b} for b in buttons]},
        },
    }
    r = requests.post(url, headers=wa_headers(), json=data)
    print("SEND_BUTTONS:", r.status_code, r.text)

def send_list(to: str, body: str, button_label: str, rows: list, section_title="Opciones"):
    url = wa_url(f"{PHONE_NUMBER_ID}/messages")
    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": body},
            "action": {"button": button_label, "sections": [{"title": section_title, "rows": rows}]},
        },
    }
    r = requests.post(url, headers=wa_headers(), json=data)
    print("SEND_LIST:", r.status_code, r.text)

def notify_admin(body: str):
    if ADMIN_PHONE:
        send_text(ADMIN_PHONE, body)

# ---------- Session ----------
def touch_session(sender: str):
    sess = SESSIONS.get(sender) or {
        "step": "idle",
        "cart": [],
        "current_map": {},
        "human_mode": False,
        "warned_expiry": False,
    }
    sess["expires_at"] = now_ts() + ttl_seconds()
    SESSIONS[sender] = sess
    return sess

def is_expired(sess):
    return sess.get("expires_at") and now_ts() > sess["expires_at"]

def maybe_warn_expiry(sender: str, sess: dict):
    remaining = int(sess.get("expires_at", 0) - now_ts())
    if remaining <= 180 and not sess.get("warned_expiry"):
        sess["warned_expiry"] = True
        SESSIONS[sender] = sess
        send_text(sender, "⏳ Ojo: tu orden se reiniciará pronto por inactividad. Si seguís, respondé cualquier cosa (ej: *menu*).")

def reset_session(sender: str):
    SESSIONS.pop(sender, None)

# ---------- UI building ----------
def show_main_menu(sender: str):
    # Botones (3) + texto con números
    send_buttons(
        sender,
        "👋 Bienvenido a *El Merol de Pancho*.\n\n"
        "Opciones (podés tocar o escribir el número):\n"
        "1) Ver menú\n2) Hacer pedido\n3) Ver carrito\n"
        "4) Ubicación y horario\n5) Asesor\n6) Borrar orden",
        [
            {"id": "MM_1", "title": "1) Menú"},
            {"id": "MM_2", "title": "2) Pedir"},
            {"id": "MM_3", "title": "3) Carrito"},
        ],
    )
    # Segundo mensaje para completar opciones (porque solo caben 3 botones)
    send_buttons(
        sender,
        "Más opciones:\n4) Ubicación y horario\n5) Asesor\n6) Borrar orden",
        [
            {"id": "MM_4", "title": "4) Ubicación"},
            {"id": "MM_5", "title": "5) Asesor"},
            {"id": "MM_6", "title": "6) Borrar"},
        ],
    )

def show_categories(sender: str, title="📋 Elegí una categoría"):
    rows = [
        {"id": "CAT_comida", "title": "1) Comida", "description": "Platos principales"},
        {"id": "CAT_bebidas", "title": "2) Bebidas", "description": "Frescos y cacao"},
    ]
    send_list(sender, f"{title}\n\n(También podés escribir 1 o 2)", "Ver categorías", rows, "Categorías")

def show_items(sender: str, sess: dict, cat_key: str):
    items = MENU.get(cat_key, [])
    # Mapa numérico para escribir "1,2,3..."
    current_map = {}
    rows = []
    text_lines = [f"📌 *{cat_key.upper()}* (tocá o escribí el número)\n"]
    for idx, it in enumerate(items, start=1):
        num = str(idx)
        current_map[num] = it["id"]
        rows.append({
            "id": f"IT_{it['id']}",
            "title": f"{idx}) {it['name']}",
            "description": f"{money(it['price'])}  | código: {it['id']}"
        })
        text_lines.append(f"{idx}) {it['name']} — {money(it['price'])}  | Escribí: {idx} (o {it['id']})")

    text_lines.append("\n🧺 Comandos: *carrito* / *pagar* / *menu*")
    sess["current_map"] = current_map
    sess["step"] = "choose_item"
    sess["category"] = cat_key
    SESSIONS[sender] = sess

    send_list(sender, "\n".join(text_lines[:4]) + ("\n\n(abrí la lista para ver todo)" if len(items) > 3 else ""), "Ver productos", rows, "Productos")
    send_text(sender, "\n".join(text_lines))  # texto completo con números + códigos

def ask_qty(sender: str, sess: dict, item: dict):
    sess["pending_item_id"] = item["id"]
    sess["pending_item_name"] = item["name"]
    sess["pending_item_price"] = item["price"]
    sess["step"] = "quantity"
    SESSIONS[sender] = sess

    send_buttons(
        sender,
        f"¿Cuántos querés de *{item['name']}*?\n(Tocá o escribí 1–4. Para otra, toca 'Otra')",
        [
            {"id": "Q_1", "title": "1"},
            {"id": "Q_2", "title": "2"},
            {"id": "Q_3", "title": "3"},
        ],
    )
    send_buttons(
        sender,
        "Más cantidades:",
        [
            {"id": "Q_4", "title": "4"},
            {"id": "Q_OTHER", "title": "Otra"},
            {"id": "CART_VIEW", "title": "Carrito"},
        ],
    )

def show_after_add(sender: str):
    send_buttons(
        sender,
        "✅ Agregado.\n¿Qué hacemos ahora?",
        [
            {"id": "ADD_MORE", "title": "➕ Agregar más"},
            {"id": "CART_VIEW", "title": "🧺 Ver carrito"},
            {"id": "GO_PAY", "title": "💳 Pagar"},
        ],
    )

def show_cart(sender: str, sess: dict):
    cart = sess["cart"]
    if not cart:
        send_text(sender, "🧺 Tu carrito está vacío. Escribí *menu* para ver opciones.")
        return
    lines = ["🧺 *Tu carrito:*"]
    for i, it in enumerate(cart, start=1):
        lines.append(f"{i}) {it['qty']} x {it['name']} — {money(it['price'])} c/u")
    lines.append(f"\n*Total:* {money(cart_total(cart))}")
    lines.append("\nOpciones: 1) Eliminar  2) Vaciar  3) Pagar  4) Menú")
    send_text(sender, "\n".join(lines))
    send_buttons(
        sender,
        "Acciones del carrito:",
        [
            {"id": "C_ELIM", "title": "1) Eliminar"},
            {"id": "C_VAC", "title": "2) Vaciar"},
            {"id": "GO_PAY", "title": "3) Pagar"},
        ],
    )
    send_buttons(
        sender,
        "Más:",
        [
            {"id": "MM_1", "title": "4) Menú"},
            {"id": "MM_5", "title": "Asesor"},
            {"id": "MM_6", "title": "Borrar"},
        ],
    )

def show_remove_list(sender: str, sess: dict):
    cart = sess["cart"]
    if not cart:
        send_text(sender, "🧺 Tu carrito está vacío.")
        return
    rows = []
    # Mapa numérico para eliminar por número
    rm_map = {}
    for idx, it in enumerate(cart, start=1):
        rm_map[str(idx)] = idx - 1
        rows.append({
            "id": f"RM_{idx-1}",
            "title": f"{idx}) {it['qty']} x {it['name']}",
            "description": f"{money(it['price'])} c/u"
        })
    sess["rm_map"] = rm_map
    sess["step"] = "remove_item"
    SESSIONS[sender] = sess
    send_list(sender, "Elegí cuál eliminar (tocá o escribí el número)", "Eliminar", rows, "Carrito")
    send_text(sender, "Escribí el número del ítem a eliminar (ej: 1) o toca en la lista.")

def start_checkout(sender: str, sess: dict):
    if not sess["cart"]:
        send_text(sender, "🧺 Tu carrito está vacío. Escribí *menu* para empezar.")
        return
    sess["step"] = "ask_name"
    SESSIONS[sender] = sess
    send_text(sender, "📝 Para registrar tu pedido: ¿Cuál es tu *nombre*?")

def ask_delivery(sender: str, sess: dict):
    sess["step"] = "delivery"
    SESSIONS[sender] = sess
    send_buttons(
        sender,
        "¿Cómo será la entrega?\n(1) Delivery  (2) Retiro",
        [
            {"id": "DEL_1", "title": "1) Delivery"},
            {"id": "DEL_2", "title": "2) Retiro"},
            {"id": "CART_VIEW", "title": "Carrito"},
        ],
    )

def ask_payment(sender: str, sess: dict):
    sess["step"] = "pay_method"
    SESSIONS[sender] = sess
    send_buttons(
        sender,
        "¿Método de pago?\n(1) Efectivo  (2) Transferencia",
        [
            {"id": "PAY_1", "title": "1) Efectivo"},
            {"id": "PAY_2", "title": "2) Transferencia"},
            {"id": "CART_VIEW", "title": "Carrito"},
        ],
    )

def ask_confirm(sender: str, sess: dict):
    cart = sess["cart"]
    lines = ["✅ *Confirmación de pedido*"]
    lines.append(f"👤 Nombre: {sess.get('customer_name','-')}")
    lines.append("📦 Items:")
    for it in cart:
        lines.append(f"- {it['qty']} x {it['name']} ({money(it['price'])})")
    lines.append(f"💰 Total: {money(cart_total(cart))}")
    lines.append(f"🚚 Entrega: {sess.get('delivery','-')}")
    if sess.get("delivery") == "delivery":
        lines.append(f"📍 Dirección: {sess.get('address','-')}")
    lines.append(f"💳 Pago: {sess.get('pay_method','-')}")
    send_text(sender, "\n".join(lines))
    sess["step"] = "confirm"
    SESSIONS[sender] = sess
    send_buttons(
        sender,
        "¿Confirmás el pedido?",
        [
            {"id": "CF_Y", "title": "1) Confirmar"},
            {"id": "CF_N", "title": "2) Cancelar"},
            {"id": "CART_VIEW", "title": "Carrito"},
        ],
    )

# ---------- Webhooks ----------
@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/webhook/whatsapp")
def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    challenge = request.query_params.get("hub.challenge")
    token = request.query_params.get("hub.verify_token")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return PlainTextResponse(content=challenge or "")
    return {"error": "Verification failed"}

@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    payload = await request.json()
    print("INCOMING:", payload)

    try:
        value = payload["entry"][0]["changes"][0]["value"]
        if "messages" not in value:
            return {"ok": True}

        msg = value["messages"][0]
        sender = msg["from"]

        sess = SESSIONS.get(sender)
        if sess and is_expired(sess):
            reset_session(sender)
            send_text(sender, "⏳ Se reinició tu sesión por inactividad. Escribí *hola* para empezar de nuevo.")
            return {"ok": True}

        sess = touch_session(sender)
        maybe_warn_expiry(sender, sess)

        text = ""
        lower = ""
        if msg.get("type") == "text":
            text = msg["text"]["body"].strip()
            lower = normalize(text)

        button_id = None
        list_id = None
        if msg.get("type") == "interactive":
            interactive = msg["interactive"]
            if interactive.get("type") == "button_reply":
                button_id = interactive["button_reply"]["id"]
            elif interactive.get("type") == "list_reply":
                list_id = interactive["list_reply"]["id"]

        # ===== MODO ASESOR =====
        if sess.get("human_mode"):
            if lower in ["salir", "menu", "hola"]:
                sess["human_mode"] = False
                sess["step"] = "idle"
                SESSIONS[sender] = sess
                show_main_menu(sender)
                return {"ok": True}
            if text:
                notify_admin(f"🧑‍💼 *Asesor*\nCliente: {sender}\n\n{text}")
                send_text(sender, "✅ Listo, le pasé tu mensaje al asesor. Para volver al menú: *salir*.")
            return {"ok": True}

        # ===== ATAJOS TEXTO =====
        if lower in ["hola", "menu", "menú", "buenas", "buenos dias", "buenos días"]:
            show_main_menu(sender)
            return {"ok": True}

        if lower == "carrito":
            show_cart(sender, sess)
            return {"ok": True}

        if lower == "ubicacion" or lower == "ubicación" or lower == "horario":
            send_text(sender, f"📍 Ubicación: {BUSINESS_LOCATION}\n🕒 Horario: {BUSINESS_HOURS}")
            return {"ok": True}

        # ===== MENÚ PRINCIPAL (botones o número) =====
        def handle_main_option(opt: str):
            if opt == "1":
                show_categories(sender, "📋 Menú — elegí categoría")
            elif opt == "2":
                show_categories(sender, "🛒 Pedido — elegí categoría")
            elif opt == "3":
                show_cart(sender, sess)
            elif opt == "4":
                send_text(sender, f"📍 Ubicación: {BUSINESS_LOCATION}\n🕒 Horario: {BUSINESS_HOURS}")
            elif opt == "5":
                sess["human_mode"] = True
                sess["step"] = "human"
                SESSIONS[sender] = sess
                notify_admin(f"🧑‍💼 *Asesor solicitado*\nCliente: {sender}")
                send_text(sender, "🧑‍💼 Perfecto. Escribí tu consulta y se la paso al asesor.\nPara volver al menú: *salir*.")
            elif opt == "6":
                reset_session(sender)
                send_text(sender, "🗑️ Orden borrada. Escribí *hola* para empezar.")
            else:
                show_main_menu(sender)

        # botones main menu
        if button_id and button_id.startswith("MM_"):
            handle_main_option(button_id.replace("MM_", ""))
            return {"ok": True}

        # si el usuario escribe 1-6 (sin haber tocado nada)
        if lower in ["1","2","3","4","5","6"] and sess.get("step") in ["idle","choose_item","remove_item","delivery","pay_method","confirm","ask_name","address"]:
            # Si está en pasos específicos, no robar el 1/2/3; se procesa por step abajo.
            if sess["step"] in ["idle"]:
                handle_main_option(lower)
                return {"ok": True}

        # ===== LISTAS =====
        if list_id and list_id.startswith("CAT_"):
            cat = list_id.replace("CAT_", "")
            show_items(sender, sess, cat)
            return {"ok": True}

        if list_id and list_id.startswith("IT_"):
            item_id = list_id.replace("IT_", "")
            item = find_item_by_id(item_id)
            if item:
                ask_qty(sender, sess, item)
            else:
                send_text(sender, "No encontré ese producto. Escribí *menu*.")
            return {"ok": True}

        if list_id and list_id.startswith("RM_"):
            idx = int(list_id.replace("RM_", ""))
            if 0 <= idx < len(sess["cart"]):
                removed = sess["cart"].pop(idx)
                SESSIONS[sender] = sess
                send_text(sender, f"🗑️ Eliminado: {removed['qty']} x {removed['name']}")
                show_cart(sender, sess)
            else:
                send_text(sender, "No pude eliminar ese ítem.")
            return {"ok": True}

        # ===== BOTONES DE CANTIDAD =====
        if button_id and button_id.startswith("Q_"):
            if button_id == "Q_OTHER":
                sess["step"] = "quantity_other"
                SESSIONS[sender] = sess
                send_text(sender, "Escribí la cantidad (ej: 5).")
                return {"ok": True}
            qty = int(button_id.replace("Q_", ""))
            item = find_item_by_id(sess.get("pending_item_id",""))
            if not item:
                send_text(sender, "Se perdió el producto. Volvé a *menu*.")
                return {"ok": True}
            sess["cart"].append({"id": item["id"], "name": item["name"], "price": item["price"], "qty": qty})
            sess["step"] = "idle"
            SESSIONS[sender] = sess
            send_text(sender, f"✅ Agregado: {qty} x {item['name']}\nTotal: {money(cart_total(sess['cart']))}")
            show_after_add(sender)
            return {"ok": True}

        # ===== ACCIONES POST-AGREGAR / CARRITO =====
        if button_id == "ADD_MORE":
            show_categories(sender, "➕ Elegí categoría para seguir agregando")
            return {"ok": True}

        if button_id == "CART_VIEW":
            show_cart(sender, sess)
            return {"ok": True}

        if button_id == "GO_PAY":
            start_checkout(sender, sess)
            return {"ok": True}

        if button_id == "C_ELIM":
            show_remove_list(sender, sess)
            return {"ok": True}

        if button_id == "C_VAC":
            sess["cart"] = []
            sess["step"] = "idle"
            SESSIONS[sender] = sess
            send_text(sender, "🗑️ Carrito vaciado. Escribí *menu* para empezar.")
            return {"ok": True}

        # ===== CHECKOUT BOTONES =====
        if button_id and button_id.startswith("DEL_"):
            if button_id == "DEL_1":
                sess["delivery"] = "delivery"
                sess["step"] = "address"
                SESSIONS[sender] = sess
                send_text(sender, "📍 Escribí tu dirección o referencia.")
            else:
                sess["delivery"] = "retiro"
                sess["step"] = "pay_method"
                SESSIONS[sender] = sess
                ask_payment(sender, sess)
            return {"ok": True}

        if button_id and button_id.startswith("PAY_"):
            sess["pay_method"] = "efectivo" if button_id == "PAY_1" else "transferencia"
            SESSIONS[sender] = sess
            ask_confirm(sender, sess)
            return {"ok": True}

        if button_id and button_id.startswith("CF_"):
            if button_id == "CF_N":
                reset_session(sender)
                send_text(sender, "Pedido cancelado ✅. Escribí *hola* para empezar.")
                return {"ok": True}

            # Confirmar
            order_id = f"MP{int(now_ts())}"
            lines = [f"📦 *Nuevo pedido* ({order_id})",
                     f"👤 Nombre: {sess.get('customer_name','-')}",
                     f"📱 Cliente: {sender}",
                     "Items:"]
            for it in sess["cart"]:
                lines.append(f"- {it['qty']} x {it['name']} ({money(it['price'])})")
            lines.append(f"Total: {money(cart_total(sess['cart']))}")
            lines.append(f"Entrega: {sess.get('delivery','-')}")
            if sess.get("delivery") == "delivery":
                lines.append(f"Dirección: {sess.get('address','-')}")
            lines.append(f"Pago: {sess.get('pay_method','-')}")
            notify_admin("\n".join(lines))

            reset_session(sender)
            send_text(sender, "✅ Pedido recibido. En breve te confirmamos por aquí 🙌")
            return {"ok": True}

        # ===== STEPS (texto) =====
        step = sess.get("step","idle")

        # Texto libre: si menciona productos, guiar
        if msg.get("type") == "text":
            hits = search_items_in_text(text)
            if hits and step == "idle":
                # si encuentra 1 producto, preguntar cantidad
                if len(hits) == 1:
                    item = hits[0]
                    q = extract_qty(text)
                    if q:
                        sess["cart"].append({"id": item["id"], "name": item["name"], "price": item["price"], "qty": q})
                        SESSIONS[sender] = sess
                        send_text(sender, f"✅ Entendí: {q} x {item['name']}. Total: {money(cart_total(sess['cart']))}")
                        show_after_add(sender)
                        return {"ok": True}
                    ask_qty(sender, sess, item)
                    return {"ok": True}
                # si son varios, pedir que confirme por lista (más seguro)
                send_text(sender, "Te entendí varios productos. Para evitar errores, mejor armémoslo por el menú 👇")
                show_categories(sender, "Elegí categoría y vamos agregando uno por uno")
                return {"ok": True}

        # seleccionar categoría por número
        if step in ["idle"] and lower in ["1","2"] and not button_id and not list_id:
            # si el usuario escribió 1 o 2 sin abrir lista, interpretarlo como categoría
            cat = "comida" if lower == "1" else "bebidas"
            show_items(sender, sess, cat)
            return {"ok": True}

        if step == "choose_item":
            # puede venir número o id (c6/b2)
            if lower in sess.get("current_map", {}):
                item_id = sess["current_map"][lower]
            else:
                item_id = lower  # permitir c6/b2
            item = find_item_by_id(item_id)
            if not item:
                send_text(sender, "No entendí. Tocá un producto en la lista o escribí su número (ej: 1) o su código (ej: c6).")
                return {"ok": True}
            ask_qty(sender, sess, item)
            return {"ok": True}

        if step == "quantity_other":
            try:
                q = int(lower)
                if q <= 0:
                    raise ValueError()
            except:
                send_text(sender, "Cantidad inválida. Escribí un número (ej: 5).")
                return {"ok": True}
            item = find_item_by_id(sess.get("pending_item_id",""))
            if not item:
                send_text(sender, "Se perdió el producto. Volvé a *menu*.")
                return {"ok": True}
            sess["cart"].append({"id": item["id"], "name": item["name"], "price": item["price"], "qty": q})
            sess["step"] = "idle"
            SESSIONS[sender] = sess
            send_text(sender, f"✅ Agregado: {q} x {item['name']}\nTotal: {money(cart_total(sess['cart']))}")
            show_after_add(sender)
            return {"ok": True}

        if step == "remove_item":
            # eliminar por número
            if lower in sess.get("rm_map", {}):
                idx = sess["rm_map"][lower]
                if 0 <= idx < len(sess["cart"]):
                    removed = sess["cart"].pop(idx)
                    SESSIONS[sender] = sess
                    send_text(sender, f"🗑️ Eliminado: {removed['qty']} x {removed['name']}")
                    show_cart(sender, sess)
                    return {"ok": True}
            send_text(sender, "Elegí un ítem válido (tocá en la lista o escribí 1,2,3...).")
            return {"ok": True}

        if step == "ask_name":
            name = text.strip()
            if len(name) < 2:
                send_text(sender, "Escribí tu nombre (mínimo 2 letras).")
                return {"ok": True}
            sess["customer_name"] = name
            SESSIONS[sender] = sess
            ask_delivery(sender, sess)
            return {"ok": True}

        if step == "address":
            addr = text.strip()
            if len(addr) < 5:
                send_text(sender, "Poné una dirección o referencia más clara 🙂")
                return {"ok": True}
            sess["address"] = addr
            SESSIONS[sender] = sess
            ask_payment(sender, sess)
            return {"ok": True}

        # fallback
        send_text(sender, "Escribí *hola* para ver el menú 😊")
        return {"ok": True}

    except Exception as e:
        print("ERROR:", e)
        return {"ok": True}
