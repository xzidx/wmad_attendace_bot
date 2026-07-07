import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
from students import STUDENTS

# ==================== CONFIG ====================
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # Set this on Render

# Cambodia timezone
CAMBODIA_TZ = pytz.timezone("Asia/Phnom_Penh")

# Store attendance (in-memory for simplicity)
attendance = {}  # {date: {student_id: "Present" or "A"}}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def get_today_date():
    """Get today's date in Cambodia time"""
    return datetime.now(CAMBODIA_TZ).date()


def get_student_by_id(student_id):
    for s in STUDENTS:
        if s["id"] == student_id:
            return s
    return None


def create_attendance_keyboard():
    """Create inline keyboard with all student names"""
    keyboard = []
    row = []

    for i, student in enumerate(STUDENTS):
        text = f"{student['id']} - {student['name']}"
        callback_data = f"mark_{student['id']}"

        row.append(InlineKeyboardButton(text, callback_data=callback_data))

        # 1 button per row (easier for students)
        keyboard.append([row[-1]])
        row = []

    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command - shows the attendance buttons"""
    chat_id = update.effective_chat.id
    today = get_today_date()

    # Initialize today's attendance if not exists
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
    """Handle when student taps their name"""
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

    # Mark as present
    attendance[today][student_id] = "Present"

    name = student["name"]
    await query.edit_message_text(
        f"✅ Thank you! You have been marked as **Present**.\n\n"
        f"Name: {name}\n"
        f"ID: {student_id}",
        parse_mode="Markdown"
    )

    logger.info(f"{student_id} - {name} marked as Present")


async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send attendance report to teacher"""
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

    # Format the report
    report_text = f"📋 *Attendance Report - {today}*\n\n"

    if present_list:
        report_text += "✅ *Present:*\n"
        report_text += "\n".join(present_list) + "\n\n"

    if absent_list:
        report_text += "❌ *Absent (A):*\n"
        report_text += "\n".join(absent_list) + "\n\n"

    report_text += f"Total Present: {len(present_list)}/23\n"
    report_text += f"Total Absent: {len(absent_list)}/23"

    await update.message.reply_text(report_text, parse_mode="Markdown")


async def auto_mark_absent(context: ContextTypes.DEFAULT_TYPE):
    """Automatically mark students who didn't respond as Absent at 7:20 AM"""
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


async def post_init(application: Application):
    """Start the scheduler after the bot is initialized"""
    scheduler = AsyncIOScheduler(timezone=CAMBODIA_TZ)

    scheduler.add_job(
        auto_mark_absent,
        trigger=CronTrigger(hour=7, minute=20, timezone=CAMBODIA_TZ),
        args=[application]
    )

    scheduler.start()
    logger.info("Scheduler started - will mark absent at 7:20 AM Cambodia time")


def main():
    if not TOKEN:
        print("❌ Error: TELEGRAM_BOT_TOKEN environment variable not set!")
        return

    application = Application.builder().token(TOKEN).post_init(post_init).build()

    # Commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("report", report))
    application.add_handler(CallbackQueryHandler(mark_attendance))

    print("✅ Attendance Bot is running...")
    application.run_polling()


if __name__ == "__main__":
    main()
