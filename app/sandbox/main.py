import subprocess
import sys
import time
from pathlib import Path

from app.parsing.jobs import ParserResult
from app.sandbox.settings import ParserSettings


def run_with_timeout(cmd: list[str], timeout: float) -> str | None:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            return None
        return proc.stdout
    except (subprocess.TimeoutExpired, Exception):
        return None


def process_pending(
    inbox: Path,
    outbox: Path,
    timeout: float,
    runner=run_with_timeout,
) -> int:
    if not inbox.exists():
        return 0
    outbox.mkdir(parents=True, exist_ok=True)

    written = 0
    entries = sorted(
        [
            p
            for p in inbox.iterdir()
            if p.is_dir() and p.name.isdigit() and not p.name.endswith(".tmp")
        ],
        key=lambda p: int(p.name),
    )

    for entry in entries:
        job_id = entry.name
        out_file = outbox / f"{job_id}.json"
        if out_file.exists():
            continue

        output = runner(
            [sys.executable, "-m", "app.sandbox.run_job", str(entry)],
            timeout=timeout,
        )
        if output is None:
            result = ParserResult(job_id=job_id, ok=False, error="timeout")
        else:
            try:
                result = ParserResult.model_validate_json(output.strip())
            except Exception:
                result = ParserResult(job_id=job_id, ok=False, error="parse_error")

        tmp_out = outbox / f"{job_id}.json.tmp"
        tmp_out.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        tmp_out.replace(out_file)
        written += 1

    return written


def main() -> None:
    settings = ParserSettings()
    settings.inbox_dir.mkdir(parents=True, exist_ok=True)
    settings.outbox_dir.mkdir(parents=True, exist_ok=True)

    while True:
        try:
            process_pending(
                inbox=settings.inbox_dir,
                outbox=settings.outbox_dir,
                timeout=settings.job_timeout_seconds,
            )
        except Exception:
            pass
        time.sleep(settings.poll_seconds)


if __name__ == "__main__":
    main()
