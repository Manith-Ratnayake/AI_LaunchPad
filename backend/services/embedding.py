from array import array

from config.config import CONFIG
from services.model_client import call_embedding_model


EMBEDDING_CONFIG = CONFIG["embedding"]

EMBEDDING_MODEL = EMBEDDING_CONFIG["model"]
EMBEDDING_DIMENSION = int(EMBEDDING_CONFIG["dimension"])
EMBEDDING_BATCH_SIZE = int(EMBEDDING_CONFIG["batch_size"])


def as_float32_list(values):
    return array("f", values).tolist()


def embed_texts(texts):
    cleaned = [str(text).strip() for text in texts]

    if not cleaned:
        return []

    for index, text in enumerate(cleaned):
        if not text:
            raise ValueError(
                f"Cannot embed empty text. Text index: {index}"
            )

    vectors = []

    for start in range(0, len(cleaned), EMBEDDING_BATCH_SIZE):
        batch = cleaned[start:start + EMBEDDING_BATCH_SIZE]

        embeddings = call_embedding_model(
            batch,
            EMBEDDING_MODEL,
            EMBEDDING_DIMENSION,
        )

        vectors.extend(
            as_float32_list(embedding)
            for embedding in embeddings
        )

    return vectors