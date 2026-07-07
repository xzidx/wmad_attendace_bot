import os
import logging
from datetime import datetime, timedelta
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz
from students import STUDENTS

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PORT = int(os.environ.get("PORT", 10000))

CAMBODIA_TZ = pytz.timezone("Asia/Phnom_Penh")
attendance = {}           # {date: {student_id: "Come" / "Late" / "A"}}
session_start_time = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

application = Application.builder().token(TOKEN).build()

def get_today_date():
    return datetime.now(CAMBODIA_TZ).date()

def get_student_by_id(student_id):
    for s in STUDENTS:
        if s["id"] == student_id:
            return s
    return None

def create_attendance_keyboard():
    keyboard = []
    for student in STUDENTS:
        text = f"{student['id']} - {student['name']}"
        callback_data = f"choose_{student['id']}"
        keyboard.append([InlineKeyboardButton(text, callback_data=callback_data)])
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global session_start_time
    
    today = get_today_date()
    if today not in attendance:
        attendance[today] = {}
    
    session_start_time = datetime.now(CAMBODIA_TZ)
    
    keyboard = create_attendance_keyboard()
    text = (
        "📋 *Attendance Started!*\n\n"
        "Students, please tap your name below.\n"
        "You can choose **Come** or **Late**.\n\n"
        "⏰ After 20 minutes, remaining students will be marked as **A**.\n\n"
        f"📅 Date: {today}"
    )
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")
    
    # Schedule auto-mark after 20 minutes
    scheduler = AsyncIOScheduler(timezone=CAMBODIA_TZ)
    scheduler.add_job(
        auto_mark_absent,
        trigger="date",
        run_date=session_start_time + timedelta(minutes=20),
        args=[update.get_bot()]
    )
    scheduler.start()

async def choose_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    student_id = query.data.replace("choose_", "")
    student = get_student_by_id(student_id)
    
    if not student:
        await query.edit_message_text("❌ Student not found.")
        return
    
    today = get_today_date()
    if today not in attendance:
        attendance[today] = {}
    
    # Show Come / Late buttons
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Come", callback_data=f"mark_{student_id}_Come")],
        [InlineKeyboardButton("⏰ Late", callback_data=f"mark_{student_id}_Late")]
    ])
    
    await query.edit_message_text(
        f"Select your status for:\n{student['id']} - {student['name']}",
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
    
    if today not in attendance:
        attendance[today] = {}
    
    attendance[today][student_id] = status
    
    status_text = "✅ Come" if status == "Come" else "⏰ Late"
    await query.edit_message_text(
        f"✅ Thank you!\n\n{student['id']} - {student['name']}\nStatus: {status_text}"
    )

async def auto_mark_absent(bot):
    today = get_today_date()
    if today not in attendance:
        attendance[today] = {}
    
    marked = 0
    for student in STUDENTS:
        sid = student["id"]
        if sid not in attendance[today]:
            attendance[today][sid] = "A"
            marked += 1
    
    logger.info(f"Auto-marked {marked} students as A after 20 minutes")

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = get_today_date()
    if today not in attendance:
        attendance[today] = {}
    
    come_list = []
    late_list = []
    absent_list = []
    
    for student in STUDENTS:
        sid = student["id"]
        status = attendance[today].get(sid, "A")
        line = f"{sid} - {student['name']}"
        
        if status == "Come":
            come_list.append(line)
        elif status == "Late":
            late_list.append(line)
        else:
            absent_list.append(line)
    
    text = f"📋 *Attendance Report - {today}*\n\n"
    
    if come_list:
        text += "✅ *Come:*\n" + "\n".join(come_list) + "\n\n"
    if late_list:
        text += "⏰ *Late:*\n" + "\n".join(late_list) + "\n\n"
    if absent_list:
        text += "❌ *Absent (A):*\n" + "\n".join(absent_list) + "\n\n"
    
    text += f"Total Come: {len(come_list)} | Late: {len(late_list)} | Absent: {len(absent_list)}"
    
    await update.message.reply_text(text, parse_mode="Markdown")

# Handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("report", report))
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

async def setup_webhook():
    await application.initialize()
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/{TOKEN}"
    await application.bot.set_webhook(webhook_url)
    logger.info(f"Webhook set: {webhook_url}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(setup_webhook())
    app.run(host="0.0.0.0", port=PORT)
