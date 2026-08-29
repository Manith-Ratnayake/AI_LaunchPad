import base64
import json
import tempfile
from pathlib import Path

import pymupdf

from config.config import CONFIG
from services.model_client import call_multimodal_json_model
from utils.paths import PROMPT_ROOT, toc_path, toc_thinking_path


TOC_CONFIG = CONFIG["toc_identification"]
MODEL = TOC_CONFIG["model"]
THINKING = bool(TOC_CONFIG["thinking"])
DPI = int(TOC_CONFIG["dpi"])
PAGES_TO_CHECK = int(TOC_CONFIG["pages_to_check"])
PROMPT = (PROMPT_ROOT / "toc_identification_prompt.txt").read_text(encoding="utf-8")


def encode_image(image_path):
    return base64.b64encode(Path(image_path).read_bytes()).decode("utf-8")


def render_pages(pdf_path, output_dir):
    image_paths = []
    with pymupdf.open(pdf_path) as document:
        end_index = min(PAGES_TO_CHECK, len(document))
        for page_index in range(end_index):
            physical_page = page_index + 1
            page = document[page_index]
            pixmap = page.get_pixmap(dpi=DPI, alpha=False)
            image_path = Path(output_dir) / f"page_{physical_page}.jpg"
            pixmap.save(str(image_path))
            image_paths.append((physical_page, image_path))
    return image_paths


def identify_table_of_contents(pdf_path):
    with tempfile.TemporaryDirectory() as temp_dir:
        image_paths = render_pages(pdf_path, temp_dir)
        content = [{"type": "text", "text": PROMPT}]

        for physical_page, image_path in image_paths:
            content.append({"type": "text", "text": f"Physical PDF page: {physical_page}"})
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encode_image(image_path)}"}})

        result, reasoning_content, _ = call_multimodal_json_model(content, MODEL, THINKING)

    return result, reasoning_content


def identify_and_save_toc(pdf_path, report_name):
    result, reasoning_content = identify_table_of_contents(pdf_path)
    json_output_path = toc_path(report_name)
    thinking_output_path = toc_thinking_path(report_name)
    json_output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    thinking_output_path.write_text(reasoning_content, encoding="utf-8")
    print(f"TOC saved: {json_output_path}")
    print(f"TOC thinking saved: {thinking_output_path}")
    return result
