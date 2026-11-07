#!/usr/bin/env bash
set -euo pipefail

JOB_ID="999999"
INBOX_JOB_DIR="data/inbox/${JOB_ID}"
OUTBOX_FILE="data/outbox/${JOB_ID}.json"

cleanup() {
    rm -rf "${INBOX_JOB_DIR}" "${OUTBOX_FILE}" "${INBOX_JOB_DIR}.tmp"
}
trap cleanup EXIT

echo "Generating test PDF bill in ${INBOX_JOB_DIR}..."
if command -v uv >/dev/null 2>&1; then
    uv run python -c '
from pathlib import Path
from fpdf import FPDF
from app.parsing.jobs import JobKind, ParserJob, write_job

pdf = FPDF()
pdf.add_page()
pdf.set_font("Helvetica", size=12)
pdf.cell(0, 10, "BESCOM Electricity Bill", new_x="LMARGIN", new_y="NEXT")
pdf.cell(0, 10, "Amount Due: Rs. 1,250.50", new_x="LMARGIN", new_y="NEXT")
pdf.cell(0, 10, "Due Date: 20-11-2026", new_x="LMARGIN", new_y="NEXT")
data = bytes(pdf.output())

write_job(
    Path("data/inbox"),
    ParserJob(job_id="'"${JOB_ID}"'", kind=JobKind.PDF, files=["bill.pdf"]),
    {"bill.pdf": data},
)
'
else
    python3 -c '
from pathlib import Path
from fpdf import FPDF
from app.parsing.jobs import JobKind, ParserJob, write_job

pdf = FPDF()
pdf.add_page()
pdf.set_font("Helvetica", size=12)
pdf.cell(0, 10, "BESCOM Electricity Bill", new_x="LMARGIN", new_y="NEXT")
pdf.cell(0, 10, "Amount Due: Rs. 1,250.50", new_x="LMARGIN", new_y="NEXT")
pdf.cell(0, 10, "Due Date: 20-11-2026", new_x="LMARGIN", new_y="NEXT")
data = bytes(pdf.output())

write_job(
    Path("data/inbox"),
    ParserJob(job_id="'"${JOB_ID}"'", kind=JobKind.PDF, files=["bill.pdf"]),
    {"bill.pdf": data},
)
'
fi

echo "Waiting for ${OUTBOX_FILE} (up to 120s)..."
ELAPSED=0
while [ ! -f "${OUTBOX_FILE}" ]; do
    if [ "${ELAPSED}" -ge 120 ]; then
        echo "Timed out waiting for ${OUTBOX_FILE}" >&2
        exit 1
    fi
    sleep 1
    ELAPSED=$((ELAPSED + 1))
done

echo "Result JSON:"
cat "${OUTBOX_FILE}"
echo ""

if grep -q "1,250.50" "${OUTBOX_FILE}"; then
    echo "markdown OK"
else
    echo "Check failed: '1,250.50' not found in ${OUTBOX_FILE}" >&2
    exit 1
fi
