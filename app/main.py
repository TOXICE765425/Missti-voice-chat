import logging
import asyncio
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from .config import BOT_TOKEN, OWNER_IDS, SUPPORT_LINK, WAKE_WORD
from .database import save_user, save_event, initialize_firebase
from .ai_engine import ask_ai
from .voice_chat import join_voice_chat, leave_voice_chat, voice_status, shutdown_voice
from .keep_alive import start_health_server

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("missti")


def main_menu(bot_username: str = ""):
    add_url = (
        f"https://t.me/{bot_username}?startgroup=true"
        if bot_username
        else "https://t.me/"
    )
    keyboard = [
        [InlineKeyboardButton("➕ Add To Your Group", url=add_url)],
        [InlineKeyboardButton("📚 Help & Commands", callback_data="help")],
        [InlineKeyboardButton("💬 Support", url=SUPPORT_LINK)],
        [InlineKeyboardButton("👑 Boss", callback_data="boss")],
    ]
    return InlineKeyboardMarkup(keyboard)


def help_text():
    return (
        "🤖 Missti — Telegram Voice Chat Assistant\n\n"
        "/start — Welcome menu\n"
        "/help — Commands\n"
        "/status — Bot status\n"
        "/join — Join this group's active voice chat\n"
        "/leave — Leave the voice chat\n\n"
        f"Wake word: {WAKE_WORD}\n"
        "Voice processing only after /join.\n"
        "Group members ko inform kar lena."
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user:
        save_user(user)

    caption = (
        f"Welcome, {user.first_name if user else 'there'}! ❤️\n\n"
        "I am Missti.\n\nTelegram Voice Chat Assistant."
    )

    bot_username = (context.bot.username or "").lstrip("@")
    markup = main_menu(bot_username)

    if user:
        try:
            photos = await context.bot.get_user_profile_photos(user.id, limit=1)
            if photos.total_count:
                file_id = photos.photos[0][-1].file_id
                await update.effective_message.reply_photo(
                    photo=file_id,
                    caption=caption,
                    reply_markup=markup,
                )
                return
        except Exception as exc:
            log.info("Could not fetch profile photo: %s", exc)

    await update.effective_message.reply_text(caption, reply_markup=markup)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(help_text())


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    active = bool(chat and chat.type != "private" and voice_status(chat.id))
    await update.effective_message.reply_text(
        "Missti is online.\n"
        f"Voice chat: {'connected' if active else 'not connected'}"
    )


async def join_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    message = update.effective_message

    if not chat or chat.type == "private":
        await message.reply_text(
            "Mujhe group mein add karke group ke active voice chat mein /join use karo."
        )
        return

    await message.reply_text(
        "ℹ️ Missti voice chat audio process karegi aur wake word par reply degi. "
        "Members ko inform/consent kara lo. Connecting..."
    )

    ok, result = await join_voice_chat(chat.id)
    await message.reply_text(result)

    if ok:
        save_event(chat.id, "voice_joined", {"wake_word": WAKE_WORD})


async def leave_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat

    if not chat or chat.type == "private":
        await update.effective_message.reply_text("Ye command group mein use karo.")
        return

    ok, result = await leave_voice_chat(chat.id)
    await update.effective_message.reply_text(result)

    if ok:
        save_event(chat.id, "voice_left")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "help":
        await query.message.reply_text(help_text())

    elif query.data == "boss":
        if not OWNER_IDS:
            await query.message.reply_text("Owner list abhi configure nahi hai.")
            return

        rows = [
            [InlineKeyboardButton(f"👑 Owner {i}", url=f"tg://user?id={uid}")]
            for i, uid in enumerate(OWNER_IDS, start=1)
        ]
        await query.message.reply_text(
            "Missti Owners:",
            reply_markup=InlineKeyboardMarkup(rows),
        )


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message or not message.text:
        return

    text = message.text.strip()
    is_private = update.effective_chat.type == "private"

    # Group me sirf wake word ke saath reply
    if not is_private and WAKE_WORD.casefold() not in text.casefold():
        return

    prompt = text
    if not is_private:
        prompt = re.sub(
            re.escape(WAKE_WORD),
            "",
            text,
            count=1,
            flags=re.IGNORECASE,
        ).strip(" ,:;")

        if not prompt:
            await message.reply_text("Haan, bolo! ❤️")
            return

    await message.reply_text("💭 Soch rahi hoon...")
    answer = await asyncio.to_thread(ask_ai, prompt)
    await message.reply_text(answer)


async def post_init(application: Application):
    initialize_firebase()
    log.info("Missti bot initialized.")


async def post_shutdown(application: Application):
    await shutdown_voice()


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is required.")

    start_health_server()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("join", join_command))
    application.add_handler(CommandHandler("leave", leave_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler)
    )

    log.info("Starting Missti AI VC bot...")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
