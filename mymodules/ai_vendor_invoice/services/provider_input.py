# © 2024 Wukong Digital. License LGPL-3.
"""Validated transport input passed from Parse Service to a Provider adapter."""

from dataclasses import dataclass, field


DOCUMENT_INPUT_MODES = ("rendered_images", "native_pdf")


@dataclass
class ProviderInput:
    """One source descriptor and exactly one Provider transport payload."""

    mode: str
    source: dict
    images: tuple = ()
    document_bytes: bytes = None
    page_artifacts: tuple = field(default_factory=tuple, repr=False)

    def __post_init__(self):
        if self.mode not in DOCUMENT_INPUT_MODES:
            raise ValueError("Unsupported document input mode.")
        if not isinstance(self.source, dict):
            raise ValueError("Provider input source metadata is required.")
        if self.mode == "rendered_images":
            if not self.images or self.document_bytes is not None:
                raise ValueError("Rendered-image input requires images only.")
            if self.source.get("page_count") != len(self.images):
                raise ValueError("Rendered-image page count does not match images.")
        elif self.document_bytes is None or self.images:
            raise ValueError("Native-PDF input requires document bytes only.")
        if not self.source.get("mime_type"):
            raise ValueError("Provider input source MIME type is required.")

    def __getitem__(self, key):
        if key == "type":
            return "pages" if self.mode == "rendered_images" else "document"
        if key == "mode":
            return self.mode
        if key == "source":
            return self.source
        if key == "images":
            return list(self.images) if self.images else None
        if key == "document_bytes":
            return self.document_bytes
        if key == "page_artifacts":
            return list(self.page_artifacts)
        raise KeyError(key)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default
