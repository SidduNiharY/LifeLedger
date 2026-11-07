import os
import tempfile
from collections.abc import Sequence
from io import BytesIO

import pikepdf

from app.parsing.jobs import MAX_MARKDOWN_CHARS


class PdfLockedError(Exception):
    pass


def unlock_pdf(data: bytes, passwords: Sequence[str]) -> bytes:
    try:
        with pikepdf.open(BytesIO(data)) as p:
            out = BytesIO()
            p.save(out)
            return out.getvalue()
    except pikepdf.PasswordError:
        pass

    for pw in passwords:
        try:
            with pikepdf.open(BytesIO(data), password=pw) as p:
                out = BytesIO()
                p.save(out)
                return out.getvalue()
        except pikepdf.PasswordError:
            continue

    raise PdfLockedError("PDF is locked and cannot be unlocked with the provided passwords.")


def pdf_to_markdown(data: bytes) -> str:
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    artifacts_path = os.environ.get("DOCLING_ARTIFACTS_PATH")
    opts = PdfPipelineOptions(artifacts_path=artifacts_path, do_ocr=False)
    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=opts),
        }
    )

    with tempfile.NamedTemporaryFile(suffix=".pdf", dir="/tmp", delete=False) as tmp:
        tmp.write(data)
        tmp.flush()
        tmp_path = tmp.name

    try:
        conv_res = converter.convert(tmp_path)
        md = conv_res.document.export_to_markdown()
        return md[:MAX_MARKDOWN_CHARS]
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
