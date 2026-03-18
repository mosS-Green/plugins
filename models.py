from google.genai.types import GenerateContentConfig, ThinkingConfig

from app import Message
from app.plugins.ai.gemini import Response, async_client
from app.plugins.ai.gemini.configs import SAFETY_SETTINGS, SEARCH_TOOLS
from app.plugins.ai.gemini.utils import create_prompts

from .prompts import SYSTEM_PROMPTS


class ModelNames:
    LEAF = "gemini-3-flash-preview"
    DEFAULT = "gemini-2.5-flash"
    THINK = "gemini-3-flash-preview"
    QUICK = "gemini-2.5-flash-lite"


class ModelConfigs:
    LEAF = GenerateContentConfig(
        candidate_count=1,
        system_instruction=SYSTEM_PROMPTS["LEAF"],
        temperature=1.0,
        max_output_tokens=8192,
        safety_settings=SAFETY_SETTINGS,
        response_modalities=["Text"],
        tools=[],
        thinking_config=ThinkingConfig(thinking_budget=0),
    )

    DEFAULT = GenerateContentConfig(
        candidate_count=1,
        system_instruction=SYSTEM_PROMPTS["DEFAULT"],
        temperature=1.0,
        max_output_tokens=8192,
        safety_settings=SAFETY_SETTINGS,
        response_modalities=["Text"],
        tools=SEARCH_TOOLS,
        thinking_config=ThinkingConfig(thinking_budget=0),
    )

    THINK = GenerateContentConfig(
        candidate_count=1,
        system_instruction=SYSTEM_PROMPTS["THINK"],
        temperature=0.8,
        max_output_tokens=60000,
        safety_settings=SAFETY_SETTINGS,
        response_modalities=["Text"],
        tools=[],
    )

    QUICK = GenerateContentConfig(
        candidate_count=1,
        system_instruction=SYSTEM_PROMPTS["QUICK"],
        temperature=0.7,
        max_output_tokens=8192,
        safety_settings=SAFETY_SETTINGS,
        response_modalities=["Text"],
        tools=[],
    )


CMD_MODEL_DICT = {
    "r": "DEFAULT",
    "rx": "LEAF",
    "f": "QUICK",
    "yt": "QUICK",
    "aig": "QUICK",
    "sm": "DEFAULT",
}


async def get_model_and_config(model_name: str | None = None) -> dict:
    model = getattr(ModelNames, model_name, ModelNames.DEFAULT)
    config = getattr(ModelConfigs, model_name, ModelConfigs.DEFAULT)
    return {"model": model, "config": config}


async def ask_ai(
    message: Message | None = None,
    model_name: str | None = None,
    prompt: str | list | None = None,
):
    try:
        if prompt:
            prompts = prompt if isinstance(prompt, list) else [prompt]
        else:
            prompts = await create_prompts(message=message)
            
    except AssertionError:
        return

    kwargs = get_model_and_config(model_name=model_name)

    response = await async_client.models.generate_content(contents=prompts, **kwargs)

    response = Response(response)

    return response.quoted_text()
