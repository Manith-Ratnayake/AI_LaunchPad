import json

from config.config import CONFIG
from services.model_client import call_model
from utils.paths import PROMPT_ROOT


QUERY_CONFIG = CONFIG["query_transform"]
QUERY_MODEL = QUERY_CONFIG["model"]
QUERY_THINKING = QUERY_CONFIG["thinking"]

QUERY_PROMPT = (PROMPT_ROOT / "query_transform_prompt.txt").read_text(encoding="utf-8")


def process_query(user_query):
    prompt = (
        f"{QUERY_PROMPT.rstrip()}"
        f"\n\nUSER QUESTION\n{user_query}"
    )

    response = call_model(
        prompt,
        QUERY_MODEL,
        QUERY_THINKING,
    )

    result = json.loads(response)
    subqueries = result.get("subqueries")

    if not isinstance(subqueries, list) or not subqueries:
        raise ValueError("Query processing returned no subqueries")

    return result