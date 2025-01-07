import google.generativeai as genai
from app.plugins.ai.models import get_response_text, basic_check, SAFETY_SETTINGS

GENERATION_CONFIG = {"temperature": 1, "max_output_tokens": 3096}

MEDIA_MODEL = genai.GenerativeModel(
    model_name="gemini-2.0-flash-exp",
    generation_config=GENERATION_CONFIG,
    system_instruction="Answer concisely and accurately, maintain a natural tone.",
    safety_settings=SAFETY_SETTINGS,
)
