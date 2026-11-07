import sys
from pathlib import Path

from app.parsing.jobs import MAX_TEXT_CHARS, JobKind, ParserJob, ParserResult
from app.sandbox.email_text import extract_email_content


def run_job(job_dir: Path) -> ParserResult:
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
            return ParserResult(job_id=job.job_id, ok=False, error="pdf_not_supported_yet")
        if job.kind == JobKind.EMAIL:
            if not job.files:
                return ParserResult(job_id=job.job_id, ok=False, error="bad_job")
            file_path = job_dir / job.files[0]
            if not file_path.is_file():
                return ParserResult(job_id=job.job_id, ok=False, error="parse_error")
            content = extract_email_content(file_path.read_bytes())
            text = content.text[:MAX_TEXT_CHARS]
            return ParserResult(job_id=job.job_id, ok=True, text=text)
        return ParserResult(job_id=job.job_id, ok=False, error="bad_job")
    except Exception:
        return ParserResult(job_id=job_id, ok=False, error="parse_error")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    result = run_job(Path(sys.argv[1]))
    print(result.model_dump_json())
