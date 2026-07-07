import os
import logging
from datetime import datetime
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import pytz
from students import STUDENTS

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PORT = int(os.environ.get("PORT", 10000))

CAMBODIA_TZ = pytz.timezone("Asia/Phnom_Penh")
attendance = {}
main_message = {}

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

application = Application.builder().token(TOKEN).build()


def get_today_date():
    return datetime.now(CAMBODIA_TZ).date()


def get_student_by_id(student_id):
    for s in STUDENTS:
        if s["id"] == student_id:
            return s
    return None


def create_keyboard(chat_id):
    keyboard = []
    today = get_today_date()
    
    for student in STUDENTS:
        sid = student["id"]
        name = student["name"]
        status = attendance.get(today, {}).get(sid)
        
        if status == "Come":
            text = f"✅ {sid} - {name}"
        elif status == "Late":
            text = f"⏰ {sid} - {name}"
        else:
            text = f"{sid} - {name}"
        
        keyboard.append([InlineKeyboardButton(text, callback_data=f"choose_{sid}")])
    
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = get_today_date()
    if today not in attendance:
        attendance[today] = {}
    
    chat_id = update.effective_chat.id
    
    keyboard = create_keyboard(chat_id)
    text = (
        "📋 *Attendance Started!*\n\n"
        "Students, please tap your name.\n"
        "Choose **Come** or **Late**.\n\n"
        f"📅 Date: {today}"
    )
    
    msg = await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
    main_message[chat_id] = msg.message_id


async def choose_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    student_id = query.data.replace("choose_", "")
    student = get_student_by_id(student_id)
    
    if not student:
        return await query.edit_message_text("❌ Not found")
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Come", callback_data=f"mark_{student_id}_Come")],
        [InlineKeyboardButton("⏰ Late", callback_data=f"mark_{student_id}_Late")]
    ])
    
    await query.edit_message_text(
        f"Select status:\n{student['id']} - {student['name']}",
        reply_markup=keyboard
    )


async def mark_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data.replace("mark_", "").split("_")
    student_id = data[0]
    status = data[1]
    
    student = get_student_by_id(student_id)
    today = get_today_date()
    chat_id = query.message.chat.id
    
    if today not in attendance:
        attendance[today] = {}
    attendance[today][student_id] = status
    
    # Update the main attendance list
    if chat_id in main_message:
        try:
            keyboard = create_keyboard(chat_id)
            await context.bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=main_message[chat_id],
                reply_markup=keyboard
            )
        except:
            pass
    
    # Edit the selection message to a short confirmation (no deletion)
    status_text = "✅ Come" if status == "Come" else "⏰ Late"
    await query.edit_message_text(
        f"✅ Marked as {status_text}\n{student['id']} - {student['name']}"
    )


async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = get_today_date()
    if today not in attendance:
        attendance[today] = {}
    
    come, late, absent = [], [], []
    
    for s in STUDENTS:
        sid = s["id"]
        status = attendance[today].get(sid, "A")
        line = f"{sid} - {s['name']}"
        
        if status == "Come": come.append(line)
        elif status == "Late": late.append(line)
        else: absent.append(line)
    
    text = f"📋 *Attendance Report - {today}*\n\n"
    if come: text += "✅ *Come:*\n" + "\n".join(come) + "\n\n"
    if late: text += "⏰ *Late:*\n" + "\n".join(late) + "\n\n"
    if absent: text += "❌ *Absent (A):*\n" + "\n".join(absent) + "\n\n"
    text += f"Come: {len(come)} | Late: {len(late)} | Absent: {len(absent)}"
    
    await update.message.reply_text(text, parse_mode="Markdown")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = get_today_date()
    chat_id = update.effective_chat.id
    
    if today in attendance:
        attendance[today] = {}
    if chat_id in main_message:
        del main_message[chat_id]
    
    await update.message.reply_text(
        "✅ Attendance has been reset.\n\n"
        "Type /start to begin a new session."
    )


# Handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("report", report))
application.add_handler(CommandHandler("reset", reset))
application.add_handler(CallbackQueryHandler(choose_status, pattern="^choose_"))
application.add_handler(CallbackQueryHandler(mark_status, pattern="^mark_"))


# Flask Webhook
app = Flask(__name__)

@app.route("/")
def home():
    return "Attendance Bot is running!"

@app.route(f"/{TOKEN}", methods=["POST"])
async def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    await application.process_update(update)
    return "ok"


async def setup():
    await application.initialize()
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/{TOKEN}"
    await application.bot.set_webhook(webhook_url)


if __name__ == "__main__":
    import asyncio
    asyncio.run(setup())
    app.run(host="0.0.0.0", port=PORT)
