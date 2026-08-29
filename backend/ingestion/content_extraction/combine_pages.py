import re

from utils.paths import extraction_thinking_path, report_pages_folder, report_text_path, thinking_pages_folder


def add_page_and_block_markers(text, page_number):
    text = text.strip()
    output = [f"[P{page_number}]"]

    if not text:
        return output[0]

    blocks = [block.strip() for block in re.split(r"\n[ \t]*\n+", text) if block.strip()]
    for block_number, block in enumerate(blocks, start=1):
        output.extend(["", f"[B{block_number} | P{page_number}]", block])

    return "\n".join(output).rstrip()


def add_thinking_page_marker(text, page_number):
    text = text.strip() or "<NO THINKING RETURNED>"
    return f"[P{page_number}]\n\n{text}"


def combine_extracted_text(report_name, total_pages):
    raw_folder = report_pages_folder(report_name)
    reasoning_folder = thinking_pages_folder(report_name)
    report_parts = []
    thinking_parts = []

    for page_number in range(1, total_pages + 1):
        raw_path = raw_folder / f"page_{page_number:04d}.txt"
        reasoning_path = reasoning_folder / f"page_{page_number:04d}.txt"

        if not raw_path.exists():
            raise FileNotFoundError(f"Missing raw extraction for PDF page {page_number}: {raw_path}")
        if not reasoning_path.exists():
            raise FileNotFoundError(f"Missing extraction thinking for PDF page {page_number}: {reasoning_path}")

        report_parts.append(add_page_and_block_markers(raw_path.read_text(encoding="utf-8"), page_number))
        thinking_parts.append(add_thinking_page_marker(reasoning_path.read_text(encoding="utf-8"), page_number))

    output_path = report_text_path(report_name)
    output_path.write_text("\n\n".join(report_parts).strip() + "\n", encoding="utf-8")

    reasoning_output_path = extraction_thinking_path(report_name)
    reasoning_output_path.write_text("\n\n".join(thinking_parts).strip() + "\n", encoding="utf-8")

    print(f"Combined marked text saved: {output_path}")
    print(f"Combined extraction thinking saved: {reasoning_output_path}")
    return output_path
