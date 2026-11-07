import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from app.parsing.jobs import (
    MAX_TEXT_CHARS,
    JobKind,
    ParsedAttachment,
    ParserJob,
    ParserResult,
)
from app.sandbox.email_text import extract_email_content
from app.sandbox.pdf import PdfLockedError, pdf_to_markdown, unlock_pdf
from app.sandbox.settings import ParserSettings


def _process_pdf(
    filename: str,
    data: bytes,
    pdf_passwords: Sequence[str],
    to_markdown: Callable[[bytes], str],
    max_pdf_bytes: int,
) -> ParsedAttachment:
    if len(data) > max_pdf_bytes:
        return ParsedAttachment(filename=filename, error="too_large")
    try:
        unlocked = unlock_pdf(data, pdf_passwords)
    except PdfLockedError:
        return ParsedAttachment(filename=filename, error="pdf_locked")
    except Exception:
        return ParsedAttachment(filename=filename, error="pdf_error")

    try:
        md = to_markdown(unlocked)
        return ParsedAttachment(filename=filename, markdown=md)
    except Exception:
        return ParsedAttachment(filename=filename, error="pdf_error")


def run_job(
    job_dir: Path,
    *,
    pdf_passwords: Sequence[str] = (),
    to_markdown: Callable[[bytes], str] = pdf_to_markdown,
    max_pdf_bytes: int = 10_000_000,
) -> ParserResult:
    job_id = job_dir.name
    job_file = job_dir / "job.json"
    if not job_file.is_file():
        return ParserResult(job_id=job_id, ok=False, error="bad_job")

    try:
        raw_json = job_file.read_text(encoding="utf-8")
        job = ParserJob.model_validate_json(raw_json)
        job_id = job.job_id
    except Exception:
        return ParserResult(job_id=job_id, ok=False, error="bad_job")

    try:
        if job.kind == JobKind.PDF:
            attachments: list[ParsedAttachment] = []
            for file in job.files:
                file_path = job_dir / file
                if not file_path.is_file():
                    attachments.append(ParsedAttachment(filename=file, error="pdf_error"))
                    continue
                data = file_path.read_bytes()
                attachments.append(
                    _process_pdf(file, data, pdf_passwords, to_markdown, max_pdf_bytes)
                )
            return ParserResult(job_id=job.job_id, ok=True, text=None, attachments=attachments)

        if job.kind == JobKind.EMAIL:
            if not job.files:
                return ParserResult(job_id=job.job_id, ok=False, error="bad_job")
            file_path = job_dir / job.files[0]
            if not file_path.is_file():
                return ParserResult(job_id=job.job_id, ok=False, error="parse_error")
            content = extract_email_content(file_path.read_bytes())
            text = content.text[:MAX_TEXT_CHARS]
            attachments = [
                _process_pdf(fname, pdata, pdf_passwords, to_markdown, max_pdf_bytes)
                for fname, pdata in content.pdfs
            ]
            return ParserResult(
                job_id=job.job_id,
                ok=True,
                text=text,
                attachments=attachments,
            )

        return ParserResult(job_id=job.job_id, ok=False, error="bad_job")
    except Exception:
        return ParserResult(job_id=job_id, ok=False, error="parse_error")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    settings = ParserSettings()
    result = run_job(
        Path(sys.argv[1]),
        pdf_passwords=settings.pdf_passwords,
        max_pdf_bytes=settings.max_pdf_bytes,
    )
    print(result.model_dump_json())
