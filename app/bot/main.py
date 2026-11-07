import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.bot.actions import (
    addbill_reply,
    addrenewal_reply,
    answer_category,
    cancelbill_reply,
    due_reply,
    fix_message,
    keywords_reply,
    owner_only,
    paid_reply,
    pdf_upload_problem,
    queue_pdf_upload,
    recent_reply,
    review_messages,
    spend_reply,
    subs_reply,
)
from app.core.config import Settings, get_settings
from app.core.db import make_engine, make_sessionmaker
from app.core.logging import setup_logging
from app.core.timeutil import local_date
from app.matching.service import answer_match
from app.notify.telegram import to_markup
from app.observability.feedback import FeedbackRecorder, LangfuseFeedback, NoopFeedback
from app.observability.tracing import setup_tracing
from app.workflows.client import BillWorkflows, TemporalBillWorkflows, connect

logger = logging.getLogger(__name__)


def build_application(
    settings: Settings,
    sessionmaker: async_sessionmaker[AsyncSession],
    workflows: BillWorkflows | None = None,
    feedback: FeedbackRecorder | None = None,
) -> Application:
    owner_id = settings.telegram_owner_chat_id
    if owner_id is None:
        raise ValueError("telegram_owner_chat_id is required")
    guard = owner_only(owner_id)

    if feedback is None:
        feedback = (
            LangfuseFeedback(settings)
            if (settings.langfuse_public_key and settings.langfuse_secret_key)
            else NoopFeedback()
        )

    workflow_holder: dict[str, BillWorkflows | None] = {"workflows": workflows}

    async def post_init(application: Application) -> None:
        if workflow_holder["workflows"] is None and settings.temporal_address:
            try:
                client = await connect(settings.temporal_address)
                workflow_holder["workflows"] = TemporalBillWorkflows(client)
                logger.info("Connected bot to Temporal at %s", settings.temporal_address)
            except Exception:
                logger.warning(
                    "Bot could not connect to Temporal at %s; bill signals disabled",
                    settings.temporal_address,
                    exc_info=True,
                )

    token = settings.telegram_bot_token.get_secret_value() if settings.telegram_bot_token else ""
    app = Application.builder().token(token).post_init(post_init).build()

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

    async def handle_subs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        today = local_date(datetime.now(UTC), settings.timezone)
        async with sessionmaker() as session:
            async with session.begin():
                reply = await subs_reply(session, today)
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

    async def handle_addbill(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        args = list(context.args or [])
        async with sessionmaker() as session:
            async with session.begin():
                reply = await addbill_reply(session, args)
        if update.effective_message:
            await update.effective_message.reply_text(reply)

    async def handle_addrenewal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        args = list(context.args or [])
        async with sessionmaker() as session:
            async with session.begin():
                reply = await addrenewal_reply(session, args)
        if update.effective_message:
            await update.effective_message.reply_text(reply)

    async def handle_due(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        today = local_date(datetime.now(UTC), settings.timezone)
        async with sessionmaker() as session:
            async with session.begin():
                reply = await due_reply(session, today)
        if update.effective_message:
            await update.effective_message.reply_text(reply)

    async def handle_paid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        arg = context.args[0] if context.args else ""
        now = datetime.now(UTC)
        async with sessionmaker() as session:
            async with session.begin():
                reply, bill_id = await paid_reply(session, arg, now)
        wf = workflow_holder["workflows"]
        if bill_id is not None and wf is not None:
            try:
                await wf.mark_paid(bill_id)
            except Exception:
                logger.exception("Failed to signal mark_paid for bill #%s", bill_id)
        if update.effective_message:
            await update.effective_message.reply_text(reply)

    async def handle_cancelbill(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        arg = context.args[0] if context.args else ""
        async with sessionmaker() as session:
            async with session.begin():
                reply, bill_id = await cancelbill_reply(session, arg)
        wf = workflow_holder["workflows"]
        if bill_id is not None and wf is not None:
            try:
                await wf.cancel(bill_id)
            except Exception:
                logger.exception("Failed to signal cancel for bill #%s", bill_id)
        if update.effective_message:
            await update.effective_message.reply_text(reply)

    async def handle_keywords(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        args = list(context.args or [])
        async with sessionmaker() as session:
            async with session.begin():
                reply = await keywords_reply(session, args)
        if update.effective_message:
            await update.effective_message.reply_text(reply)

    async def handle_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query:
            return
        await query.answer()
        data = query.data or ""
        async with sessionmaker() as session:
            async with session.begin():
                answer_text = await answer_category(session, data, feedback=feedback)
        await query.edit_message_text(text=answer_text)

    async def handle_match_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query:
            return
        await query.answer()
        data = query.data or ""
        now = datetime.now(UTC)
        async with sessionmaker() as session:
            async with session.begin():
                reply, paid_ids = await answer_match(session, data, now=now)
        wf = workflow_holder["workflows"]
        if paid_ids and wf is not None:
            for pid in paid_ids:
                try:
                    await wf.mark_paid(pid)
                except Exception:
                    logger.exception("Failed to signal mark_paid for bill #%s", pid)
        await query.edit_message_text(text=reply)

    async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_message or not update.effective_message.document:
            return
        doc = update.effective_message.document
        problem = pdf_upload_problem(doc.mime_type, doc.file_size, settings.max_upload_bytes)
        if problem is not None:
            await update.effective_message.reply_text(problem)
            return

        file = await doc.get_file()
        data = await file.download_as_bytearray()
        now = datetime.now(UTC)
        async with sessionmaker() as session:
            async with session.begin():
                reply = await queue_pdf_upload(
                    session,
                    settings.inbox_dir,
                    file_unique_id=doc.file_unique_id,
                    data=bytes(data),
                    now=now,
                )
        await update.effective_message.reply_text(reply)

    app.add_handler(CommandHandler("spend", guard(handle_spend)))
    app.add_handler(CommandHandler("recent", guard(handle_recent)))
    app.add_handler(CommandHandler("review", guard(handle_review)))
    app.add_handler(CommandHandler("fix", guard(handle_fix)))
    app.add_handler(CommandHandler("addbill", guard(handle_addbill)))
    app.add_handler(CommandHandler("addrenewal", guard(handle_addrenewal)))
    app.add_handler(CommandHandler("due", guard(handle_due)))
    app.add_handler(CommandHandler("paid", guard(handle_paid)))
    app.add_handler(CommandHandler("cancelbill", guard(handle_cancelbill)))
    app.add_handler(CommandHandler("keywords", guard(handle_keywords)))
    app.add_handler(CommandHandler("subs", guard(handle_subs)))
    app.add_handler(CallbackQueryHandler(guard(handle_category_callback), pattern=r"^cat:"))
    app.add_handler(CallbackQueryHandler(guard(handle_match_callback), pattern=r"^match:"))
    app.add_handler(MessageHandler(filters.Document.ALL, guard(handle_document)))

    return app


def main() -> None:
    settings = get_settings()
    settings.require("telegram_bot_token", "telegram_owner_chat_id", "database_url")
    setup_logging()
    setup_tracing(settings)

    engine = make_engine(settings.database_url)
    sessionmaker = make_sessionmaker(engine)

    app = build_application(settings, sessionmaker)
    logger.info("Starting Telegram bot polling...")
    app.run_polling()


if __name__ == "__main__":
    main()
