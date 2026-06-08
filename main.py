import os
import requests
import anthropic

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
ANTHROPIC_KEY = os.environ.get('ANTHROPIC_API_KEY')
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

def get_updates(offset=None):
    url = f"{BASE_URL}/getUpdates"
    params = {"timeout": 30, "offset": offset}
    r = requests.get(url, params=params)
    return r.json()

def send_message(chat_id, text):
    url = f"{BASE_URL}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text})

def ask_mnemo(text):
    response = client.messages.create(
        model="claude-haiku-4-5-20251001,
        max_tokens=1024,
        system="Tu es Mnemo, un assistant de mémoire personnelle. Tu aides à capturer, organiser et retrouver les pensées et idées. Réponds en français de manière concise.",
        messages=[{"role": "user", "content": text}]
    )
    return response.content[0].text

def main():
    offset = None
    print("Mnemo bot started!")
    while True:
        updates = get_updates(offset)
        for update in updates.get("result", []):
            offset = update["update_id"] + 1
            msg = update.get("message", {})
            chat_id = msg.get("chat", {}).get("id")
            text = msg.get("text", "")
            if chat_id and text:
                reply = ask_mnemo(text)
                send_message(chat_id, reply)

if __name__ == "__main__":
    main()

