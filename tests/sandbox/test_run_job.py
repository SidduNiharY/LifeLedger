from email.message import EmailMessage

from app.parsing.jobs import MAX_TEXT_CHARS, JobKind, ParsedAttachment, ParserJob, write_job
from app.sandbox.run_job import run_job
from tests.sandbox.test_email_text import eml
from tests.sandbox.test_pdf import BILL, encrypt


def email_with(pdf: bytes) -> bytes:
    m = EmailMessage()
    m["From"] = "billing@bescom.co.in"
    m.set_content("Your bill is attached.")
    m.add_attachment(pdf, maintype="application", subtype="pdf", filename="bill.pdf")
    return bytes(m)


def job(tmp_path, kind, name, data, id_="21"):
    return write_job(tmp_path, ParserJob(job_id=id_, kind=kind, files=[name]), {name: data})


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


def test_email_pdf_attachment_becomes_markdown(tmp_path):
    r = run_job(
        job(tmp_path, JobKind.EMAIL, "message.eml", email_with(BILL)), to_markdown=lambda d: "MD"
    )
    assert r.ok and r.attachments == [ParsedAttachment(filename="bill.pdf", markdown="MD")]


def test_locked_attachment_reports_pdf_locked(tmp_path):
    r = run_job(
        job(tmp_path, JobKind.EMAIL, "message.eml", email_with(encrypt(BILL, "pw"))),
        to_markdown=lambda d: "MD",
    )
    assert r.ok and r.attachments[0].error == "pdf_locked"


def test_pdf_job_and_size_limit(tmp_path):
    r = run_job(job(tmp_path, JobKind.PDF, "document.pdf", BILL), to_markdown=lambda d: "MD")
    assert (r.text, r.attachments[0].filename, r.attachments[0].markdown) == (
        None,
        "document.pdf",
        "MD",
    )
    big = run_job(
        job(tmp_path, JobKind.PDF, "document.pdf", BILL, id_="22"),
        to_markdown=lambda d: "MD",
        max_pdf_bytes=10,
    )
    assert big.attachments[0].error == "too_large"


def test_pdf_error_reports_pdf_error(tmp_path):
    def fail_markdown(d: bytes) -> str:
        raise RuntimeError("conversion failed")

    r = run_job(job(tmp_path, JobKind.PDF, "document.pdf", BILL), to_markdown=fail_markdown)
    assert r.ok and r.attachments[0].error == "pdf_error"

