import os
import re
import sqlite3
import requests
import anthropic
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
ANTHROPIC_KEY = os.environ.get('ANTHROPIC_API_KEY')
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

# ── Base de données ───────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect("mnemo.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            remind_at TEXT NOT NULL,
            sent INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS memos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS active_users (
            chat_id INTEGER PRIMARY KEY
        )
    """)
    conn.commit()
    conn.close()

def save_reminder(chat_id, message, remind_at):
    conn = sqlite3.connect("mnemo.db")
    c = conn.cursor()
    c.execute("INSERT INTO reminders (chat_id, message, remind_at) VALUES (?, ?, ?)",
              (chat_id, message, remind_at))
    conn.commit()
    conn.close()

def get_due_reminders():
    conn = sqlite3.connect("mnemo.db")
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("SELECT id, chat_id, message FROM reminders WHERE remind_at <= ? AND sent = 0", (now,))
    rows = c.fetchall()
    conn.close()
    return rows

def mark_sent(reminder_id):
    conn = sqlite3.connect("mnemo.db")
    c = conn.cursor()
    c.execute("UPDATE reminders SET sent = 1 WHERE id = ?", (reminder_id,))
    conn.commit()
    conn.close()

def save_memo(chat_id, content):
    conn = sqlite3.connect("mnemo.db")
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("INSERT INTO memos (chat_id, content, created_at) VALUES (?, ?, ?)",
              (chat_id, content, now))
    conn.commit()
    conn.close()

def get_today_memos(chat_id):
    conn = sqlite3.connect("mnemo.db")
    c = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("SELECT content FROM memos WHERE chat_id = ? AND created_at LIKE ?",
              (chat_id, f"{today}%"))
    rows = [r[0] for r in c.fetchall()]
    conn.close()
    return rows

def get_tomorrow_reminders(chat_id):
    conn = sqlite3.connect("mnemo.db")
    c = conn.cursor()
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    c.execute("SELECT message, remind_at FROM reminders WHERE chat_id = ? AND remind_at LIKE ? AND sent = 0",
              (chat_id, f"{tomorrow}%"))
    rows = c.fetchall()
    conn.close()
    return rows

def get_all_active_users():
    conn = sqlite3.connect("mnemo.db")
    c = conn.cursor()
    c.execute("SELECT chat_id FROM active_users")
    rows = [r[0] for r in c.fetchall()]
    conn.close()
    return rows

def register_user(chat_id):
    conn = sqlite3.connect("mnemo.db")
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO active_users (chat_id) VALUES (?)", (chat_id,))
    conn.commit()
    conn.close()

# ── Telegram ──────────────────────────────────────────────────────────────────
def get_updates(offset=None):
    url = f"{BASE_URL}/getUpdates"
    params = {"timeout": 30, "offset": offset}
    r = requests.get(url, params=params)
    return r.json()

def send_message(chat_id, text):
    url = f"{BASE_URL}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})

# ── Parser de rappel ──────────────────────────────────────────────────────────
def parse_reminder(text):
    now = datetime.now()
    text = text.strip()

    # "dans X minutes/heures"
    m = re.search(r'dans\s+(\d+)\s*(minute|heure|min|h)', text, re.IGNORECASE)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        delta = timedelta(hours=n) if unit.startswith('h') else timedelta(minutes=n)
        remind_at = now + delta
        msg = re.sub(r'dans\s+\d+\s*(minute|heure|min|h)', '', text, flags=re.IGNORECASE).strip()
        return remind_at.strftime("%Y-%m-%d %H:%M"), msg or "Rappel !"

    # "demain HHhMM"
    m = re.search(r'demain\s+(\d{1,2})[h:](\d{2})?', text, re.IGNORECASE)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2)) if m.group(2) else 0
        remind_at = (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0)
        msg = re.sub(r'demain\s+\d{1,2}[h:]\d{0,2}', '', text, flags=re.IGNORECASE).strip()
        return remind_at.strftime("%Y-%m-%d %H:%M"), msg or "Rappel !"

    # "DD mois HHhMM"
    mois_map = {
        'janvier': 1, 'février': 2, 'mars': 3, 'avril': 4,
        'mai': 5, 'juin': 6, 'juillet': 7, 'août': 8,
        'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12
    }
    m = re.search(
        r'(\d{1,2})\s+(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+(\d{1,2})[h:](\d{2})?',
        text, re.IGNORECASE
    )
    if m:
        day = int(m.group(1))
        month = mois_map[m.group(2).lower()]
        hour = int(m.group(3))
        minute = int(m.group(4)) if m.group(4) else 0
        year = now.year if month >= now.month else now.year + 1
        remind_at = datetime(year, month, day, hour, minute)
        msg = re.sub(
            r'\d{1,2}\s+(janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+\d{1,2}[h:]\d{0,2}',
            '', text, flags=re.IGNORECASE
        ).strip()
        return remind_at.strftime("%Y-%m-%d %H:%M"), msg or "Rappel !"

    return None, None

# ── Claude ────────────────────────────────────────────────────────────────────
def ask_mnemo(text):
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=(
            "Tu es Mnemo, un assistant de mémoire personnelle. "
            "Tu aides à capturer, organiser et retrouver des pensées, notes et souvenirs. "
            "Tu réponds de façon concise et bienveillante en français. "
            "Si l'utilisateur veut créer un rappel, dis-lui d'utiliser la commande /rappel suivie de la date/heure et du message. "
            "Exemple : /rappel demain 9h Appel client"
        ),
        messages=[{"role": "user", "content": text}]
    )
    return response.content[0].text

def generate_evening_review(memos, reminders_tomorrow):
    memos_text = "\n".join(f"- {m}" for m in memos) if memos else "Aucune note aujourd'hui."
    reminders_text = "\n".join(f"- {r[0]} à {r[1]}" for r in reminders_tomorrow) if reminders_tomorrow else "Aucun rappel prévu."

    prompt = (
        f"Voici les notes capturées aujourd'hui par l'utilisateur :\n{memos_text}\n\n"
        f"Voici ses rappels prévus pour demain :\n{reminders_text}\n\n"
        "Fais un bilan de fin de journée chaleureux et concis (5-7 lignes max). "
        "Résume ce qui a été fait/pensé aujourd'hui, et prépare-le mentalement pour demain. "
        "Termine par une phrase d'encouragement."
    )
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system="Tu es Mnemo, assistant de mémoire personnel, chaleureux et bienveillant. Tu parles en français.",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text

def generate_morning_priorities(memos_yesterday, reminders_today):
    memos_text = "\n".join(f"- {m}" for m in memos_yesterday) if memos_yesterday else "Aucune note hier."
    reminders_text = "\n".join(f"- {r[0]} à {r[1]}" for r in reminders_today) if reminders_today else "Aucun rappel aujourd'hui."

    prompt = (
        f"Voici ce que l'utilisateur a noté hier :\n{memos_text}\n\n"
        f"Voici ses rappels prévus aujourd'hui :\n{reminders_text}\n\n"
        "Génère un message de début d'après-midi motivant avec 3 priorités claires pour la journée. "
        "Base-toi sur ses notes et rappels. Sois concis, structuré et énergisant."
    )
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system="Tu es Mnemo, assistant de mémoire personnel, chaleureux et bienveillant. Tu parles en français.",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text

# ── Jobs schedulés ────────────────────────────────────────────────────────────
def check_reminders():
    due = get_due_reminders()
    for reminder_id, chat_id, message in due:
        send_message(chat_id, f"⏰ *Rappel Mnemo :*\n{message}")
        mark_sent(reminder_id)

def send_evening_review():
    users = get_all_active_users()
    for chat_id in users:
        memos = get_today_memos(chat_id)
        reminders_tomorrow = get_tomorrow_reminders(chat_id)
        review = generate_evening_review(memos, reminders_tomorrow)
        send_message(chat_id, f"🌙 *Bilan de ta journée — Mnemo*\n\n{review}")

def send_morning_priorities():
    users = get_all_active_users()
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    today = datetime.now().strftime("%Y-%m-%d")
    for chat_id in users:
        # mémos d'hier
        conn = sqlite3.connect("mnemo.db")
        c = conn.cursor()
        c.execute("SELECT content FROM memos WHERE chat_id = ? AND created_at LIKE ?",
                  (chat_id, f"{yesterday}%"))
        memos_yesterday = [r[0] for r in c.fetchall()]
        # rappels d'aujourd'hui
        c.execute("SELECT message, remind_at FROM reminders WHERE chat_id = ? AND remind_at LIKE ? AND sent = 0",
                  (chat_id, f"{today}%"))
        reminders_today = c.fetchall()
        conn.close()

        priorities = generate_morning_priorities(memos_yesterday, reminders_today)
        send_message(chat_id, f"☀️ *Priorités du jour — Mnemo*\n\n{priorities}")

# ── Main loop ─────────────────────────────────────────────────────────────────
def main():
    init_db()

    scheduler = BackgroundScheduler()
    scheduler.add_job(check_reminders, 'interval', minutes=1)
    scheduler.add_job(send_evening_review, 'cron', hour=20, minute=0)
    scheduler.add_job(send_morning_priorities, 'cron', hour=13, minute=0)
    scheduler.start()

    offset = None
    print("Mnemo bot started!")

    while True:
        updates = get_updates(offset)
        for update in updates.get("result", []):
            offset = update["update_id"] + 1
            msg = update.get("message", {})
            chat_id = msg.get("chat", {}).get("id")
            text = msg.get("text", "")

            if not chat_id or not text:
                continue

            # Enregistrer l'utilisateur actif
            register_user(chat_id)

            # /start
            if text == "/start":
                send_message(chat_id,
                    "👋 Bonjour ! Je suis *Mnemo*, ton assistant de mémoire.\n\n"
                    "📝 `/memo [texte]` — Sauvegarde une pensée\n"
                    "⏰ `/rappel [date] [message]` — Crée un vrai rappel\n"
                    "🔍 `/recherche [mot]` — Trouve tes mémos\n"
                    "📋 `/liste` — Affiche tous tes mémos\n"
                    "❓ `/aide` — Voir toutes les options\n\n"
                    "_Tu recevras un bilan à 20h et tes priorités à 13h chaque jour_ 🌙☀️")
                continue

            # /memo
            if text.lower().startswith("/memo"):
                content = text[5:].strip()
                if content:
                    save_memo(chat_id, content)
                    send_message(chat_id, f"✅ *Mémo enregistré !*\n_{content}_")
                else:
                    send_message(chat_id, "Écris quelque chose après `/memo` 😊")
                continue

            # /rappel
            if text.lower().startswith("/rappel"):
                content = text[7:].strip()
                remind_at, reminder_msg = parse_reminder(content)
                if remind_at:
                    save_reminder(chat_id, reminder_msg, remind_at)
                    send_message(chat_id,
                        f"✅ *Rappel enregistré !*\n📅 {remind_at}\n💬 {reminder_msg}")
                else:
                    send_message(chat_id,
                        "❌ Je n'ai pas compris la date. Essaie :\n"
                        "`/rappel demain 9h Appel client`\n"
                        "`/rappel 18 juin 14h30 RDV médecin`\n"
                        "`/rappel dans 2 heures prendre médicament`")
                continue

            # /aide
            if text == "/aide":
                send_message(chat_id,
                    "🧠 *Commandes Mnemo :*\n\n"
                    "📝 `/memo [texte]` — Sauvegarde une pensée\n"
                    "⏰ `/rappel [date] [message]` — Crée un rappel\n"
                    "🔍 `/recherche [mot]` — Trouve tes mémos\n"
                    "📋 `/liste` — Affiche tous tes mémos\n\n"
                    "_Bilan automatique à 20h · Priorités à 13h_ 🌙☀️")
                continue

            # Conversation libre → Claude
            reply = ask_mnemo(text)
            send_message(chat_id, reply)

if __name__ == "__main__":
    main()

