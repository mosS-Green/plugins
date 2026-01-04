from app.plugins.ai.gemini.utils import run_basic_check
from app.modules.ai_sandbox.tools import MUSIC_TOOL, LIST_TOOL
from google.genai.types import (
    DynamicRetrievalConfig,
    GenerateContentConfig,
    GoogleSearchRetrieval,
    SafetySetting,
    UrlContext,
    Tool,
    ThinkingConfig,
)
from .prompts import SYSTEM_PROMPTS

safety = [
    SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
    SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
    SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF"),
    SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
    SafetySetting(category="HARM_CATEGORY_CIVIC_INTEGRITY", threshold="OFF"),
]


def create_config(
    model,
    instruction: str | None = None,
    temp: float | None = None,
    tokens: int | None = None,
    search: list | None = None,
    modals: list | None = None,
    mime_type: str | None = None,
    think: int | None = None,
    **kwargs,
):
    """Creates a model configuration dict for Gemini API calls."""
    return {
        "model": model,
        "config": GenerateContentConfig(
            candidate_count=1,
            system_instruction=instruction,
            temperature=temp,
            max_output_tokens=tokens,
            safety_settings=safety,
            response_modalities=modals,
            response_mime_type=mime_type,
            tools=search,
            thinking_config=think,
            **kwargs,
        ),
    }


SEARCH_TOOL = [
    Tool(
        google_search=GoogleSearchRetrieval(
            dynamic_retrieval_config=DynamicRetrievalConfig(dynamic_threshold=0.6)
        )
    ),
    Tool(
        url_context=UrlContext(),
    ),
]


MODEL = {
    "LEAF": create_config(
        "gemini-3-flash-preview",
        SYSTEM_PROMPTS["LEAF"],
        1.0,
        8192,
        search=[],
        think=ThinkingConfig(thinking_budget=0),
    ),
    "FUNC": create_config(
        "gemini-flash-latest",
        SYSTEM_PROMPTS["FUNC"],
        0.8,
        8192,
        search=[MUSIC_TOOL, LIST_TOOL],
        think=ThinkingConfig(thinking_budget=0),
    ),
    "DEFAULT": create_config(
        "gemini-flash-latest",
        SYSTEM_PROMPTS["DEFAULT"],
        1.0,
        8192,
        search=SEARCH_TOOL,
        think=ThinkingConfig(thinking_budget=0),
    ),
    "THINK": create_config(
        "gemini-3-flash-preview",
        SYSTEM_PROMPTS["THINK"],
        0.8,
        60000,
        search=[],
    ),
    "QUICK": create_config(
        "gemini-flash-lite-latest",
        SYSTEM_PROMPTS["QUICK"],
        0.6,
        8192,
        search=[],
    ),
}
