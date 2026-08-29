import json

from config.config import CONFIG
from services.model_client import call_model
from utils.paths import PROMPT_ROOT


ANSWER_CONFIG = CONFIG["answer"]

ANSWER_MODEL = ANSWER_CONFIG["model"]
ANSWER_THINKING = ANSWER_CONFIG["thinking"]

ANSWER_PROMPT = (
    PROMPT_ROOT / "generate_answer_prompt.txt"
).read_text(encoding="utf-8")


def generate(question, contexts, query_plan=None):
    context_text = []

    for index, item in enumerate(contexts, start=1):
        metadata = item.get("metadata", {})

        source = {
            "report": metadata.get("report"),
            "company": metadata.get("company"),
            "year": metadata.get("year"),
            "section": metadata.get("section_category"),
            "subsection": metadata.get("subsection_name"),
            "chunk_id": metadata.get("chunk_id"),
        }

        context_text.append(
            f"SOURCE {index}\n"
            f"METADATA: {json.dumps(source, ensure_ascii=False)}\n"
            f"TEXT:\n{item.get('text', '')}"
        )

    prompt = (
        f"{ANSWER_PROMPT.rstrip()}"
        f"\n\nQUESTION\n{question}"
        f"\n\nCONTEXT\n{'\n\n'.join(context_text)}"
    )

    return call_model(
        prompt,
        ANSWER_MODEL,
        ANSWER_THINKING,
    )