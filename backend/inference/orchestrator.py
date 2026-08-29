from config.config import CONFIG
from inference.generate_answer import generate
from inference.query_transform import process_query
from inference.retrieval.opensearch_search import retrieve_subquery
from inference.retrieval.rerank import rerank


RERANK_TOP_K = int(CONFIG["retrieval"]["rerank_top_k"])


def deduplicate(results):
    unique = {}

    for item in results:
        key = item["key"]

        if key not in unique:
            unique[key] = item
            continue

        if item.get("rerank_score", 0) > unique[key].get("rerank_score", 0):
            unique[key] = item

    return list(unique.values())


def round_robin(groups, limit):
    merged = []
    index = 0

    while len(merged) < limit:
        added = False

        for group in groups:
            if index < len(group):
                merged.append(group[index])
                added = True

            if len(merged) >= limit:
                break

        if not added:
            break

        index += 1

    return deduplicate(merged)[:limit]


def answer_question(question):
    if not question or not str(question).strip():
        raise ValueError("Question is required")

    question = str(question).strip()

    query_plan = process_query(question)

    ranked_groups = []
    retrieval = []

    for subquery in query_plan["subqueries"]:
        candidates = retrieve_subquery(subquery)

        ranked = rerank(
            subquery["query"],
            candidates,
        )

        ranked_groups.append(ranked)

        retrieval.append(
            {
                "subquery": subquery,
                "candidate_count": len(candidates),
                "reranked_count": len(ranked),
            }
        )

    contexts = round_robin(
        ranked_groups,
        RERANK_TOP_K,
    )

    answer = generate(
        question,
        contexts,
    )

    sources = []

    for item in contexts:
        metadata = item.get("metadata", {})

        sources.append(
            {
                "key": item.get("key"),
                "score": item.get("rerank_score"),
                "report": metadata.get("report"),
                "company": metadata.get("company"),
                "year": metadata.get("year"),
                "section": metadata.get("section_category"),
                "subsection": metadata.get("subsection"),
                "chunk_id": metadata.get("chunk_id"),
            }
        )

    return {
        "answer": answer,
        "query_plan": query_plan,
        "retrieval": retrieval,
        "sources": sources,
    }