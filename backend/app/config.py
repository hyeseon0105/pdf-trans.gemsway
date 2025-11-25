import os
from pathlib import Path
from typing import List

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
STORAGE_DIR = ROOT_DIR / "app" / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
TRANSLATED_DIR = STORAGE_DIR / "translated"
PREVIEWS_DIR = STORAGE_DIR / "previews"
ASSETS_DIR = ROOT_DIR / "assets"

for directory in (STORAGE_DIR, UPLOADS_DIR, TRANSLATED_DIR, PREVIEWS_DIR, ASSETS_DIR):
    directory.mkdir(exist_ok=True, parents=True)

# 로고 이미지 경로 (환경 변수로 설정 가능, 기본값: assets/logo.png)
LOGO_PATH = Path(os.environ.get("LOGO_PATH", str(ASSETS_DIR / "logo.png")))

ALLOWED_ORIGINS: List[str] = [
	os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173"),
]

# Optional: Force a Windows Korean font path for ReportLab if present
WINDOWS_MALGUN_TTF = os.environ.get("WINDOWS_MALGUN_TTF", r"C:\Windows\Fonts\malgun.ttf")


