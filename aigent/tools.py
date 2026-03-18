from google.genai.types import FunctionDeclaration, Schema, Tool, Type

ASK_AI_TOOL = Tool(
    function_declarations=[
        FunctionDeclaration(
            name="ask_default_ai",
            description=(
                "Delegate a prompt to the stronger default AI model (gemini-2.5-flash with search). "
                "Returns the prompt and the model's response. "
                "Set with_codebase=true to include the full userbot project codebase as context."
            ),
            parameters=Schema(
                type=Type.OBJECT,
                properties={
                    "prompt": Schema(
                        type=Type.STRING,
                        description="The prompt to send to the default AI model.",
                    ),
                    "with_codebase": Schema(
                        type=Type.BOOLEAN,
                        description="If true, the full project codebase is included as context for the query.",
                    ),
                },
                required=["prompt"],
            ),
        )
    ]
)

CREATE_FILE_TOOL = Tool(
    function_declarations=[
        FunctionDeclaration(
            name="create_file",
            description=(
                "Create a file at the given path relative to the project root. "
                "Works for any file type. The file is also uploaded to the chat."
            ),
            parameters=Schema(
                type=Type.OBJECT,
                properties={
                    "filename": Schema(
                        type=Type.STRING,
                        description="File path relative to project root (e.g. 'app/utils/helper.py', 'data.json').",
                    ),
                    "content": Schema(
                        type=Type.STRING,
                        description="The full content of the file.",
                    ),
                },
                required=["filename", "content"],
            ),
        )
    ]
)

UPLOAD_FILE_TOOL = Tool(
    function_declarations=[
        FunctionDeclaration(
            name="upload_file",
            description="Upload an existing file from the project to the Telegram chat.",
            parameters=Schema(
                type=Type.OBJECT,
                properties={
                    "filepath": Schema(
                        type=Type.STRING,
                        description="File path relative to project root (e.g. 'app/modules/aigent/config.py').",
                    ),
                },
                required=["filepath"],
            ),
        )
    ]
)

READ_FILE_TOOL = Tool(
    function_declarations=[
        FunctionDeclaration(
            name="read_file",
            description="Read the contents of a file from the project. Use before editing to see current state.",
            parameters=Schema(
                type=Type.OBJECT,
                properties={
                    "filepath": Schema(
                        type=Type.STRING,
                        description="File path relative to project root.",
                    ),
                },
                required=["filepath"],
            ),
        )
    ]
)

EDIT_FILE_TOOL = Tool(
    function_declarations=[
        FunctionDeclaration(
            name="edit_file",
            description=(
                "Edit an existing file. You provide the filepath and a natural language instruction "
                "describing the changes. The stronger default model generates the precise edits, "
                "shows a diff to the user for approval, and applies on confirmation."
            ),
            parameters=Schema(
                type=Type.OBJECT,
                properties={
                    "filepath": Schema(
                        type=Type.STRING,
                        description="File path relative to project root.",
                    ),
                    "instruction": Schema(
                        type=Type.STRING,
                        description="Natural language description of what to change in the file.",
                    ),
                },
                required=["filepath", "instruction"],
            ),
        )
    ]
)

AIGENT_TOOLS = [
    ASK_AI_TOOL,
    CREATE_FILE_TOOL,
    UPLOAD_FILE_TOOL,
    READ_FILE_TOOL,
    EDIT_FILE_TOOL,
]
