import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from config.config import CONFIG
from services.model_client import call_chat_model
from utils.paths import PROMPT_ROOT, chunk_folder, enrichment_folder, report_text_path, subsection_json_path


ENRICHMENT_CONFIG = CONFIG["enrichment"]
MODEL = ENRICHMENT_CONFIG["model"]
THINKING = bool(ENRICHMENT_CONFIG["thinking"])
MAX_WORKERS = int(ENRICHMENT_CONFIG.get("max_workers", 40))
PIPELINE_CONFIG = CONFIG.get("pipeline", {})
MAX_RETRIES = max(1, int(PIPELINE_CONFIG.get("max_retries", 5)))
RETRY_DELAY_SECONDS = max(0.0, float(PIPELINE_CONFIG.get("retry_delay_seconds", 2)))
PROMPT_PATH = PROMPT_ROOT / "subsection_enrichment_prompt.txt"
CHART_TYPES = {"bar", "line", "area", "pie", "scatter", "donut", "multi-series"}
CONTENT_TYPES = {"text", "table", "mixed", *CHART_TYPES}


def page_marker_position(text, physical_page):
    match = re.search(rf"(?m)^\[P{physical_page}\]\s*$", text)
    if not match:
        raise ValueError(f"Page marker not found: [P{physical_page}]")
    return match.start()


def extract_subsection(report_text, subsections, title):
    subsection_index = next((index for index, item in enumerate(subsections) if item["title"] == title), None)
    if subsection_index is None:
        raise ValueError(f"Subsection not found: {title}")

    subsection = subsections[subsection_index]
    current_page = subsection["physical_page"]
    start_position = page_marker_position(report_text, current_page)
    later_pages = [item["physical_page"] for item in subsections[subsection_index + 1:] if item["physical_page"] > current_page]
    end_position = page_marker_position(report_text, later_pages[0]) if later_pages else len(report_text)

    if end_position <= start_position:
        raise ValueError(f"Invalid subsection range for '{title}'.")

    return report_text[start_position:end_position].strip(), subsection


def report_identity(report_name):
    match = re.fullmatch(r"(.+?)_(\d{4})", report_name)
    if not match:
        return report_name, None
    return match.group(1).replace("_", " "), int(match.group(2))


def safe_folder_name(title):
    return re.sub(r"[^a-zA-Z0-9]+", "_", title).strip("_").lower()


class EnrichmentFailure(Exception):
    def __init__(self, message, raw_response="", reasoning_content=""):
        super().__init__(message)
        self.raw_response = raw_response
        self.reasoning_content = reasoning_content


def get_enrichment(subsection_text, chunk_text, subsection, report_name):
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    company, year = report_identity(report_name)
    metadata = [f"Company: {company}", f"Subsection: {subsection['title']}"]

    if year is not None:
        metadata.insert(1, f"Year: {year}")
    if subsection.get("section"):
        metadata.append(f"Section: {subsection['section']}")

    user_prompt = f"""
{chr(10).join(metadata)}
Printed page: {subsection["printed_page"]}
Physical PDF page: {subsection["physical_page"]}

FULL SUBSECTION CONTEXT

{subsection_text}

END FULL SUBSECTION CONTEXT

TARGET CHUNK

{chunk_text}

END TARGET CHUNK
"""

    raw_response = ""
    reasoning_content = ""
    try:
        raw_response, reasoning_content = call_chat_model(
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": user_prompt}],
            model=MODEL,
            thinking=THINKING,
            response_format={"type": "json_object"},
        )
        enrichment = json.loads(raw_response)
        validate_enrichment(enrichment)
        return enrichment, reasoning_content
    except Exception as error:
        raise EnrichmentFailure(str(error), raw_response=raw_response, reasoning_content=reasoning_content) from error


def save_failed_enrichment(output_dir, chunk_index, blocks, error):
    failed_dir = output_dir / "failed"
    failed_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    failure = {"chunk": chunk_index, "blocks": blocks, "error_type": type(error).__name__, "error": str(error)}

    raw_response = getattr(error, "raw_response", "")
    reasoning_content = getattr(error, "reasoning_content", "")
    if raw_response:
        failure["raw_response"] = raw_response
    if reasoning_content:
        failure["reasoning_content"] = reasoning_content

    failure_path = failed_dir / f"chunk_{chunk_index:03}_failed_{timestamp}.json"
    failure_path.write_text(json.dumps(failure, indent=2, ensure_ascii=False), encoding="utf-8")
    return failure_path


def validate_string_list(value, field):
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"'{field}' must be a list of strings.")


def validate_structured_category(enrichment):
    if enrichment.get("category") not in {"numerical", "semantic"}:
        raise ValueError("Structured content category must be 'numerical' or 'semantic'.")


def validate_enrichment(enrichment):
    if not isinstance(enrichment, dict):
        raise ValueError("Enrichment output must be a JSON object.")

    description = enrichment.get("description")
    keywords = enrichment.get("keywords")
    content_type = enrichment.get("type")

    if not isinstance(description, str) or not description.strip():
        raise ValueError("Enrichment must contain a non-empty 'description'.")
    validate_string_list(keywords, "keywords")
    if content_type not in CONTENT_TYPES:
        raise ValueError(f"Unsupported enrichment type: {content_type}")

    if content_type == "text":
        expected_fields = {"type", "description", "keywords"}
    elif content_type == "table":
        expected_fields = {"type", "category", "description", "rows", "columns", "units", "keywords"}
        validate_structured_category(enrichment)
        validate_string_list(enrichment.get("rows"), "rows")
        validate_string_list(enrichment.get("columns"), "columns")
        validate_string_list(enrichment.get("units"), "units")
    elif content_type == "mixed":
        expected_fields = {"type", "description", "keywords"}
    else:
        expected_fields = {"type", "category", "description", "x_axis", "y_axis", "units", "series", "categories", "keywords"}
        validate_structured_category(enrichment)

    missing_fields = expected_fields - set(enrichment)
    unexpected_fields = set(enrichment) - expected_fields
    if missing_fields:
        raise ValueError(f"Enrichment is missing fields: {', '.join(sorted(missing_fields))}")
    if unexpected_fields:
        raise ValueError(f"Enrichment contains unexpected fields: {', '.join(sorted(unexpected_fields))}")


def load_chunking_details(chunk_dir):
    chunking_path = chunk_dir / "chunking_details.json"
    if not chunking_path.exists():
        raise FileNotFoundError(f"Chunking details not found: {chunking_path}")

    chunks = json.loads(chunking_path.read_text(encoding="utf-8")).get("chunks")
    if not isinstance(chunks, list) or not chunks:
        raise ValueError(f"Invalid chunking details: {chunking_path}")
    return chunks


def enrich_report(report_name, titles=None, workers=None):
    text_path = report_text_path(report_name)
    subsections_path = subsection_json_path(report_name)
    chunks_root = chunk_folder(report_name)
    enrichment_root = enrichment_folder(report_name)

    if not text_path.exists():
        raise FileNotFoundError(f"Report text not found: {text_path}")
    if not subsections_path.exists():
        raise FileNotFoundError(f"Subsection JSON not found: {subsections_path}")
    if not PROMPT_PATH.exists():
        raise FileNotFoundError(f"Enrichment prompt not found: {PROMPT_PATH}")

    report_text = text_path.read_text(encoding="utf-8")
    subsections = json.loads(subsections_path.read_text(encoding="utf-8")).get("subsections", [])
    if not subsections:
        raise ValueError("subsection.json contains no subsections.")

    selected_titles = titles or [subsection["title"] for subsection in subsections]
    subsection_lookup = {subsection["title"]: subsection for subsection in subsections}
    for title in selected_titles:
        if title not in subsection_lookup:
            raise ValueError(f"Subsection not found: {title}")

    prepared_subsections = {}
    tasks = []

    for title in selected_titles:
        subsection_text, subsection = extract_subsection(report_text, subsections, title)
        folder_name = safe_folder_name(title)
        chunk_dir = chunks_root / folder_name
        output_dir = enrichment_root / folder_name
        chunk_groups = load_chunking_details(chunk_dir)

        prepared_subsections[title] = {
            "subsection": subsection,
            "subsection_text": subsection_text,
            "chunk_dir": chunk_dir,
            "output_dir": output_dir,
            "chunk_groups": chunk_groups,
            "results": {},
        }

        for index, chunk_group in enumerate(chunk_groups, start=1):
            chunk_path = chunk_dir / f"chunk_{index:03}.txt"
            success_path = output_dir / f"chunk_{index:03}.json"

            if not chunk_path.exists():
                raise FileNotFoundError(f"Chunk text not found: {chunk_path}")

            if success_path.exists():
                existing_enrichment = json.loads(success_path.read_text(encoding="utf-8"))
                validate_enrichment(existing_enrichment)
                prepared_subsections[title]["results"][index] = {"chunk": index, "blocks": chunk_group["blocks"], **existing_enrichment}
                print(f"{title} chunk {index}: already enriched, skipped.")
                continue

            tasks.append((title, index, chunk_group["blocks"], chunk_path.read_text(encoding="utf-8")))

    def enrich_with_retry(title, chunk_index, blocks, chunk_text):
        prepared = prepared_subsections[title]
        output_dir = prepared["output_dir"]
        output_dir.mkdir(parents=True, exist_ok=True)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                enrichment, reasoning_content = get_enrichment(prepared["subsection_text"], chunk_text, prepared["subsection"], report_name)
                if attempt > 1:
                    print(f"{title} chunk {chunk_index}: succeeded on attempt {attempt}/{MAX_RETRIES}.")
                return enrichment, reasoning_content
            except Exception as error:
                failure_path = save_failed_enrichment(output_dir, chunk_index, blocks, error)
                print(f"{title} chunk {chunk_index}: attempt {attempt}/{MAX_RETRIES} failed: {error}")
                print(f"  saved failure: {failure_path}")

                if attempt >= MAX_RETRIES:
                    raise RuntimeError(f"{title} chunk {chunk_index}: failed after {MAX_RETRIES} attempts.") from error

                if RETRY_DELAY_SECONDS > 0:
                    time.sleep(RETRY_DELAY_SECONDS)

    worker_count = int(workers or MAX_WORKERS)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {}
        for title, chunk_index, blocks, chunk_text in tasks:
            future = executor.submit(enrich_with_retry, title, chunk_index, blocks, chunk_text)
            futures[future] = (title, chunk_index, blocks)

        for future in as_completed(futures):
            title, chunk_index, blocks = futures[future]
            prepared = prepared_subsections[title]
            output_dir = prepared["output_dir"]
            output_dir.mkdir(parents=True, exist_ok=True)

            try:
                enrichment, reasoning_content = future.result()
                prepared["results"][chunk_index] = {"chunk": chunk_index, "blocks": blocks, **enrichment}
                (output_dir / f"chunk_{chunk_index:03}.json").write_text(json.dumps(enrichment, indent=2, ensure_ascii=False), encoding="utf-8")
                (output_dir / f"chunk_{chunk_index:03}_thinking.txt").write_text(reasoning_content, encoding="utf-8")
                print(f"{title} chunk {chunk_index}: enriched.")
            except Exception as error:
                print(f"{title} chunk {chunk_index}: FAILED: {error}")

    incomplete = {}
    total_enriched = 0

    for title, prepared in prepared_subsections.items():
        expected_count = len(prepared["chunk_groups"])
        success_count = len(prepared["results"])
        total_enriched += success_count

        if success_count != expected_count:
            incomplete[title] = (success_count, expected_count)
            print(f"{title}: enrichment incomplete, {success_count}/{expected_count} chunks succeeded.")
            continue

        combined = {"chunks": [prepared["results"][index] for index in range(1, expected_count + 1)]}
        combined_path = prepared["output_dir"] / "enrichment_details.json"
        prepared["output_dir"].mkdir(parents=True, exist_ok=True)
        combined_path.write_text(json.dumps(combined, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"{title}: saved enrichment for {expected_count} chunks.")

    if incomplete:
        failed_names = ", ".join(incomplete)
        raise RuntimeError(f"Enrichment incomplete for {len(incomplete)} subsection(s): {failed_names}")

    return total_enriched
