from config.config import CONFIG
from services.embedding import embed_texts
from services.opensearch_client import DEFAULT_INDEX, get_opensearch_client


RETRIEVAL_CONFIG = CONFIG["retrieval"]

SEMANTIC_TOP_K = int(RETRIEVAL_CONFIG["search_semantic_top_k"])
KEYWORD_TOP_K = int(RETRIEVAL_CONFIG["search_keyword_top_k"])


def _filter_clauses(subquery):
    clauses = []

    if subquery.get("company") is not None:
        clauses.append({"term": {"company": subquery["company"]}})

    if subquery.get("year") is not None:
        clauses.append({"term": {"year": int(subquery["year"])}})

    return clauses


def _format_hits(response, search_type):
    results = []

    for hit in response.get("hits", {}).get("hits", []):
        source = dict(hit.get("_source") or {})

        source.pop("embedding", None)
        text = source.pop("source_text", None)
        source.pop("search_text", None)

        results.append(
            {
                "key": source.get("doc_key") or hit.get("_id"),
                "search_type": search_type,
                "search_score": hit.get("_score"),
                "text": text,
                "metadata": source,
            }
        )

    return results


def semantic_search(client, query, filters):
    knn = {
        "vector": embed_texts([query])[0],
        "k": SEMANTIC_TOP_K,
    }

    if filters:
        knn["filter"] = {
            "bool": {
                "filter": filters,
            }
        }

    body = {
        "size": SEMANTIC_TOP_K,
        "_source": {"excludes": ["embedding"]},
        "query": {
            "knn": {
                "embedding": knn,
            }
        },
    }

    response = client.search(
        index=DEFAULT_INDEX,
        body=body,
    )

    return _format_hits(response, "semantic")


def keyword_search(client, query, filters):
    bool_query = {
        "must": [
            {
                "match": {
                    "search_text": query,
                }
            }
        ]
    }

    if filters:
        bool_query["filter"] = filters

    body = {
        "size": KEYWORD_TOP_K,
        "_source": {"excludes": ["embedding"]},
        "query": {
            "bool": bool_query,
        },
    }

    response = client.search(
        index=DEFAULT_INDEX,
        body=body,
    )

    return _format_hits(response, "keyword")


def retrieve_subquery(subquery):
    query = subquery["query"]
    filters = _filter_clauses(subquery)

    client, _ = get_opensearch_client()

    semantic_results = semantic_search(
        client,
        query,
        filters,
    )

    keyword_results = keyword_search(
        client,
        query,
        filters,
    )

    unique = {}

    for item in semantic_results + keyword_results:
        unique.setdefault(item["key"], item)

    return list(unique.values())