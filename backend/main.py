import argparse
from pathlib import Path

from inference.orchestrator import answer_question
from ingestion.chunking.subsection_chunking import chunk_report
from ingestion.chunking.subsection_enrichment import enrich_report
from ingestion.content_extraction.combine_pages import combine_extracted_text
from ingestion.content_extraction.extract_pages import extract_pdf
from ingestion.document_hierarchy.build_subsections import build_and_save_subsections
from ingestion.document_hierarchy.page_number_identification import identify_and_save_page_numbers
from ingestion.document_hierarchy.toc_identification import identify_and_save_toc
from ingestion.indexing.opensearch_ingestion import ingest_enriched_chunks_to_opensearch
from utils.pipeline_state import PipelineState


def run_pipeline(pdf_path):
    pdf_path = Path(pdf_path).resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError("Input file must be a PDF")

    report_name = pdf_path.stem
    pipeline_state = PipelineState(report_name, source_pdf=pdf_path.name)
    print(f"\nProcessing: {report_name}")
    step = "extraction"

    try:
        if not pipeline_state.is_completed("extraction"):
            print("\n[1] Extracting pages")
            extraction = extract_pdf(pdf_path, report_name)
            pipeline_state.set_extraction(extraction["total_pages"], extraction["failed_pages"])
            if extraction["failed_pages"]:
                raise RuntimeError(f"{len(extraction['failed_pages'])} pages failed extraction")
            pipeline_state.mark_completed("extraction")
        else:
            print("\n[1] Extraction already completed")
            extraction = pipeline_state.data["extraction"]

        step = "combine_text"
        if not pipeline_state.is_completed("combine_text"):
            print("\n[2] Combining extraction")
            combine_extracted_text(report_name, extraction["total_pages"])
            pipeline_state.mark_completed("combine_text")
        else:
            print("\n[2] Combined text already completed")

        step = "toc_identification"
        if not pipeline_state.is_completed("toc_identification"):
            print("\n[3] Identifying Table of Contents")
            identify_and_save_toc(pdf_path, report_name)
            pipeline_state.mark_completed("toc_identification")
        else:
            print("\n[3] Table of Contents already identified")

        step = "page_number_identification"
        if not pipeline_state.is_completed("page_number_identification"):
            print("\n[4] Identifying printed page numbers")
            identify_and_save_page_numbers(pdf_path, report_name)
            pipeline_state.mark_completed("page_number_identification")
        else:
            print("\n[4] Printed page numbers already identified")

        step = "subsections"
        if not pipeline_state.is_completed("subsections"):
            print("\n[5] Building subsection mappings")
            build_and_save_subsections(report_name)
            pipeline_state.mark_completed("subsections")
        else:
            print("\n[5] Subsection mappings already completed")

        step = "chunking"
        if not pipeline_state.is_completed("chunking"):
            print("\n[6] Creating semantic subsection chunks")
            chunk_count = chunk_report(report_name, reuse_existing=True)
            pipeline_state.set_chunk_count(chunk_count)
            pipeline_state.mark_completed("chunking")
        else:
            print("\n[6] Chunking already completed")
            chunk_count = int(pipeline_state.data["chunking"]["chunk_count"])

        step = "enrichment"
        if not pipeline_state.is_completed("enrichment"):
            print("\n[7] Enriching chunks")
            enriched_count = enrich_report(report_name)
            pipeline_state.set_enrichment_count(enriched_count)
            pipeline_state.mark_completed("enrichment")
        else:
            print("\n[7] Enrichment already completed")
            enriched_count = int(pipeline_state.data["enrichment"]["chunk_count"])

        step = "opensearch_ingestion"
        if not pipeline_state.is_completed("opensearch_ingestion"):
            print("\n[8] Ingesting enriched chunks into OpenSearch")
            indexed_count = ingest_enriched_chunks_to_opensearch(report_name)
            pipeline_state.mark_completed("opensearch_ingestion")
        else:
            print("\n[8] OpenSearch ingestion already completed")
            indexed_count = enriched_count

        print("\nPipeline completed")
        print(f"Chunks: {chunk_count}")
        print(f"Enriched: {enriched_count}")
        print(f"Indexed: {indexed_count}")
        return {"report": report_name, "chunks": chunk_count, "enriched": enriched_count, "indexed": indexed_count}

    except Exception:
        pipeline_state.mark_failed(step)
        raise


def run_inference(question):
    result = answer_question(question)
    print("\nAnswer:")
    print(result["answer"])
    print("\nSources:")
    for source in result["sources"]:
        print(f"{source.get('company')} | {source.get('year')} | {source.get('section')} | {source.get('chunk_id')}")


def run_chunk_stage(report_name, titles=None, rebuild=False, workers=None):
    count = chunk_report(report_name, titles=titles, workers=workers, reuse_existing=not rebuild)
    state = PipelineState(report_name)
    if titles is None:
        state.set_chunk_count(count)
        state.mark_completed("chunking")
        state.reset_from("enrichment")
    return count


def run_enrichment_stage(report_name, titles=None, workers=None):
    count = enrich_report(report_name, titles=titles, workers=workers)
    state = PipelineState(report_name)
    if titles is None:
        state.set_enrichment_count(count)
        state.mark_completed("enrichment")
        state.reset_from("opensearch_ingestion")
    return count


def main():
    parser = argparse.ArgumentParser(description="Annual report ingestion and RAG pipeline")
    commands = parser.add_subparsers(dest="command", required=True)

    ingest_parser = commands.add_parser("ingest", help="Run the complete ingestion pipeline for a PDF")
    ingest_parser.add_argument("pdf_path", help="Path to annual report PDF")

    ask_parser = commands.add_parser("ask", help="Ask a question against indexed reports")
    ask_parser.add_argument("question", help="Question to ask")

    chunk_parser = commands.add_parser("chunk", help="Run or retry semantic chunking for an extracted report")
    chunk_parser.add_argument("report", help="Report name, for example asiri_2025")
    chunk_parser.add_argument("--titles", nargs="+", help="Only process specific subsection titles")
    chunk_parser.add_argument("--workers", type=int, help="Override chunking worker count")
    chunk_parser.add_argument("--rebuild", action="store_true", help="Rebuild selected chunks instead of reusing successful existing outputs")

    enrich_parser = commands.add_parser("enrich", help="Run or retry chunk enrichment")
    enrich_parser.add_argument("report", help="Report name, for example asiri_2025")
    enrich_parser.add_argument("--titles", nargs="+", help="Only process specific subsection titles")
    enrich_parser.add_argument("--workers", type=int, help="Override enrichment worker count")

    validate_parser = commands.add_parser("validate", help="Validate enriched documents without embedding or indexing")
    validate_parser.add_argument("report", help="Report name, for example asiri_2025")

    reset_parser = commands.add_parser("reset", help="Reset pipeline state from a step without deleting output files")
    reset_parser.add_argument("report", help="Report name, for example asiri_2025")
    reset_parser.add_argument("step", choices=PipelineState.STEPS)

    args = parser.parse_args()

    if args.command == "ingest":
        run_pipeline(args.pdf_path)
    elif args.command == "ask":
        run_inference(args.question)
    elif args.command == "chunk":
        run_chunk_stage(args.report, titles=args.titles, rebuild=args.rebuild, workers=args.workers)
    elif args.command == "enrich":
        run_enrichment_stage(args.report, titles=args.titles, workers=args.workers)
    elif args.command == "validate":
        ingest_enriched_chunks_to_opensearch(args.report, validate_only=True)
    elif args.command == "reset":
        PipelineState(args.report).reset_from(args.step)
        print(f"Reset '{args.report}' from step: {args.step}")


if __name__ == "__main__":
    main()
