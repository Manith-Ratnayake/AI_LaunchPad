from __future__ import annotations

import os
import time
from pathlib import Path
from dotenv import load_dotenv
from llama_cloud import LlamaCloud

load_dotenv()
LLAMA_CLOUD_API_KEY = os.getenv("LLAMA_CLOUD_API_KEY")



input_filename = "durdans_2026.pdf"
output_filename = "durdans_2026.txt"

PDF_PATH = Path(input_filename)
OUTPUT_PATH = Path(output_filename)


def main() -> None:

    global parsing_instruction

    if not PDF_PATH.exists():
        raise FileNotFoundError(
            f"PDF not found: {PDF_PATH.resolve()}\n"
            "Place annual_report.pdf in the same folder as this script."
        )

    if not LLAMA_CLOUD_API_KEY:
        raise EnvironmentError(
            "LLAMA_CLOUD_API_KEY is not set.\n"
            "Windows PowerShell:\n"
            '$env:LLAMA_CLOUD_API_KEY="llx-your-key"\n\n'
            "Linux or macOS:\n"
            'export LLAMA_CLOUD_API_KEY="llx-your-key"'
        )

    start_time = time.perf_counter()
    client = LlamaCloud()

    print("Uploading PDF to LlamaParse...")
    uploaded_file = client.files.create(
        file=PDF_PATH,
        purpose="parse",
    )

    print("Parsing PDF...")

    result = client.parsing.parse(
        file_id=uploaded_file.id,
        tier="agentic",
        version="latest",
        expand=["text"],
        agentic_options={
            "custom_prompt": parsing_instruction
        },
    )



    if result.text is None:
        raise RuntimeError(
            "LlamaParse completed but returned no text output."
        )

    output_parts: list[str] = []

    for page in result.text.pages:
        output_parts.append(
            f"===== PAGE {page.page_number} =====\n\n"
            f"{page.text.strip()}\n"
        )

    OUTPUT_PATH.write_text(
        "\n".join(output_parts),
        encoding="utf-8",
    )

    elapsed = time.perf_counter() - start_time
    print(f"Finished in {elapsed:.2f} seconds.")
    print(f"Text saved to: {OUTPUT_PATH.resolve()}")

   


parsing_instruction = """
This document is a corporate annual report.

Extract the document content accurately in its natural reading order.

Preserve section headings, subheadings, paragraphs, bullet points, financial values,
table titles, table structure, row labels, column labels, footnotes, and captions.

For multi-column pages, follow the correct reading order rather than mixing text
between columns.

Preserve tables as structured tables. Do not convert tables into disconnected text.

Ignore decorative content, repeated headers, repeated footers, page numbers,
background text, logos, and text that appears only as part of decorative photographs
or illustrations.

Do not summarize, rewrite, explain, or infer information.
Extract only information that is actually present in the document.
"""


if __name__ == "__main__":
    main()
