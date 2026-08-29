# Annual Report Financial Assistant

This project turns corporate annual reports into a searchable knowledge base and uses a retrieval augmented generation pipeline to answer questions from the reports.

The main idea is not to treat an annual report as one large document. The pipeline first reconstructs the report structure, divides each subsection into meaningful retrieval units, enriches those units with searchable metadata, and then indexes them for hybrid retrieval.

```text
Annual Report PDF
        ↓
Page level multimodal extraction
        ↓
Marked report text with page and block boundaries
        ↓
TOC + printed page number detection
        ↓
Subsection reconstruction
        ↓
Semantic subsection chunking
        ↓
Retrieval focused chunk enrichment
        ↓
Embedding generation + OpenSearch indexing
        ↓
                Knowledge Base
                      ↓
User Question → Query transformation
                      ↓
          Semantic + keyword retrieval
                      ↓
                  Reranking
                      ↓
          Grounded answer + sources
```

## How an annual report becomes searchable

### 1. Page level extraction

The pipeline starts from the original PDF rather than relying only on the PDF text layer. Each page is rendered as an image and sent to a multimodal model for extraction.

This is important for annual reports because useful information is often spread across normal paragraphs, multi column layouts, tables, charts, headings, and visually structured pages.

Extraction is performed independently for each PDF page so failed pages can be identified and retried without rebuilding the complete report.

### 2. Rebuilding the report as traceable text

The extracted pages are combined into one report representation.

During this stage the system adds physical page markers and block markers such as:

```text
[P72]

[B1 | P72]
STATEMENT OF CASH FLOWS

[B2 | P72]
...
```

These markers preserve the connection between later retrieval chunks and the original report location. They also give the chunking stage stable boundaries instead of asking the model to rewrite or split arbitrary text spans.

### 3. Recovering document hierarchy

Annual reports usually contain printed page numbers that do not match their physical PDF page numbers because of covers, introductory pages, and other front matter.

The pipeline therefore performs two separate document understanding tasks on the opening pages:

1. Table of Contents identification extracts the report's listed sections and subsections.
2. Printed page number identification determines the relationship between printed report pages and physical PDF pages.

The two results are combined to map each TOC subsection to the physical location where it starts in the PDF.

This produces a subsection map that becomes the structural backbone for chunking.

### 4. Semantic chunking inside each subsection

Chunking is performed subsection by subsection rather than over the entire report at once.

The model receives the candidate subsection content and decides where meaningful retrieval units should begin. Existing source blocks remain indivisible, consecutive, and traceable to their original pages.

The goal is not fixed token sized chunks. A chunk should represent a self contained piece of information that could reasonably answer a user question. A financial statement may remain one chunk, while a long management discussion may naturally become several chunks.

Chunk boundaries are validated before they are accepted. If a model response is invalid, the stage retries according to the configured pipeline retry policy.

### 5. Retrieval focused enrichment

Each accepted chunk is enriched in a separate model call while its boundary remains unchanged.

The enrichment layer identifies the content type and creates metadata that helps retrieval understand what the chunk contains. Depending on the content, this can include a retrieval description, keywords, table row and column concepts, units, chart axes, series, and categories.

Structured content is also classified as numerical or semantic where applicable.

The important distinction is that the original chunk remains the source of truth. Enrichment does not replace the source text; it adds a compact semantic representation that makes the source easier to find.

### 6. Building the OpenSearch document

Before indexing, each chunk is combined with its report context and enrichment metadata.

The searchable document contains information such as the company, year, section, subsection, chunk type, page range, block references, retrieval description, keywords, structured terms, and original source text.

A separate embedding text is constructed from the descriptive metadata rather than embedding only raw extracted text. This gives the vector representation explicit context such as which company, year, section, and financial concept the chunk belongs to.

The current embedding pipeline uses `text-embedding-v4` with 1024 dimensional vectors.

Each enriched chunk is then stored in OpenSearch with both:

1. A vector embedding for semantic similarity search.
2. Searchable text for lexical keyword retrieval.

The original chunk text is stored alongside the index metadata so retrieved results can still be passed to the answer model as evidence.

## How a question becomes an answer

### 7. Query transformation

A user question is first converted into one or more search friendly subqueries.

This stage is especially useful for comparison questions. A question involving multiple companies or multiple years is decomposed so each retrieval query targets one company and one year at a time.

For example, a comparison across three years can become three focused retrieval operations rather than one broad search request.

The query plan also extracts company and year metadata that can be applied as OpenSearch filters.

### 8. Hybrid retrieval

Every subquery is searched in two ways.

Semantic retrieval embeds the subquery and performs vector search against the chunk embeddings.

Keyword retrieval searches the indexed search text and helps recover exact financial terminology, labels, names, and phrases that vector search may not rank strongly enough.

The two candidate sets are merged and deduplicated before reranking.

### 9. Reranking

The retrieved candidate chunks are passed through `qwen3-rerank`.

Reranking evaluates the actual relationship between the subquery and each candidate and produces a smaller, more relevant context set for answer generation.

When a question contains multiple subqueries, the final contexts are combined using round robin selection so one part of a comparison does not consume the entire context window.

### 10. Grounded answer generation

The final answer model receives the original user question together with the highest ranked source chunks and their metadata.

The generation prompt requires the answer to use only the supplied annual report context. Supporting statements are cited using the retrieved source labels, and the system is instructed to say when the retrieved evidence is insufficient rather than inventing missing information.

The API returns the generated answer together with the query plan, retrieval information, and source metadata used to produce it.

## Pipeline state and retries

Each report has a saved pipeline state covering extraction, text combination, TOC identification, page number identification, subsection construction, chunking, enrichment, and OpenSearch ingestion.

Completed stages can be reused instead of rerunning the complete pipeline. Failed chunking and enrichment model outputs are retried using the retry settings in `config/config.yaml`, while individual stages can also be rerun when necessary.

This makes the ingestion process resumable, which is useful for large annual reports where repeating every model call after one failure would be unnecessarily expensive.

## Main project flow

```text
ingestion/
    content_extraction/     PDF pages → extracted report text
    document_hierarchy/    TOC + page mapping → subsections
    chunking/               subsections → semantic chunks → enrichment
    indexing/               enriched chunks → embeddings → OpenSearch

inference/
    query_transform.py      user question → retrieval plan
    retrieval/              semantic + keyword search → reranking
    generate_answer.py      retrieved evidence → final answer
    orchestrator.py         connects the complete inference flow

services/
    model_client.py         model access
    embedding.py            embedding generation
    opensearch_client.py    OpenSearch connection

config/
    config.yaml             models, retrieval limits, workers, retries and index settings
    prompts/                prompts used by each model driven stage
```

## Running the pipeline

Environment variables are defined using `.env`. The included `.env.example` shows the expected variables without containing credentials.

Install the Python dependencies:

```bash
pip install -r requirements.txt
```

Run the complete ingestion pipeline for an annual report:

```bash
python main.py ingest path/to/annual_report.pdf
```

Ask a question against reports already indexed in OpenSearch:

```bash
python main.py ask "What was Asiri's revenue in 2025?"
```

The same inference flow is exposed through FastAPI. The main endpoint is:

```text
POST /query
```

with a request body containing the user's question.

## Configuration

The pipeline is intentionally configuration driven. `config/config.yaml` controls the model used at each stage, extraction resolution and concurrency, chunking and enrichment workers, retry behaviour, embedding settings, retrieval candidate counts, reranking depth, AWS settings, and the OpenSearch index.

This allows the extraction, retrieval, or model configuration to change without changing the overall pipeline architecture.
