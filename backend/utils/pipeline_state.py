import json

from utils.paths import pipeline_state_path


class PipelineState:
    STEPS = (
        "extraction",
        "combine_text",
        "toc_identification",
        "page_number_identification",
        "subsections",
        "chunking",
        "enrichment",
        "opensearch_ingestion",
    )

    def __init__(self, report_name, source_pdf=None):
        self.report_name = report_name
        self.path = pipeline_state_path(report_name)
        self.data = self.load(source_pdf)
        self.save()

    def load(self, source_pdf):
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid pipeline state JSON: {self.path}") from exc
        else:
            data = {}

        data.setdefault("report", self.report_name)
        data["source_pdf"] = str(source_pdf) if source_pdf is not None else data.get("source_pdf")

        steps = data.setdefault("steps", {})
        for step in self.STEPS:
            steps.setdefault(step, "pending")

        extraction = data.setdefault("extraction", {})
        extraction.setdefault("total_pages", 0)
        extraction.setdefault("failed_pages", [])

        chunking = data.setdefault("chunking", {})
        chunking.setdefault("chunk_count", 0)

        enrichment = data.setdefault("enrichment", {})
        enrichment.setdefault("chunk_count", 0)

        return data

    def save(self):
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")

    def is_completed(self, step):
        return self.data["steps"].get(step) == "completed"

    def set_step(self, step, status):
        if step not in self.STEPS:
            raise ValueError(f"Unknown pipeline step: {step}")
        self.data["steps"][step] = status
        self.save()

    def mark_completed(self, step):
        self.set_step(step, "completed")

    def mark_failed(self, step):
        self.set_step(step, "failed")

    def set_extraction(self, total_pages, failed_pages):
        self.data["extraction"] = {"total_pages": int(total_pages), "failed_pages": list(failed_pages)}
        self.save()

    def set_chunk_count(self, chunk_count):
        self.data["chunking"]["chunk_count"] = int(chunk_count)
        self.save()

    def set_enrichment_count(self, chunk_count):
        self.data["enrichment"]["chunk_count"] = int(chunk_count)
        self.save()

    def reset_from(self, step):
        if step not in self.STEPS:
            raise ValueError(f"Unknown pipeline step: {step}")

        start_index = self.STEPS.index(step)
        for current_step in self.STEPS[start_index:]:
            self.data["steps"][current_step] = "pending"

        if start_index <= self.STEPS.index("chunking"):
            self.data["chunking"]["chunk_count"] = 0
        if start_index <= self.STEPS.index("enrichment"):
            self.data["enrichment"]["chunk_count"] = 0

        self.save()
