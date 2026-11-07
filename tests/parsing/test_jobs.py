import pytest
from pydantic import ValidationError

from app.parsing.jobs import JobKind, ParserJob, write_job


def test_job_rejects_path_tricks():
    for bad in ["../etc/passwd", ".hidden", "a/b", ""]:
        with pytest.raises(ValidationError):
            ParserJob(job_id="7", kind=JobKind.EMAIL, files=[bad])


def test_write_job_is_atomic(tmp_path):
    d = write_job(
        tmp_path,
        ParserJob(job_id="7", kind=JobKind.EMAIL, files=["message.eml"]),
        {"message.eml": b"raw"},
    )
    assert d == tmp_path / "7" and (d / "message.eml").read_bytes() == b"raw"
    assert ParserJob.model_validate_json((d / "job.json").read_text()).files == ["message.eml"]
    assert not list(tmp_path.glob("*.tmp"))
