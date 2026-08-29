from services.embedding import EMBEDDING_DIMENSION, EMBEDDING_MODEL


def index_body():
    return {
        "settings": {"index.knn": True},
        "mappings": {
            "properties": {
                "doc_key": {"type": "keyword"},
                "report": {"type": "keyword"},
                "company": {"type": "keyword"},
                "year": {"type": "integer"},
                "section_category": {"type": "keyword"},
                "section_start_page": {"type": "integer"},
                "subsection": {"type": "keyword"},
                "subsection_name": {"type": "keyword"},
                "subsection_start_page": {"type": "integer"},
                "subsection_printed_page": {"type": "integer"},
                "subsection_start_block": {"type": "integer"},
                "chunk_id": {"type": "keyword"},
                "chunk_number": {"type": "integer"},
                "chunk_type": {"type": "keyword"},
                "content_category": {"type": "keyword"},
                "page_start": {"type": "integer"},
                "page_end": {"type": "integer"},
                "blocks": {"type": "object"},
                "description": {"type": "text"},
                "keywords": {"type": "keyword"},
                "rows": {"type": "keyword"},
                "columns": {"type": "keyword"},
                "units": {"type": "keyword"},
                "x_axis": {"type": "keyword"},
                "y_axis": {"type": "keyword"},
                "series": {"type": "keyword"},
                "categories": {"type": "keyword"},
                "embedding_model": {"type": "keyword"},
                "embedding_text": {"type": "text", "index": False},
                "search_text": {"type": "text"},
                "source_text": {"type": "text", "index": False},
                "embedding": {
                    "type": "knn_vector",
                    "dimension": EMBEDDING_DIMENSION,
                    "space_type": "cosinesimil",
                },
            }
        },
    }


def ensure_index(client, index_name):
    if not client.indices.exists(index=index_name):
        print(f"Creating OpenSearch index: {index_name}")
        client.indices.create(index=index_name, body=index_body())
        return

    mapping = client.indices.get_mapping(index=index_name)
    properties = mapping[index_name].get("mappings", {}).get("properties", {})
    embedding = properties.get("embedding", {})

    if embedding.get("type") != "knn_vector":
        raise ValueError(f"Index '{index_name}' embedding field is not knn_vector.")

    dimension = embedding.get("dimension")
    if int(dimension or 0) != EMBEDDING_DIMENSION:
        raise ValueError(f"Index dimension is {dimension}, but {EMBEDDING_MODEL} requires {EMBEDDING_DIMENSION}.")
