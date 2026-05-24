from pathlib import Path
import os


def load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
        return
    except ModuleNotFoundError:
        pass

    env_path = Path(".env")
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)

