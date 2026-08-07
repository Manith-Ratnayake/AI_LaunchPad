from __future__ import annotations

import time
from pathlib import Path
import os
import pdfplumber


file_path = Path(__file__).resolve().parent
print(file_path)

PDF_PATH = Path("annual_report.pdf")
PDF_PATH = file_path / PDF_PATH

OUTPUT_PATH = Path("pdfplumber_output.txt")
OUTPUT_PATH = file_path / OUTPUT_PATH


def main() -> None:
    if not PDF_PATH.exists():
        raise FileNotFoundError(f"PDF not found: {PDF_PATH.resolve()}\n" "Place annual_report.pdf in the same folder as this script.")

    start_time = time.perf_counter()
    output_parts: list[str] = []

    with pdfplumber.open(PDF_PATH) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text(layout=True) or ""

            output_parts.append(
                f"===== PAGE {page_number} =====\n\n{text.strip()}\n"
            )

            page.close()

    OUTPUT_PATH.write_text(
        "\n".join(output_parts),
        encoding="utf-8",
    )

    elapsed = time.perf_counter() - start_time
    print(f"Finished in {elapsed:.2f} seconds.")
    print(f"Text saved to: {OUTPUT_PATH.resolve()}")


if __name__ == "__main__":
    main()
