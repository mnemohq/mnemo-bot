from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
import anthropic

app = Flask(__name__)
client = anthropic.Anthropic()

@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.values.get("Body", "").strip()
    
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system="""Tu es Mnemo, un assistant de mémoire personnelle bienveillant. 
        Ton rôle est d'aider l'utilisateur à capturer, organiser et retrouver ses pensées et idées.
        Réponds toujours en français de manière concise et encourageante.""",
        messages=[{"role": "user", "content": incoming_msg}]
    )
    
    reply = response.content[0].text
    resp = MessagingResponse()
    resp.message(reply)
    return str(resp)
@app.route("/")
def home():
    return "Mnemo bot is running!"

if __name__ == "__main__":
    app.run(debug=True)
