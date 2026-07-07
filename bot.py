import os
import logging
from datetime import datetime
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
from students import STUDENTS

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PORT = int(os.environ.get("PORT", 10000))

CAMBODIA_TZ = pytz.timezone("Asia/Phnom_Penh")
attendance = {}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
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
        callback_data = f"mark_{student['id']}"
        keyboard.append([InlineKeyboardButton(text, callback_data=callback_data)])
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = get_today_date()
    if today not in attendance:
        attendance[today] = {}
    keyboard = create_attendance_keyboard()
    text = (
        "👋 *Attendance Bot*\n\n"
        "Please tap your name below if you are present today.\n"
        "The bot will automatically mark absent students at 7:20 AM.\n\n"
        f"📅 Date: {today}"
    )
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode="Markdown")

async def mark_attendance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    student_id = query.data.replace("mark_", "")
    student = get_student_by_id(student_id)
    if not student:
        await query.edit_message_text("❌ Student not found.")
        return
    today = get_today_date()
    if today not in attendance:
        attendance[today] = {}
    attendance[today][student_id] = "Present"
    await query.edit_message_text(
        f"✅ Thank you! Marked as **Present**.\n\nName: {student['name']}\nID: {student_id}",
        parse_mode="Markdown"
    )

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = get_today_date()
    if today not in attendance:
        attendance[today] = {}
    present_list = []
    absent_list = []
    for student in STUDENTS:
        sid = student["id"]
        status = attendance[today].get(sid, "A")
        line = f"{sid} - {student['name']}"
        if status == "Present":
            present_list.append(line)
        else:
            absent_list.append(line)
    report_text = f"📋 *Attendance Report - {today}*\n\n"
    if present_list:
        report_text += "✅ *Present:*\n" + "\n".join(present_list) + "\n\n"
    if absent_list:
        report_text += "❌ *Absent (A):*\n" + "\n".join(absent_list) + "\n\n"
    report_text += f"Total Present: {len(present_list)}/23\nTotal Absent: {len(absent_list)}/23"
    await update.message.reply_text(report_text, parse_mode="Markdown")

async def auto_mark_absent(context: ContextTypes.DEFAULT_TYPE):
    today = get_today_date()
    if today not in attendance:
        attendance[today] = {}
    marked_count = 0
    for student in STUDENTS:
        sid = student["id"]
        if sid not in attendance[today]:
            attendance[today][sid] = "A"
            marked_count += 1
    logger.info(f"Auto-marked {marked_count} students as Absent for {today}")

async def post_init(app: Application):
    scheduler = AsyncIOScheduler(timezone=CAMBODIA_TZ)
    scheduler.add_job(
        auto_mark_absent,
        trigger=CronTrigger(hour=7, minute=20, timezone=CAMBODIA_TZ),
        args=[app]
    )
    scheduler.start()
    logger.info("✅ Scheduler started - Auto absent at 7:20 AM Cambodia time")

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("report", report))
application.add_handler(CallbackQueryHandler(mark_attendance))

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
    await post_init(application)
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/{TOKEN}"
    await application.bot.set_webhook(webhook_url)
    logger.info(f"✅ Webhook set to: {webhook_url}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(setup_webhook())
    app.run(host="0.0.0.0", port=PORT)
