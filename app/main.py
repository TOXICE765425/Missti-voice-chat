import logging
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup,
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters,
)
from .config import BOT_TOKEN, BOT_USERNAME, OWNER_IDS, SUPPORT_LINK, WAKE_WORD
from .database import save_user, save_event, initialize_firebase
from .ai_engine import ask_ai
from .voice_chat import join_voice_chat, leave_voice_chat
from .keep_alive import start_health_server

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("missti")

def main_menu():
    add_url = (
        f"https://t.me/{BOT_USERNAME}?startgroup=true"
        if BOT_USERNAME else "https://t.me/"
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
        "/start — Open welcome menu\n"
        "/help — Show commands\n"
        "/join — Voice-chat setup/status\n"
        "/leave — Leave voice chat (when voice engine is enabled)\n"
        "/status — Show bot status\n\n"
        f"Wake word: {WAKE_WORD}\n"
        "Voice chat audio automation is not enabled in this starter build."
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user:
        save_user(user)
    caption = (
        f"Welcome, {user.first_name if user else 'there'}! ❤️\n\n"
        "I am Missti.\n\n"
        "Telegram Voice Chat Assistant."
    )
    # Telegram Bot API can fetch the user's profile photo, but sending that
    # photo as the bot's welcome image is intentionally best-effort.
    if user:
        try:
            photos = await context.bot.get_user_profile_photos(user.id, limit=1)
            if photos.total_count:
                file_id = photos.photos[0][-1].file_id
                await update.effective_message.reply_photo(
                    photo=file_id, caption=caption, reply_markup=main_menu()
                )
                return
        except Exception as exc:
            log.info("Could not fetch user's profile photo: %s", exc)
    await update.effective_message.reply_text(caption, reply_markup=main_menu())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(help_text())

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "Missti is online.\nVoice-chat audio engine: not enabled in this starter build."
    )

async def join_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat or chat.type == "private":
        await update.effective_message.reply_text(
            "Pehle mujhe group mein add karo, phir group ke voice chat mein /join use karo."
        )
        return
    ok, message = await join_voice_chat(chat.id)
    await update.effective_message.reply_text(message)

async def leave_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat:
        return
    ok, message = await leave_voice_chat(chat.id)
    await update.effective_message.reply_text(message)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "help":
        await query.message.reply_text(help_text())
    elif query.data == "boss":
        if not OWNER_IDS:
            await query.message.reply_text("Owner list abhi configure nahi hai.")
            return
        rows = []
        for index, owner_id in enumerate(OWNER_IDS, start=1):
            rows.append([InlineKeyboardButton(
                f"👑 Owner {index} · {owner_id}",
                url=f"tg://user?id={owner_id}",
            )])
        await query.message.reply_text(
            "Missti Owners:", reply_markup=InlineKeyboardMarkup(rows)
        )

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Text chat AI is available in private chats. Group text is answered only
    # when the wake word is explicitly present.
    message = update.effective_message
    if not message or not message.text:
        return
    text = message.text.strip()
    is_private = update.effective_chat.type == "private"
    if not is_private and WAKE_WORD.casefold() not in text.casefold():
        return
    prompt = text
    if not is_private:
        prompt = text.replace(WAKE_WORD, "", 1).strip(" ,:;")
        if not prompt:
            await message.reply_text("Haan, bolo! ❤️")
            return
    await message.reply_text("💭 Soch rahi hoon...")
    answer = ask_ai(prompt)
    await message.reply_text(answer)

async def post_init(application: Application):
    initialize_firebase()
    log.info("Missti bot initialized.")

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is required.")
    start_health_server()
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
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
