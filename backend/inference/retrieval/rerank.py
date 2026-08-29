import os

from openai import OpenAI

from config.config import CONFIG


RERANK_CONFIG = CONFIG["reranker"]
RETRIEVAL_CONFIG = CONFIG["retrieval"]

RERANK_MODEL = RERANK_CONFIG["model"]
RERANK_TOP_K = int(RETRIEVAL_CONFIG["rerank_top_k"])


def rerank(query, candidates):
    candidates = [
        item for item in candidates
        if item.get("text")
    ]

    if not candidates:
        return []

    api_key = os.getenv("DASHSCOPE_API_KEY")
    workspace_id = os.getenv("DASHSCOPE_WORKSPACE_ID")

    if not api_key:
        raise ValueError("DASHSCOPE_API_KEY is not set")

    if not workspace_id:
        raise ValueError("DASHSCOPE_WORKSPACE_ID is not set")

    client = OpenAI(
        api_key=api_key,
        base_url=(
            f"https://{workspace_id}."
            "ap-southeast-1.maas.aliyuncs.com/compatible-api/v1"
        ),
    )

    top_k = min(
        RERANK_TOP_K,
        len(candidates),
    )

    response = client.post(
        "/reranks",
        body={
            "model": RERANK_MODEL,
            "query": query,
            "documents": [
                item["text"]
                for item in candidates
            ],
            "top_n": top_k,
        },
        cast_to=object,
    )

    ranked = []

    for result in response["results"]:
        item = dict(
            candidates[result["index"]]
        )

        item["rerank_score"] = float(
            result["relevance_score"]
        )

        ranked.append(item)

    return ranked