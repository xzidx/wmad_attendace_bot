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
main_message = {}  # chat_id -> message_id (only ONE message per chat)

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


def build_main_text():
    """Build the main attendance text with summary counts."""
    today = get_today_date()
    day_data = attendance.get(today, {})

    come_count = sum(1 for v in day_data.values() if v == "Come")
    late_count = sum(1 for v in day_data.values() if v == "Late")
    total = len(STUDENTS)
    absent_count = total - come_count - late_count

    text = (
        f"📋 *Attendance — {today}*\n\n"
        f"Tap your name → choose *Come* or *Late*.\n\n"
        f"✅ Come: {come_count}  |  ⏰ Late: {late_count}  |  ❌ Absent: {absent_count}"
    )
    return text


def create_keyboard():
    """Build the student list keyboard with status icons."""
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
            text = f"⬜ {sid} - {name}"

        keyboard.append([InlineKeyboardButton(text, callback_data=f"choose_{sid}")])

    return InlineKeyboardMarkup(keyboard)


async def update_main_message(context, chat_id):
    """Edit the ONE main message in-place. If it fails, do nothing."""
    if chat_id not in main_message:
        return
    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=main_message[chat_id],
            text=build_main_text(),
            reply_markup=create_keyboard(),
            parse_mode="Markdown"
        )
    except Exception:
        pass  # message unchanged or deleted — ignore


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = get_today_date()
    if today not in attendance:
        attendance[today] = {}

    chat_id = update.effective_chat.id

    # Delete the old main message if it exists (keep chat clean)
    if chat_id in main_message:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=main_message[chat_id])
        except Exception:
            pass

    # Send ONE main message and store its ID
    msg = await update.message.reply_text(
        build_main_text(),
        reply_markup=create_keyboard(),
        parse_mode="Markdown"
    )
    main_message[chat_id] = msg.message_id


async def choose_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    student_id = query.data.replace("choose_", "")
    student = get_student_by_id(student_id)

    if not student:
        await query.answer("❌ Student not found", show_alert=True)
        return

    # Show Come / Late buttons — edit the SAME main message (no new message)
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Come", callback_data=f"mark_{student_id}_Come"),
            InlineKeyboardButton("⏰ Late", callback_data=f"mark_{student_id}_Late"),
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="back_to_list")],
    ])

    try:
        await query.edit_message_text(
            f"Select status for:\n*{student['id']} — {student['name']}*",
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    except Exception:
        pass


async def mark_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    data = query.data.replace("mark_", "").split("_")
    student_id = data[0]
    status = data[1]

    student = get_student_by_id(student_id)
    if not student:
        await query.answer("❌ Student not found", show_alert=True)
        return

    today = get_today_date()
    chat_id = query.message.chat.id

    if today not in attendance:
        attendance[today] = {}
    attendance[today][student_id] = status

    # Show a small popup confirmation (no new message!)
    emoji = "✅" if status == "Come" else "⏰"
    await query.answer(f"{emoji} {student['name']} marked as {status}", show_alert=False)

    # Go straight back to the updated main list (edit in-place)
    try:
        await query.edit_message_text(
            build_main_text(),
            reply_markup=create_keyboard(),
            parse_mode="Markdown"
        )
        # Keep tracking this as the main message
        main_message[chat_id] = query.message.message_id
    except Exception:
        pass


async def back_to_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the Back button — return to the main list."""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id

    try:
        await query.edit_message_text(
            build_main_text(),
            reply_markup=create_keyboard(),
            parse_mode="Markdown"
        )
        main_message[chat_id] = query.message.message_id
    except Exception:
        pass


async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = get_today_date()
    if today not in attendance:
        attendance[today] = {}

    come, late, absent = [], [], []

    for s in STUDENTS:
        sid = s["id"]
        status = attendance[today].get(sid, "A")
        line = f"{sid} - {s['name']}"

        if status == "Come":
            come.append(line)
        elif status == "Late":
            late.append(line)
        else:
            absent.append(line)

    text = f"📋 *Attendance Report — {today}*\n\n"
    if come:
        text += "✅ *Come:*\n" + "\n".join(come) + "\n\n"
    if late:
        text += "⏰ *Late:*\n" + "\n".join(late) + "\n\n"
    if absent:
        text += "❌ *Absent:*\n" + "\n".join(absent) + "\n\n"
    text += f"*Come: {len(come)} | Late: {len(late)} | Absent: {len(absent)}*"

    await update.message.reply_text(text, parse_mode="Markdown")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = get_today_date()
    chat_id = update.effective_chat.id

    if today in attendance:
        attendance[today] = {}

    # Delete old main message
    if chat_id in main_message:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=main_message[chat_id])
        except Exception:
            pass
        del main_message[chat_id]

    await update.message.reply_text(
        "✅ Attendance has been reset.\n\nType /start to begin a new session."
    )


# Handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("report", report))
application.add_handler(CommandHandler("reset", reset))
application.add_handler(CallbackQueryHandler(back_to_list, pattern="^back_to_list$"))
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
