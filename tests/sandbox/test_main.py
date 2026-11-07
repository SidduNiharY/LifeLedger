import subprocess
import sys

from app.parsing.jobs import JobKind, ParserJob, ParserResult, write_job
from app.sandbox.main import process_pending, run_with_timeout


def test_timeout_returns_none():
    assert (
        run_with_timeout([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.5) is None
    )


def test_process_pending_writes_results_and_skips(tmp_path):
    inbox, outbox = tmp_path / "in", tmp_path / "out"
    inbox.mkdir()
    outbox.mkdir()
    write_job(inbox, ParserJob(job_id="1", kind=JobKind.EMAIL, files=["m.eml"]), {"m.eml": b"x"})
    write_job(inbox, ParserJob(job_id="2", kind=JobKind.EMAIL, files=["m.eml"]), {"m.eml": b"x"})
    (inbox / "3.tmp").mkdir()
    (outbox / "2.json").write_text(ParserResult(job_id="2", ok=True, text="done").model_dump_json())
    assert process_pending(inbox, outbox, timeout=5, runner=lambda cmd, timeout: None) == 1
    assert ParserResult.model_validate_json((outbox / "1.json").read_text()).error == "timeout"
    assert not (outbox / "3.json").exists()


def test_sandbox_does_not_load_core_settings():
    code = "import sys, app.sandbox.main; assert 'app.core.config' not in sys.modules"
    assert subprocess.run([sys.executable, "-c", code], capture_output=True).returncode == 0
