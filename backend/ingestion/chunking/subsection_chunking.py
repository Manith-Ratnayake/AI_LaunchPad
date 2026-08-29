import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from config.config import CONFIG
from services.model_client import call_json_model
from utils.paths import PROMPT_ROOT, chunk_folder, report_text_path, subsection_json_path


CHUNKING_CONFIG = CONFIG["chunking"]
MODEL = CHUNKING_CONFIG["model"]
THINKING = bool(CHUNKING_CONFIG["thinking"])
MAX_WORKERS = int(CHUNKING_CONFIG.get("max_workers", 50))
PIPELINE_CONFIG = CONFIG.get("pipeline", {})
MAX_RETRIES = max(1, int(PIPELINE_CONFIG.get("max_retries", 5)))
RETRY_DELAY_SECONDS = max(0.0, float(PIPELINE_CONFIG.get("retry_delay_seconds", 2)))
PROMPT_PATH = PROMPT_ROOT / "subsection_chunking_prompt.txt"


def page_marker_position(text, physical_page):
    match = re.search(rf"(?m)^\[P{physical_page}\]\s*$", text)
    if not match:
        raise ValueError(f"Page marker not found: [P{physical_page}]")
    return match.start()


def block_marker_position(text, page, block):
    match = re.search(rf"\[B{block}\s*\|\s*P{page}\]", text)
    if not match:
        raise ValueError(f"Block marker not found: [B{block} | P{page}]")
    return match.start()


def block_end_position(text, page, block):
    match = re.search(rf"\[B{block}\s*\|\s*P{page}\]", text)
    if not match:
        raise ValueError(f"Block marker not found: [B{block} | P{page}]")

    remaining_text = text[match.end():]
    next_marker = re.search(r"(?m)(?:^\[P\d+\]\s*$|\[B\d+\s*\|\s*P\d+\])", remaining_text)
    return len(text) if not next_marker else match.end() + next_marker.start()


def source_blocks(text):
    blocks = [
        {"start_page": int(match.group(2)), "start_block": int(match.group(1))}
        for match in re.finditer(r"\[B(\d+)\s*\|\s*P(\d+)\]", text)
    ]
    if not blocks:
        raise ValueError("No block markers found.")
    return blocks


def extract_candidate_subsection(report_text, subsections, title):
    subsection_index = next((index for index, item in enumerate(subsections) if item["title"] == title), None)
    if subsection_index is None:
        raise ValueError(f"Subsection not found: {title}")

    subsection = subsections[subsection_index]
    current_page = subsection["physical_page"]
    start_position = page_marker_position(report_text, current_page)
    later_pages = [item["physical_page"] for item in subsections[subsection_index + 1:] if item["physical_page"] > current_page]
    end_position = page_marker_position(report_text, later_pages[0]) if later_pages else len(report_text)

    if end_position <= start_position:
        raise ValueError(f"Invalid candidate range for '{title}'.")

    candidate_text = report_text[start_position:end_position].strip()
    if not source_blocks(candidate_text):
        raise ValueError(f"No source blocks found for '{title}'.")

    return candidate_text, subsection


def report_identity(report_name):
    match = re.fullmatch(r"(.+?)_(\d{4})", report_name)
    if not match:
        return report_name, None
    return match.group(1).replace("_", " "), int(match.group(2))


def get_chunking_details(subsection_text, subsection, report_name):
    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    company, year = report_identity(report_name)
    prompt = (
        prompt.replace("{company}", company)
        .replace("{year}", str(year or ""))
        .replace("{section}", str(subsection.get("section", "")))
        .replace("{subsection}", subsection["title"])
    )

    metadata = [f"Company: {company}", f"Subsection: {subsection['title']}"]
    if year is not None:
        metadata.insert(1, f"Year: {year}")
    if subsection.get("section"):
        metadata.append(f"Section: {subsection['section']}")

    user_prompt = f"""
{chr(10).join(metadata)}
Printed page: {subsection["printed_page"]}
Physical PDF page: {subsection["physical_page"]}

CANDIDATE SUBSECTION TEXT

{subsection_text}

END CANDIDATE SUBSECTION TEXT
"""

    details, reasoning_content, _ = call_json_model(prompt, user_prompt, MODEL, THINKING)
    return details, reasoning_content


def expand_chunk_boundaries(candidate_text, raw_details):
    if not isinstance(raw_details, dict):
        raise ValueError("Model output must be a JSON object.")

    chunk_starts = raw_details.get("chunks")
    if not isinstance(chunk_starts, list) or not chunk_starts:
        raise ValueError("Model output must contain a non-empty 'chunks' list.")

    candidate_blocks = source_blocks(candidate_text)
    block_lookup = {(block["start_page"], block["start_block"]): index for index, block in enumerate(candidate_blocks)}
    start_indices = []

    for chunk_index, chunk_start in enumerate(chunk_starts, start=1):
        if not isinstance(chunk_start, dict):
            raise ValueError(f"Chunk start {chunk_index} must be a JSON object.")
        if set(chunk_start) != {"start_page", "start_block"}:
            raise ValueError(f"Chunk start {chunk_index} must contain only start_page and start_block.")

        page = chunk_start["start_page"]
        block = chunk_start["start_block"]
        if not isinstance(page, int) or isinstance(page, bool) or not isinstance(block, int) or isinstance(block, bool):
            raise ValueError(f"Chunk start {chunk_index} page and block values must be integers.")

        key = (page, block)
        if key not in block_lookup:
            raise ValueError(f"Chunk start {chunk_index} does not match a candidate source block: {chunk_start}")
        start_indices.append(block_lookup[key])

    if start_indices != sorted(set(start_indices)):
        raise ValueError("Chunk starts must be unique and appear in source order.")

    expanded_chunks = []
    for index, start_index in enumerate(start_indices):
        next_start = start_indices[index + 1] if index + 1 < len(start_indices) else len(candidate_blocks)
        if next_start <= start_index:
            raise ValueError("Chunk starts must create non-empty consecutive ranges.")
        expanded_chunks.append({"blocks": candidate_blocks[start_index:next_start]})

    return {"chunks": expanded_chunks}, {"before_subsection": candidate_blocks[:start_indices[0]]}


def create_chunks(candidate_text, chunking_details):
    chunks = []
    for index, chunk_group in enumerate(chunking_details["chunks"], start=1):
        first_block = chunk_group["blocks"][0]
        last_block = chunk_group["blocks"][-1]
        start_position = block_marker_position(candidate_text, first_block["start_page"], first_block["start_block"])
        end_position = block_end_position(candidate_text, last_block["start_page"], last_block["start_block"])
        chunks.append({"chunk": index, "blocks": chunk_group["blocks"], "text": candidate_text[start_position:end_position].strip()})
    return chunks


def safe_folder_name(title):
    return re.sub(r"[^a-zA-Z0-9]+", "_", title).strip("_").lower()


def existing_chunk_count(output_dir):
    details_path = output_dir / "chunking_details.json"
    error_path = output_dir / "validation_error.txt"
    if error_path.exists() or not details_path.exists():
        return None

    try:
        details = json.loads(details_path.read_text(encoding="utf-8"))
        chunks = details.get("chunks")
        if not isinstance(chunks, list) or not chunks:
            return None
        if any(not (output_dir / f"chunk_{index:03}.txt").exists() for index in range(1, len(chunks) + 1)):
            return None
        return len(chunks)
    except Exception:
        return None


def chunk_report(report_name, titles=None, workers=None, reuse_existing=True):
    text_path = report_text_path(report_name)
    subsections_path = subsection_json_path(report_name)

    if not text_path.exists():
        raise FileNotFoundError(f"Report text not found: {text_path}")
    if not subsections_path.exists():
        raise FileNotFoundError(f"Subsection JSON not found: {subsections_path}")

    report_text = text_path.read_text(encoding="utf-8")
    subsections = json.loads(subsections_path.read_text(encoding="utf-8")).get("subsections", [])
    if not subsections:
        raise ValueError("subsection.json contains no subsections.")

    selected_titles = titles or [subsection["title"] for subsection in subsections]
    existing_titles = {subsection["title"] for subsection in subsections}
    for title in selected_titles:
        if title not in existing_titles:
            raise ValueError(f"Subsection not found: {title}")

    counts = {}
    failures = {}
    pending_titles = []

    for title in selected_titles:
        output_dir = chunk_folder(report_name) / safe_folder_name(title)
        if reuse_existing:
            count = existing_chunk_count(output_dir)
            if count is not None:
                counts[title] = count
                print(f"{title}: existing {count} chunks reused.")
                continue
        pending_titles.append(title)

    def process_subsection(title):
        candidate_text, subsection = extract_candidate_subsection(report_text, subsections, title)
        output_dir = chunk_folder(report_name) / safe_folder_name(title)
        output_dir.mkdir(parents=True, exist_ok=True)

        (output_dir / "subsection_input.txt").write_text(candidate_text, encoding="utf-8")
        (output_dir / "candidate_blocks.json").write_text(json.dumps(source_blocks(candidate_text), indent=2, ensure_ascii=False), encoding="utf-8")

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                raw_details, reasoning_content = get_chunking_details(candidate_text, subsection, report_name)
                (output_dir / "chunking_details_raw.json").write_text(json.dumps(raw_details, indent=2, ensure_ascii=False), encoding="utf-8")
                (output_dir / "chunking_thinking.txt").write_text(reasoning_content, encoding="utf-8")

                chunking_details, ignored_blocks = expand_chunk_boundaries(candidate_text, raw_details)
                chunks = create_chunks(candidate_text, chunking_details)
                (output_dir / "chunking_details.json").write_text(json.dumps(chunking_details, indent=2, ensure_ascii=False), encoding="utf-8")
                (output_dir / "ignored_blocks.json").write_text(json.dumps(ignored_blocks, indent=2, ensure_ascii=False), encoding="utf-8")

                validation_error_path = output_dir / "validation_error.txt"
                if validation_error_path.exists():
                    validation_error_path.unlink()

                for old_chunk_file in output_dir.glob("chunk_*.txt"):
                    old_chunk_file.unlink()
                for chunk in chunks:
                    (output_dir / f"chunk_{chunk['chunk']:03}.txt").write_text(chunk["text"], encoding="utf-8")

                if attempt > 1:
                    print(f"{title}: succeeded on attempt {attempt}/{MAX_RETRIES}.")
                return len(chunks)
            except Exception as error:
                (output_dir / "validation_error.txt").write_text(str(error), encoding="utf-8")
                print(f"{title}: attempt {attempt}/{MAX_RETRIES} failed: {error}")

                if attempt >= MAX_RETRIES:
                    raise RuntimeError(f"{title}: failed after {MAX_RETRIES} attempts.") from error

                if RETRY_DELAY_SECONDS > 0:
                    time.sleep(RETRY_DELAY_SECONDS)

    worker_count = int(workers or MAX_WORKERS)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {executor.submit(process_subsection, title): title for title in pending_titles}
        for future in as_completed(futures):
            title = futures[future]
            try:
                counts[title] = future.result()
                print(f"{title}: created {counts[title]} chunks.")
            except Exception as error:
                failures[title] = str(error)
                print(f"{title}: FAILED: {error}")

    if failures:
        failed_names = ", ".join(failures)
        raise RuntimeError(f"Chunking failed for {len(failures)} subsection(s): {failed_names}")

    return sum(counts.values())