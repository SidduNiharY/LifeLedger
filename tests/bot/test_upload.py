from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from pydantic import SecretStr
from telegram.ext import MessageHandler

from app.bot.actions import pdf_upload_problem, queue_pdf_upload
from app.bot.main import build_application
from app.core.config import Settings
from app.parsing.jobs import JobKind, ParserJob


def test_pdf_upload_problem():
    assert pdf_upload_problem("image/png", 100, 10_000_000) == "Please send the bill as a PDF."
    assert (
        pdf_upload_problem("application/pdf", 20_000_000, 10_000_000)
        == "That PDF is too large (max 10 MB)."
    )
    assert pdf_upload_problem("application/pdf", 100, 10_000_000) is None


async def test_queue_pdf_upload(session, tmp_path):
    now = datetime(2026, 11, 6, 4, 0, tzinfo=UTC)
    assert (
        await queue_pdf_upload(session, tmp_path, file_unique_id="AgAD1", data=b"%PDF", now=now)
        == "📥 Got it, reading the PDF…"
    )
    assert (
        await queue_pdf_upload(session, tmp_path, file_unique_id="AgAD1", data=b"%PDF", now=now)
        == "I already have that file."
    )
    [job_dir] = list(tmp_path.iterdir())
    assert ParserJob.model_validate_json((job_dir / "job.json").read_text()).kind is JobKind.PDF


async def test_handle_document_flow(sessionmaker, tmp_path):
    settings = Settings(
        database_url="postgresql+asyncpg://user:pass@localhost/db",
        telegram_bot_token=SecretStr("123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"),
        telegram_owner_chat_id=12345,
        inbox_dir=tmp_path,
    )
    app = build_application(settings, sessionmaker)
    doc_handler = [h for h in app.handlers[0] if isinstance(h, MessageHandler)][0]
    ctx = MagicMock()
    ctx.args = []

    # 1. Non-pdf document
    update_non_pdf = MagicMock()
    update_non_pdf.effective_chat.id = 12345
    update_non_pdf.effective_message.document.mime_type = "image/png"
    update_non_pdf.effective_message.document.file_size = 100
    update_non_pdf.effective_message.reply_text = AsyncMock()
    await doc_handler.callback(update_non_pdf, ctx)
    update_non_pdf.effective_message.reply_text.assert_awaited_once_with(
        "Please send the bill as a PDF."
    )

    # 2. Valid PDF
    update_pdf = MagicMock()
    update_pdf.effective_chat.id = 12345
    update_pdf.effective_message.document.mime_type = "application/pdf"
    update_pdf.effective_message.document.file_size = 100
    update_pdf.effective_message.document.file_unique_id = "uniq_1"
    mock_file = MagicMock()
    mock_file.download_as_bytearray = AsyncMock(return_value=bytearray(b"%PDF"))
    update_pdf.effective_message.document.get_file = AsyncMock(return_value=mock_file)
    update_pdf.effective_message.reply_text = AsyncMock()
    await doc_handler.callback(update_pdf, ctx)
    update_pdf.effective_message.reply_text.assert_awaited_once_with("📥 Got it, reading the PDF…")
