import json
import re
from collections import Counter

from opensearchpy import helpers

from config.config import CONFIG
from ingestion.indexing.index import ensure_index
from services.embedding import EMBEDDING_MODEL, embed_texts
from services.opensearch_client import DEFAULT_INDEX, get_opensearch_client
from utils.paths import chunk_folder, enrichment_folder, subsection_json_path, toc_path


BULK_SIZE = int(CONFIG.get("opensearch", {}).get("bulk_size", 100))


def safe_folder_name(title):
    return re.sub(r"[^a-zA-Z0-9]+", "_", title).strip("_").lower()


def parse_report_identity(report_name):
    match = re.fullmatch(r"(.+?)[_-](20\d{2})", report_name)
    if not match:
        return report_name.replace("_", " ").strip(), None
    return match.group(1).replace("_", " ").strip(), int(match.group(2))


def strip_markers(text):
    text = re.sub(r"(?m)^\[P\d+\]\s*$", "", text)
    text = re.sub(r"(?m)^\[B\d+\s*\|\s*P\d+\]\s*$", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def build_section_ranges(toc_data):
    entries = toc_data.get("toc", {}).get("entries", [])
    sections = []
    current = None

    for entry in entries:
        if entry.get("level") == 1:
            current = {"title": entry["title"], "start_printed_page": None}
            sections.append(current)
            continue

        if entry.get("level") == 2 and current is not None and current["start_printed_page"] is None:
            printed_page = entry.get("printed_page")
            if isinstance(printed_page, int) and not isinstance(printed_page, bool):
                current["start_printed_page"] = printed_page

    return [section for section in sections if section["start_printed_page"] is not None]


def section_for_subsection(subsection, section_ranges):
    printed_page = subsection.get("printed_page")
    if isinstance(printed_page, int) and not isinstance(printed_page, bool):
        eligible = [section for section in section_ranges if section["start_printed_page"] <= printed_page]
        if eligible:
            return eligible[-1]["title"], eligible[-1]["start_printed_page"]

    if section_ranges:
        return section_ranges[-1]["title"], section_ranges[-1]["start_printed_page"]
    return "Unknown", None


def structured_terms(enrichment):
    values = []
    for field in ("rows", "columns", "units", "x_axis", "y_axis", "series", "categories"):
        value = enrichment.get(field)
        if isinstance(value, list):
            values.extend(str(item).strip() for item in value if str(item).strip())
        elif isinstance(value, str) and value.strip():
            values.append(value.strip())
    return values


def build_embedding_text(company, year, section, subsection_title, enrichment):
    parts = [f"Company: {company}"]
    if year is not None:
        parts.append(f"Year: {year}")
    parts.extend([f"Section: {section}", f"Subsection: {subsection_title}", f"Content type: {enrichment['type']}"])

    if enrichment.get("category"):
        parts.append(f"Category: {enrichment['category']}")

    parts.append(f"Description: {enrichment['description']}")
    if enrichment.get("keywords"):
        parts.append("Keywords: " + ", ".join(enrichment["keywords"]))

    terms = structured_terms(enrichment)
    if terms:
        parts.append("Structured terms: " + ", ".join(terms))

    return "\n".join(parts)


def load_enriched_documents(report_name):
    chunks_root = chunk_folder(report_name)
    enrichment_root = enrichment_folder(report_name)
    subsection_path = subsection_json_path(report_name)
    toc_file = toc_path(report_name)

    for path in (chunks_root, enrichment_root, subsection_path, toc_file):
        if not path.exists():
            raise FileNotFoundError(f"Required path not found: {path}")

    company, year = parse_report_identity(report_name)
    subsections = load_json(subsection_path).get("subsections", [])
    section_ranges = build_section_ranges(load_json(toc_file))
    if not subsections:
        raise ValueError(f"No subsections found in {subsection_path}")

    documents = []
    for subsection in subsections:
        title = subsection["title"]
        folder = safe_folder_name(title)
        chunk_dir = chunks_root / folder
        enrichment_dir = enrichment_root / folder
        details_path = enrichment_dir / "enrichment_details.json"

        if not chunk_dir.is_dir():
            raise FileNotFoundError(f"Chunk folder missing for '{title}': {chunk_dir}")
        if not details_path.exists():
            raise FileNotFoundError(f"Enrichment details missing for '{title}': {details_path}")

        details = load_json(details_path).get("chunks", [])
        chunk_files = sorted(chunk_dir.glob("chunk_*.txt"))
        if len(details) != len(chunk_files):
            raise ValueError(f"Chunk/enrichment mismatch for '{title}': {len(chunk_files)} chunks vs {len(details)} enrichments")

        section, section_start_page = section_for_subsection(subsection, section_ranges)

        for expected_index, enrichment in enumerate(details, start=1):
            if enrichment.get("chunk") != expected_index:
                raise ValueError(f"Unexpected chunk number for '{title}': expected {expected_index}, got {enrichment.get('chunk')}")

            chunk_path = chunk_dir / f"chunk_{expected_index:03}.txt"
            if not chunk_path.exists():
                raise FileNotFoundError(f"Chunk text missing: {chunk_path}")

            blocks = enrichment.get("blocks") or []
            if not blocks:
                raise ValueError(f"No block metadata for '{title}' chunk {expected_index}")

            source_text = chunk_path.read_text(encoding="utf-8")
            pages = [int(block["start_page"]) for block in blocks]
            first_block = blocks[0]
            chunk_id = f"{folder}/chunk_{expected_index:03}"
            embedding_text = build_embedding_text(company, year, section, title, enrichment)
            cleaned_source = strip_markers(source_text)
            search_text = f"{embedding_text}\n\n{cleaned_source}" if cleaned_source else embedding_text

            document = {
                "doc_key": f"{report_name}/{chunk_id}",
                "report": report_name,
                "company": company,
                "year": year,
                "section_category": section,
                "section_start_page": section_start_page,
                "subsection": title,
                "subsection_name": title,
                "subsection_start_page": subsection.get("physical_page"),
                "subsection_printed_page": subsection.get("printed_page"),
                "subsection_start_block": int(first_block["start_block"]),
                "chunk_id": chunk_id,
                "chunk_number": expected_index,
                "chunk_type": enrichment["type"],
                "content_category": enrichment.get("category"),
                "page_start": min(pages),
                "page_end": max(pages),
                "blocks": blocks,
                "description": enrichment["description"],
                "keywords": enrichment.get("keywords") or [],
                "search_text": search_text,
                "source_text": source_text,
                "embedding_text": embedding_text,
            }

            for field in ("rows", "columns", "units", "x_axis", "y_axis", "series", "categories"):
                if field in enrichment:
                    document[field] = enrichment[field]

            documents.append({key: value for key, value in document.items() if value is not None})

    keys = [document["doc_key"] for document in documents]
    duplicates = [key for key, count in Counter(keys).items() if count > 1]
    if duplicates:
        raise ValueError(f"Duplicate doc_key values found: {duplicates[:5]}")

    return documents


def print_validation(report_name, documents):
    types = Counter(document["chunk_type"] for document in documents)
    categories = Counter(document.get("content_category", "none") for document in documents)
    print(f"Report: {report_name}")
    print(f"Validated documents: {len(documents)}")
    print("Types: " + ", ".join(f"{key}={value}" for key, value in sorted(types.items())))
    print("Categories: " + ", ".join(f"{key}={value}" for key, value in sorted(categories.items())))
    return len(documents)


def ingest_enriched_chunks_to_opensearch(report_name, index_name=None, profile_name=None, region_name=None, validate_only=False):
    documents = load_enriched_documents(report_name)
    if validate_only:
        return print_validation(report_name, documents)

    index_name = index_name or DEFAULT_INDEX
    client, service = get_opensearch_client(profile_name=profile_name, region_name=region_name)
    ensure_index(client, index_name)

    embedding_inputs = [document["embedding_text"] for document in documents]
    print(f"Embedding {len(embedding_inputs)} chunks with {EMBEDDING_MODEL}...")
    vectors = embed_texts(embedding_inputs)
    if len(vectors) != len(documents):
        raise RuntimeError(f"Embedding count mismatch: {len(vectors)} vectors for {len(documents)} documents")

    actions = []
    for document, vector in zip(documents, vectors):
        source = dict(document)
        source["embedding_model"] = EMBEDDING_MODEL
        source["embedding"] = vector
        action = {"_op_type": "index", "_index": index_name, "_source": source}
        if service == "es":
            action["_id"] = source["doc_key"]
        actions.append(action)

    if BULK_SIZE < 1:
        raise ValueError("opensearch.bulk_size must be >= 1")

    print(f"Indexing {len(actions)} documents into '{index_name}'...")
    success_count, errors = helpers.bulk(client, actions, chunk_size=BULK_SIZE, request_timeout=120, raise_on_error=False)
    if errors:
        raise RuntimeError(f"{len(errors)} OpenSearch documents failed. First failures: {errors[:3]}")

    print(f"Ingestion completed: {success_count}/{len(actions)} documents indexed for {report_name}.")
    return success_count
