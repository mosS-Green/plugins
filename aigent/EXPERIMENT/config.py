import os

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = os.getcwd()

GEN_TEMP_DIR = os.path.join(PROJECT_ROOT, "app", "plugins", "temp", "gen")
os.makedirs(GEN_TEMP_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

GEN_MODEL = "gemini-3-flash-preview"

# ---------------------------------------------------------------------------
# API Key — reuse autobot's key for gemini-cli
# ---------------------------------------------------------------------------

GEMINI_API_KEY = os.getenv("AUTOBOT_GEMINI_API_KEY", "")

# ---------------------------------------------------------------------------
# Timeouts
# ---------------------------------------------------------------------------

CLI_TIMEOUT = 120  # seconds to wait for gemini-cli to finish
REVIEW_TIMEOUT = 120  # seconds to wait for user review reply
