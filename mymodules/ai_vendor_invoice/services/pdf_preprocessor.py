# © 2024 Wukong Digital. License LGPL-3.
"""Convert a PDF attachment into an in-memory ProviderInput."""

import hashlib

import fitz

from .provider_input import ProviderInput


class PDFPreprocessorError(Exception):
    """Base error for PDF-to-page conversion."""


class PDFInvalidError(PDFPreprocessorError):
    """The input is not a readable PDF."""


class PDFEmptyError(PDFPreprocessorError):
    """The PDF contains no pages."""


class PDFEncryptedError(PDFPreprocessorError):
    """The PDF is encrypted and cannot be opened without a password."""


class PDFRenderError(PDFPreprocessorError):
    """A PDF page could not be rendered as PNG."""


def prepare_provider_input(pdf_attachment, mode="rendered_images"):
    """Prepare one validated ProviderInput without persisting transport bytes."""
    pdf_bytes = pdf_attachment.raw or b""
    if not pdf_bytes:
        raise PDFInvalidError("PDF input is empty.")
    try:
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
    except (RuntimeError, ValueError) as error:
        raise PDFInvalidError("PDF input is invalid.") from error
    try:
        if document.needs_pass:
            raise PDFEncryptedError("Encrypted PDF input cannot be opened.")
        if document.page_count == 0:
            raise PDFEmptyError("PDF input contains no pages.")
        source = {
            "attachment_id": pdf_attachment.id,
            "page_count": document.page_count,
            "mime_type": "application/pdf",
            "checksum": hashlib.sha256(pdf_bytes).hexdigest(),
        }
        if mode == "native_pdf":
            return ProviderInput(
                mode=mode,
                source=source,
                document_bytes=pdf_bytes,
            )
        images = []
        for page_number in range(document.page_count):
            try:
                page = document.load_page(page_number)
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                images.append(pixmap.tobytes("png"))
            except (RuntimeError, ValueError) as error:
                raise PDFRenderError("PDF page rendering failed.") from error
        return ProviderInput(
            mode=mode,
            source=source,
            images=tuple(images),
        )
    finally:
        document.close()
