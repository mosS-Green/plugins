from google.genai.types import Tool, FunctionDeclaration, Schema, Type

MUSIC_TOOL = Tool(
    function_declarations=[
        FunctionDeclaration(
            name="get_ytm_link",
            description="Finds a YouTube Music link for the given song name.",
            parameters=Schema(
                type=Type.OBJECT,
                properties={
                    "song_name": Schema(
                        type=Type.STRING,
                        description="The name of the song to search for."
                    )
                },
                required=["song_name"]
            )
        )
    ]
)

LIST_TOOL = Tool(
    function_declarations=[
        FunctionDeclaration(
            name="get_my_list",
            description="Retrieve the items in my reminder list.",
            parameters=Schema(
                type=Type.OBJECT,
                properties={}, # No parameters needed from AI, we inject user_id
            )
        )
    ]
)
