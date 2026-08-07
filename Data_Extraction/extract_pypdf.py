from __future__ import annotations

import time
from pathlib import Path

from pypdf import PdfReader


PDF_PATH = Path("annual_report.pdf")
OUTPUT_PATH = Path("pypdf_output.txt")


def main() -> None:
    if not PDF_PATH.exists():
        raise FileNotFoundError(
            f"PDF not found: {PDF_PATH.resolve()}\n"
            "Place annual_report.pdf in the same folder as this script."
        )

    start_time = time.perf_counter()
    reader = PdfReader(str(PDF_PATH))
    output_parts: list[str] = []

    for page_number, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text(extraction_mode="layout") or ""
        except (TypeError, ValueError):
            text = page.extract_text() or ""

        output_parts.append(
            f"===== PAGE {page_number} =====\n\n{text.strip()}\n"
        )

    OUTPUT_PATH.write_text(
        "\n".join(output_parts),
        encoding="utf-8",
    )

    elapsed = time.perf_counter() - start_time
    print(f"Finished in {elapsed:.2f} seconds.")
    print(f"Text saved to: {OUTPUT_PATH.resolve()}")


if __name__ == "__main__":
    main()
