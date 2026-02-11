from fastapi import FastAPI, Request

app = FastAPI(title="WhatsApp Orders API")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    payload = await request.json()
    print("INCOMING WHATSAPP EVENT:")
    print(payload)
    return {"ok": True}
