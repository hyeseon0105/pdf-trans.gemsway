import os
from pathlib import Path
from typing import List

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
STORAGE_DIR = ROOT_DIR / "app" / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
TRANSLATED_DIR = STORAGE_DIR / "translated"

for directory in (STORAGE_DIR, UPLOADS_DIR, TRANSLATED_DIR):
    directory.mkdir(exist_ok=True, parents=True)

ALLOWED_ORIGINS: List[str] = [
	os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173"),
]

# Optional: Force a Windows Korean font path for ReportLab if present
WINDOWS_MALGUN_TTF = os.environ.get("WINDOWS_MALGUN_TTF", r"C:\Windows\Fonts\malgun.ttf")


