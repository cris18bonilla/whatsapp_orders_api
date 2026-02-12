VERIFY_TOKEN = os.getenv("verify_token", "lux_verify_123")
VERIFY_TOKEN = os.getenv("verify_token", "lux_verify_123")from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
import os

app = FastAPI(title="WhatsApp Orders API")

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "lux_verify_123")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/webhook/whatsapp")
def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    challenge = request.query_params.get("hub.challenge")
    token = request.query_params.get("hub.verify_token")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return PlainTextResponse(challenge or "")
    return {"error": "Verification failed"}

@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    payload = await request.json()
    print("INCOMING WHATSAPP EVENT:")
    print(payload)
    return {"ok": True}
