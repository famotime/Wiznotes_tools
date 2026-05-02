from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT.parent / "account" / "web_accounts.json"
DEFAULT_EXPORT_DIR = PROJECT_ROOT / "export_wiznotes" / "output"
DEFAULT_LOG_DIR = PROJECT_ROOT / "export_wiznotes" / "logs"
DEFAULT_MAX_WORKERS = 10
DEFAULT_MAX_NOTES = None
DEFAULT_REEXPORT_DOT_FILES = False
DEFAULT_EXCLUDE_FOLDERS = ["/My Drafts/", "/My Emails/"]
