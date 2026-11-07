import shutil
from enum import StrEnum
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, Field

MAX_TEXT_CHARS = 20_000


class JobKind(StrEnum):
    EMAIL = "email"
    PDF = "pdf"


FileName = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")]


class ParserJob(BaseModel):
    job_id: str = Field(pattern=r"^\d+$")
    kind: JobKind
    files: list[FileName] = Field(min_length=1, max_length=6)


class ParsedAttachment(BaseModel):
    filename: str
    markdown: str | None = None
    error: str | None = None


class ParserResult(BaseModel):
    job_id: str
    ok: bool
    error: str | None = None
    text: str | None = None
    attachments: list[ParsedAttachment] = Field(default_factory=list)


def write_job(inbox_dir: Path, job: ParserJob, files: dict[str, bytes]) -> Path:
    inbox_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = inbox_dir / f"{job.job_id}.tmp"
    final_dir = inbox_dir / job.job_id

    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=False)

    (tmp_dir / "job.json").write_text(job.model_dump_json(indent=2), encoding="utf-8")
    for filename, content in files.items():
        (tmp_dir / filename).write_bytes(content)

    if final_dir.exists():
        shutil.rmtree(final_dir)
    tmp_dir.rename(final_dir)
    return final_dir
