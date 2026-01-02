from google.genai.types import (
    Tool,
    FunctionDeclaration,
    Schema,
    Type
)
from .lastfm_tool import get_my_lastfm_status

# Mapping of function names to actual Python callables
SANDBOX_FUNCTIONS = {
    "get_my_lastfm_status": get_my_lastfm_status,
}

# Definitions for Gemini
SANDBOX_TOOLS = [
    Tool(
        function_declarations=[
            FunctionDeclaration(
                name="get_my_lastfm_status",
                description="Gets the song the user is currently listening to or last listened to on Last.fm. Use this when the user asks 'what am I playing', 'my status', etc.",
                parameters=Schema(
                    type=Type.OBJECT,
                    properties={
                        "user_id": Schema(
                            type=Type.INTEGER,
                            description="The Telegram User ID of the user. If not known, omit it (system will inject it)."
                        ),
                    },
                    required=[]  # user_id is optional as we'll inject it if missing
                )
            )
        ]
    )
]
