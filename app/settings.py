from dataclasses import dataclass
import json
import os
from pathlib import Path
from uuid import uuid4

from dotenv import dotenv_values
import yaml

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    data_dir: Path = ROOT / "data"
    demo_mode: bool = True

    @property
    def online_ready(self):
        # Compatibility indicator only. No provider or network path exists.
        return False

    def save_preferences(self):
        self.data_dir.mkdir(parents=True,exist_ok=True)
        destination=self.data_dir/'preferences.json'
        temporary=destination.with_suffix('.'+uuid4().hex+'.tmp')
        try:
            temporary.write_text(json.dumps({'version':1,'demo_mode':self.demo_mode}),encoding='utf-8')
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)


def load_settings(env_path: Path | None = None) -> Settings:
    values=dotenv_values(env_path or ROOT / '.env')
    directory=Path(os.getenv('APP_DATA_DIR') or values.get('APP_DATA_DIR') or ROOT/'data').resolve()
    demo=True
    try:
        preferences=json.loads((directory/'preferences.json').read_text(encoding='utf-8'))
        if isinstance(preferences.get('demo_mode'),bool):
            demo=preferences['demo_mode']
    except (OSError,ValueError,AttributeError):
        pass
    # Legacy AI_* keys have no effect and are never copied to Settings.
    return Settings(data_dir=directory,demo_mode=demo)


def load_yaml(name: str):
    return yaml.safe_load((ROOT / "config" / name).read_text(encoding="utf-8"))
