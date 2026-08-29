from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PROMPT_ROOT = ROOT / "config" / "prompts"

OUTPUT_ROOT = ROOT / "outputs"
ANNUAL_REPORT_ROOT = ROOT / "annual_reports"

OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)


def report_folder(report_name):
    folder = OUTPUT_ROOT / report_name
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def report_pages_folder(report_name):
    folder = report_folder(report_name) / "report_pages"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def thinking_pages_folder(report_name):
    folder = report_folder(report_name) / "thinking_pages"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def report_text_path(report_name):
    return report_folder(report_name) / "report.txt"


def extraction_thinking_path(report_name):
    return report_folder(report_name) / "thinking.txt"


def pipeline_state_path(report_name):
    return report_folder(report_name) / "pipeline_state.json"


def toc_path(report_name):
    return report_folder(report_name) / "toc.json"


def toc_thinking_path(report_name):
    return report_folder(report_name) / "toc_thinking.txt"


def page_numbers_path(report_name):
    return report_folder(report_name) / "page_numbers.json"


def page_numbers_thinking_path(report_name):
    return report_folder(report_name) / "page_numbers_thinking.txt"


def subsection_json_path(report_name):
    return report_folder(report_name) / "subsection.json"


def chunk_folder(report_name):
    folder = report_folder(report_name) / "chunks"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def enrichment_folder(report_name):
    folder = report_folder(report_name) / "enrichment"
    folder.mkdir(parents=True, exist_ok=True)
    return folder
