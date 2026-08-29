import json

from utils.paths import page_numbers_path, subsection_json_path, toc_path


def get_page_offset(page_number_data):
    offsets = []

    for item in page_number_data["page_number_mapping"]:
        printed_page = item["printed_page"]
        physical_page = item["physical_page"]

        if isinstance(printed_page, int) and not isinstance(printed_page, bool):
            offsets.append(physical_page - printed_page)

    if not offsets:
        raise ValueError("No usable printed page mappings found in page_numbers.json.")

    unique_offsets = set(offsets)

    if len(unique_offsets) != 1:
        raise ValueError(f"Inconsistent physical to printed page offsets found: {sorted(unique_offsets)}")

    return offsets[0]


def validate_subsection_order(subsections):
    previous_printed_page = None
    previous_physical_page = None

    for subsection in subsections:
        printed_page = subsection["printed_page"]
        physical_page = subsection["physical_page"]

        if previous_printed_page is not None and printed_page < previous_printed_page:
            raise ValueError(
                f"Printed pages are not in ascending order at '{subsection['title']}': "
                f"{printed_page} comes after {previous_printed_page}."
            )

        if previous_physical_page is not None and physical_page < previous_physical_page:
            raise ValueError(
                f"Physical pages are not in ascending order at '{subsection['title']}': "
                f"{physical_page} comes after {previous_physical_page}."
            )

        previous_printed_page = printed_page
        previous_physical_page = physical_page


def build_subsections(toc_data, page_number_data):
    page_offset = get_page_offset(page_number_data)
    subsections = []

    for entry in toc_data["toc"]["entries"]:
        if entry.get("level") != 2:
            continue

        printed_page = entry.get("printed_page")

        if not isinstance(printed_page, int) or isinstance(printed_page, bool):
            continue

        subsections.append({
            "title": entry["title"],
            "printed_page": printed_page,
            "physical_page": printed_page + page_offset,
        })

    if not subsections:
        raise ValueError("No level 2 TOC entries with numeric printed pages were found.")

    subsections.sort(key=lambda subsection: subsection["printed_page"])

    validate_subsection_order(subsections)

    return {"subsections": subsections}


def build_and_save_subsections(report_name):
    toc_file = toc_path(report_name)
    page_file = page_numbers_path(report_name)

    if not toc_file.exists():
        raise FileNotFoundError(f"TOC file not found: {toc_file}")

    if not page_file.exists():
        raise FileNotFoundError(f"Page numbers file not found: {page_file}")

    result = build_subsections(
        json.loads(toc_file.read_text(encoding="utf-8")),
        json.loads(page_file.read_text(encoding="utf-8")),
    )

    output_path = subsection_json_path(report_name)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Subsection mapping saved: {output_path}")

    return result