import os
import sys
import tempfile
from pathlib import Path

# Force local single-user mode and no LLM before the app is imported
# (load_dotenv never overrides variables that are already set).
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""
os.environ["SUPABASE_SERVICE_KEY"] = ""
os.environ["OPENAI_API_KEY"] = ""
os.environ["LLM_API_KEY"] = ""
os.environ["LOCAL_DATA_DIR"] = tempfile.mkdtemp(prefix="dressme-test-")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
