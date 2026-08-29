import base64
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pymupdf

from config.config import CONFIG
from services.model_client import call_vision_model_with_reasoning
from utils.paths import PROMPT_ROOT, report_pages_folder, thinking_pages_folder


EXTRACTION_CONFIG = CONFIG["extraction"]
MODEL = EXTRACTION_CONFIG["model"]
THINKING = bool(EXTRACTION_CONFIG["thinking"])
DPI = int(EXTRACTION_CONFIG["dpi"])
MAX_WORKERS = int(EXTRACTION_CONFIG.get("max_workers", 10))
EXTRACTION_PROMPT = (PROMPT_ROOT / "text_extraction_prompt.txt").read_text(encoding="utf-8")


def page_file(report_name, page_number):
    return report_pages_folder(report_name) / f"page_{page_number:04d}.txt"


def thinking_file(report_name, page_number):
    return thinking_pages_folder(report_name) / f"page_{page_number:04d}.txt"


def encode_image(image_path):
    return base64.b64encode(image_path.read_bytes()).decode("utf-8")


def render_page(page, output_path):
    matrix = pymupdf.Matrix(DPI / 72, DPI / 72)
    page.get_pixmap(matrix=matrix, alpha=False).save(str(output_path))


def extract_page(page_number, image_path, raw_path, thinking_path):
    try:
        output, reasoning = call_vision_model_with_reasoning(
            image_base64=encode_image(image_path),
            prompt=EXTRACTION_PROMPT,
            model=MODEL,
            thinking=THINKING,
        )

        raw_path.write_text(output + "\n", encoding="utf-8")
        thinking_path.write_text((reasoning or "<NO THINKING RETURNED>") + "\n", encoding="utf-8")

        return {"page": page_number, "success": True, "thinking_returned": bool(reasoning), "error": None}
    except Exception as exc:
        return {"page": page_number, "success": False, "thinking_returned": False, "error": str(exc)}


def extract_pdf(pdf_path, report_name):
    pdf_path = Path(pdf_path).resolve()
    changed = False
    failed_pages = []

    with pymupdf.open(pdf_path) as document, tempfile.TemporaryDirectory() as temp_dir:
        total_pages = len(document)
        print(f"Source PDF pages: {total_pages}")
        print(f"Extraction model: {MODEL} | thinking={THINKING} | dpi={DPI} | workers={MAX_WORKERS}")
        pages_to_extract = []

        for page_index, page in enumerate(document):
            page_number = page_index + 1
            raw_path = page_file(report_name, page_number)
            reasoning_path = thinking_file(report_name, page_number)

            if raw_path.exists() and reasoning_path.exists():
                print(f"[{page_number}/{total_pages}] Using existing extraction + thinking")
                continue

            image_path = Path(temp_dir) / f"page_{page_number:04d}.png"
            print(f"[{page_number}/{total_pages}] Rendering page")
            render_page(page, image_path)
            pages_to_extract.append((page_number, image_path, raw_path, reasoning_path))

        if pages_to_extract:
            print(f"Extracting {len(pages_to_extract)} pages with {MAX_WORKERS} concurrent requests")
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = {
                    executor.submit(extract_page, page_number, image_path, raw_path, reasoning_path): page_number
                    for page_number, image_path, raw_path, reasoning_path in pages_to_extract
                }

                for future in as_completed(futures):
                    result = future.result()
                    page_number = result["page"]
                    if result["success"]:
                        changed = True
                        thinking_status = "thinking saved" if result["thinking_returned"] else "NO thinking returned"
                        print(f"[{page_number}/{total_pages}] Extraction saved, {thinking_status}")
                    else:
                        failed_pages.append({"page": page_number, "error": result["error"]})
                        print(f"[{page_number}/{total_pages}] FAILED: {result['error']}")

    return {"total_pages": total_pages, "changed": changed, "failed_pages": failed_pages}
