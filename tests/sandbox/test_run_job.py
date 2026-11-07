from app.parsing.jobs import MAX_TEXT_CHARS, JobKind, ParserJob, write_job
from app.sandbox.run_job import run_job
from tests.sandbox.test_email_text import eml


def test_email_job_returns_text(tmp_path):
    d = write_job(
        tmp_path,
        ParserJob(job_id="7", kind=JobKind.EMAIL, files=["message.eml"]),
        {"message.eml": eml(plain="Rs.450.00 debited")},
    )
    r = run_job(d)
    assert r.ok and r.job_id == "7" and "Rs.450.00 debited" in r.text


def test_text_is_capped(tmp_path):
    d = write_job(
        tmp_path,
        ParserJob(job_id="8", kind=JobKind.EMAIL, files=["message.eml"]),
        {"message.eml": eml(plain="a" * 30_000)},
    )
    assert len(run_job(d).text) == MAX_TEXT_CHARS


def test_bad_job_json(tmp_path):
    (tmp_path / "9").mkdir()
    (tmp_path / "9" / "job.json").write_text('{"job_id":"9","kind":"email","files":["../x"]}')
    assert (run_job(tmp_path / "9").ok, run_job(tmp_path / "9").error) == (False, "bad_job")
