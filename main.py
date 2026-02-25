from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
import os
import requests

app = FastAPI(title="WhatsApp Orders API")

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "lux_verify_123")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "")

@app.get("/health")
def health():
    return {"status": "ok"}

# Verificación del webhook (GET)
@app.get("/webhook/whatsapp")
def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    challenge = request.query_params.get("hub.challenge")
    token = request.query_params.get("hub.verify_token")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return PlainTextResponse(challenge or "")
    return {"error": "Verification failed"}

def send_whatsapp_text(to: str, text: str):
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        print("Missing WHATSAPP_TOKEN or PHONE_NUMBER_ID in env vars.")
        return

    url = f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }

    r = requests.post(url, headers=headers, json=payload)
    print("SEND MESSAGE STATUS:", r.status_code)
    try:
        print("SEND MESSAGE RESPONSE:", r.json())
    except Exception:
        print("SEND MESSAGE RESPONSE (raw):", r.text)

# Recepción de mensajes (POST)
@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    payload = await request.json()
    print("INCOMING WHATSAPP EVENT:")
    print(payload)

    # Intentar extraer mensaje entrante (texto) y responder
    try:
        entry = payload["entry"][0]
        change = entry["changes"][0]
        value = change["value"]

        # mensajes entrantes
        messages = value.get("messages", [])
        if messages:
            msg = messages[0]
            from_number = msg.get("from")  # número del usuario que escribió
            text_body = (msg.get("text") or {}).get("body", "")

            if from_number:
                reply = f"✅ Recibí tu mensaje: {text_body}"
                send_whatsapp_text(from_number, reply)

    except Exception as e:
        print("ERROR parsing webhook:", str(e))

    return {"ok": True}

