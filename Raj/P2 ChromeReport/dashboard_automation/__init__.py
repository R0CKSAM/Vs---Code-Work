"""Weekly TV dashboard ingestion automation."""

from .pipeline import process_new_files

__all__ = ["process_new_files"]
