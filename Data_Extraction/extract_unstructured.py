from __future__ import annotations

import time
from pathlib import Path

from unstructured.partition.pdf import partition_pdf


PDF_PATH = Path("annual_report.pdf")
OUTPUT_PATH = Path("unstructured_output.txt")


def main() -> None:
    if not PDF_PATH.exists():
        raise FileNotFoundError(
            f"PDF not found: {PDF_PATH.resolve()}\n"
            "Place annual_report.pdf in the same folder as this script."
        )

    start_time = time.perf_counter()

    elements = partition_pdf(
        filename=str(PDF_PATH),
        strategy="auto",
        include_page_breaks=True,
        languages=["eng"],
    )

    output_parts: list[str] = []
    current_page: int | None = None

    for element in elements:
        element_text = str(element).strip()

        if not element_text:
            continue

        metadata = getattr(element, "metadata", None)
        page_number = getattr(metadata, "page_number", None)

        if page_number is not None and page_number != current_page:
            current_page = page_number

            output_parts.append(
                f"\n\n===== PAGE {page_number} =====\n"
            )

        output_parts.append(element_text)

    OUTPUT_PATH.write_text(
        "\n\n".join(output_parts),
        encoding="utf-8",
    )

    elapsed = time.perf_counter() - start_time

    print(f"Finished in {elapsed:.2f} seconds.")
    print(f"Elements extracted: {len(elements)}")
    print(f"Text saved to: {OUTPUT_PATH.resolve()}")


if __name__ == "__main__":
    main()