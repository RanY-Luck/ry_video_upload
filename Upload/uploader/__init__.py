from pathlib import Path

from Upload.conf import BASE_DIR

Path(BASE_DIR / "cookies").mkdir(exist_ok=True)