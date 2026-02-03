from fastapi import FastAPI, Request
import requests
from fastapi.responses import JSONResponse
import traceback
import json
from dotenv import load_dotenv
from openai import AzureOpenAI
import os
load_dotenv()

client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
)

DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT")


app = FastAPI()

# 🔹 Replace with YOUR sandbox number
SOURCE_NUMBER = os.getenv("SOURCE_NUMBER")

# 🔹 Your Gupshup API key
API_KEY = os.getenv("API_KEY")

sessions = {}  # in-memory session store


def process_message(phone, text):

    text = text.strip().lower()

    session = sessions.get(phone, {
        "active": False,
        "messages": []
    })

    # ---- EXIT CONVERSATION ----
    if text in ["exit", "quit", "stop"]:
        sessions[phone] = {
            "active": False,
            "messages": []
        }
        return "👋 Conversation ended. Say *Hi* to start again."

    # ---- START CONVERSATION ----
    if not session["active"]:
        if text in ["hi", "hello", "hey"]:
            session["active"] = True
            session["messages"] = [
                {
                    "role": "system",
                    "content": (
                        "You are a Lenskart specialist assistant. "
                        "You help users with eye tests, spectacle lenses, "
                        "frames, contact lenses, blue cut, power issues, "
                        "pricing guidance, and basic eye-care advice. "
                        "Keep responses friendly, short, and helpful. "
                        "Do NOT answer unrelated topics."
                    )
                },
                {
                    "role": "assistant",
                    "content": "Hi 👋 Welcome to Lenskart Support! How can I help you today with your eyes or eyewear?"
                }
            ]
            sessions[phone] = session
            return session["messages"][-1]["content"]
        else:
            return ""  # ignore random text before hi

    # ---- ACTIVE CONVERSATION ----
    session["messages"].append({
        "role": "user",
        "content": text
    })

    try:
        response = client.chat.completions.create(
            model=DEPLOYMENT,
            messages=session["messages"],
            temperature=0.4,
            max_tokens=300
        )

        reply = response.choices[0].message.content
        session["messages"].append({
            "role": "assistant",
            "content": reply
        })

        sessions[phone] = session
        return reply

    except Exception as e:
        print("🔥 LLM ERROR:", e)
        return "Sorry 😕 I'm having trouble right now. Please try again."


def send_message(phone, text):
    url = "https://api.gupshup.io/wa/api/v1/msg"

    message_payload = {
        "type": "text",
        "text": text
    }

    payload = {
        "channel": "whatsapp",
        "source": SOURCE_NUMBER,
        "destination": phone,
        "message": json.dumps(message_payload),
        "src.name": "approchatbot"
    }

    headers = {
        "apikey": API_KEY,
        "Content-Type": "application/x-www-form-urlencoded"
    }

    try:
        response = requests.post(url, data=payload, headers=headers)
    
        print("response",response)
        print("📤 Gupshup response:", response.status_code, response.text)
    except Exception:
        print("🔥 ERROR while sending message")
        traceback.print_exc()


@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        print("📩 Incoming payload:", data)

        payload = data.get("payload")
        if not payload:
            print("⚠️ No payload key")
            return "ignored"

        sender = payload.get("sender", {})
        user_phone = sender.get("phone")
        text = payload.get("payload", {}).get("text")

        if not user_phone or not text:
            print("⚠️ Missing sender phone or text")
            return "ignored"

        reply = process_message(user_phone, text)
        send_message(user_phone, reply)

        return {"status": "ok"}

    except Exception as e:
        print("🔥 ERROR IN WEBHOOK 🔥")
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})
