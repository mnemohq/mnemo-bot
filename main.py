import os
import anthropic
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
client = anthropic.Anthropic()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    incoming_msg = update.message.text
    
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system="""Tu es Mnemo, un assistant de mémoire personnelle bienveillant. 
        Ton rôle est d'aider l'utilisateur à capturer, organiser et retrouver ses pensées et idées.
        Réponds toujours en français de manière concise et encourageante.""",
        messages=[{"role": "user", "content": incoming_msg}]
    )
    
    reply = response.content[0].text
    await update.message.reply_text(reply)

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

