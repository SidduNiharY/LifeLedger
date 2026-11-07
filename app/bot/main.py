import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from app.bot.actions import (
    answer_category,
    fix_message,
    owner_only,
    recent_reply,
    review_messages,
    spend_reply,
)
from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_sessionmaker
from app.core.logging import setup_logging
from app.core.timeutil import local_date
from app.notify.telegram import to_markup

logger = logging.getLogger(__name__)


def build_application(
    settings: Settings,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> Application:
    owner_id = settings.telegram_owner_chat_id
    if owner_id is None:
        raise ValueError("telegram_owner_chat_id is required")
    guard = owner_only(owner_id)

    token = settings.telegram_bot_token.get_secret_value() if settings.telegram_bot_token else ""
    app = Application.builder().token(token).build()

    async def handle_spend(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        arg = context.args[0] if context.args else None
        today = local_date(datetime.now(UTC), settings.timezone)
        async with sessionmaker() as session:
            async with session.begin():
                reply = await spend_reply(session, arg, today)
        if update.effective_message:
            await update.effective_message.reply_text(reply)

    async def handle_recent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        async with sessionmaker() as session:
            async with session.begin():
                reply = await recent_reply(session)
        if update.effective_message:
            await update.effective_message.reply_text(reply)

    async def handle_review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        async with sessionmaker() as session:
            async with session.begin():
                messages = await review_messages(session)
        if update.effective_message:
            for msg in messages:
                await update.effective_message.reply_text(
                    text=msg.text,
                    reply_markup=to_markup(msg.keyboard),
                )

    async def handle_fix(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        arg = context.args[0] if context.args else ""
        async with sessionmaker() as session:
            async with session.begin():
                msg = await fix_message(session, arg)
        if update.effective_message:
            await update.effective_message.reply_text(
                text=msg.text,
                reply_markup=to_markup(msg.keyboard),
            )

    async def handle_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query:
            return
        await query.answer()
        data = query.data or ""
        async with sessionmaker() as session:
            async with session.begin():
                answer_text = await answer_category(session, data)
        await query.edit_message_text(text=answer_text)

    app.add_handler(CommandHandler("spend", guard(handle_spend)))
    app.add_handler(CommandHandler("recent", guard(handle_recent)))
    app.add_handler(CommandHandler("review", guard(handle_review)))
    app.add_handler(CommandHandler("fix", guard(handle_fix)))
    app.add_handler(CallbackQueryHandler(guard(handle_category_callback), pattern=r"^cat:"))

    return app


def main() -> None:
    settings = get_settings()
    settings.require("telegram_bot_token", "telegram_owner_chat_id", "database_url")
    setup_logging()

    engine = make_engine(settings.database_url)
    sessionmaker = make_sessionmaker(engine)

    app = build_application(settings, sessionmaker)
    logger.info("Starting Telegram bot polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
