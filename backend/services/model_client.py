import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from config.config import CONFIG


load_dotenv()

PROVIDER = CONFIG["provider"]
PROVIDER_CONFIG = CONFIG["providers"][PROVIDER]

BASE_URL = PROVIDER_CONFIG["base_url"]
API_KEY_ENV = f"{PROVIDER.upper()}_API_KEY"
API_KEY = os.getenv(API_KEY_ENV)

if not API_KEY:
    raise ValueError(f"{API_KEY_ENV} is not set.")

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)


def get_extra_body(thinking):
    if PROVIDER == "dashscope":
        return {"enable_thinking": thinking}
    if PROVIDER == "openrouter":
        return {"reasoning": {"enabled": thinking}}
    return {}


def get_reasoning_content(message):
    reasoning = getattr(message, "reasoning_content", None)
    if reasoning:
        return str(reasoning).strip()

    model_extra = getattr(message, "model_extra", None) or {}
    reasoning = model_extra.get("reasoning_content")
    return str(reasoning).strip() if reasoning else ""


def call_chat_model(messages, model, thinking, response_format=None):
    kwargs = {
        "model": model,
        "messages": messages,
        "extra_body": get_extra_body(thinking),
    }
    if response_format is not None:
        kwargs["response_format"] = response_format

    response = client.chat.completions.create(**kwargs)
    message = response.choices[0].message
    content = (message.content or "").strip()

    if not content:
        raise RuntimeError("Model returned empty output")

    return content, get_reasoning_content(message)


def call_model(prompt, model, thinking):
    content, _ = call_chat_model(
        messages=[{"role": "user", "content": prompt}],
        model=model,
        thinking=thinking,
    )
    return content


def call_json_model(system_prompt, user_prompt, model, thinking):
    content, reasoning = call_chat_model(
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
        model=model,
        thinking=thinking,
        response_format={"type": "json_object"},
    )
    return json.loads(content), reasoning, content


def call_vision_model_with_reasoning(image_base64, prompt, model, thinking, mime_type="image/png"):
    return call_chat_model(
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_base64}"}},
                {"type": "text", "text": prompt},
            ],
        }],
        model=model,
        thinking=thinking,
    )


def call_multimodal_json_model(content, model, thinking):
    raw, reasoning = call_chat_model(
        messages=[{"role": "user", "content": content}],
        model=model,
        thinking=thinking,
        response_format={"type": "json_object"},
    )
    return json.loads(raw), reasoning, raw


def call_embedding_model(texts, model, dimension):
    response = client.embeddings.create(
        model=model,
        input=texts,
        dimensions=dimension,
        encoding_format="float",
    )
    return [item.embedding for item in response.data]
