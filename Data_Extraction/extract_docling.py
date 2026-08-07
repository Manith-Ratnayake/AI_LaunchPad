from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ["TORCH_COMPILE_DISABLE"] = "1"

from docling.document_converter import DocumentConverter


BASE_DIR = Path(__file__).resolve().parent

PDF_PATH = BASE_DIR / "annual_report.pdf"
OUTPUT_PATH = BASE_DIR / "docling_output.txt"


def is_memory_error(error: BaseException) -> bool:
    error_message = str(error).lower()

    memory_error_messages = (
        "not enough memory",
        "out of memory",
        "std::bad_alloc",
        "defaultcpuallocator",
        "cannot allocate memory",
        "memory allocation",
    )

    return isinstance(error, MemoryError) or any(
        message in error_message
        for message in memory_error_messages
    )


def main() -> None:
    if not PDF_PATH.exists():
        print(f"Error: PDF not found at:\n{PDF_PATH}")
        print("Place annual_report.pdf in the same folder as this script.")
        sys.exit(1)

    start_time = time.perf_counter()

    try:
        print(f"Processing: {PDF_PATH.name}")

        converter = DocumentConverter()
        result = converter.convert(PDF_PATH)

        text = result.document.export_to_text(
            page_break_placeholder=(
                "\n\n===== PAGE BREAK =====\n\n"
            ),
            traverse_pictures=True,
        )

        OUTPUT_PATH.write_text(
            text,
            encoding="utf-8",
        )

    except BaseException as error:
        if isinstance(error, KeyboardInterrupt):
            print("\nProcessing stopped by the user.")
            sys.exit(130)

        if is_memory_error(error):
            print("\nDocling stopped because the computer ran out of memory.")
            print("Close other programs or restart the computer and try again.")
            print("You can also reduce Docling batch sizes or disable OCR.")
            sys.exit(1)

        print("\nDocling could not process the PDF.")
        print(f"Error type: {type(error).__name__}")
        print(f"Details: {error}")
        sys.exit(1)

    elapsed = time.perf_counter() - start_time

    print(f"Finished in {elapsed:.2f} seconds.")
    print(f"Text saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()