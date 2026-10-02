import json
import os
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path

APP_NAME = 'MuteAIMP'
CONFIG_DIR = Path(os.getenv('LOCALAPPDATA', Path.home())) / APP_NAME
CONFIG_FILE = CONFIG_DIR / 'settings.json'

DEFAULT_SOUND_THRESHOLD_DBFS = -60
DEFAULT_INTERVAL_MS = 500
DEFAULT_RESUME_DELAY_MS = 1000


@dataclass
class Settings:
    enabled: bool = True
    trigger_mode: str = 'media'  # audio / media
    sound_threshold_dbfs: int = DEFAULT_SOUND_THRESHOLD_DBFS
    check_interval_ms: int = DEFAULT_INTERVAL_MS
    resume_after_external: bool = True
    resume_delay_ms: int = DEFAULT_RESUME_DELAY_MS
    pause_when_aimp_volume_zero: bool = False
    resume_when_aimp_volume_restored: bool = True
    filter_mode: str = 'all'  # all / blacklist / whitelist
    whitelist: list[str] = field(default_factory=list)
    blacklist: list[str] = field(default_factory=list)


class SettingsStore:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self.settings = self.load()

    def load(self):
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            base = asdict(Settings())
            base.update(data)
            return Settings(**base)
        except Exception:
            return Settings()

    def save(self):
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix('.tmp')
            tmp.write_text(
                json.dumps(asdict(self.settings), indent=2, ensure_ascii=False),
                encoding='utf-8',
            )
            tmp.replace(self.path)

    def snapshot(self):
        with self.lock:
            return Settings(**asdict(self.settings))

    def update(self, **kwargs):
        with self.lock:
            for key, value in kwargs.items():
                if hasattr(self.settings, key):
                    setattr(self.settings, key, value)
            self.save()


store = SettingsStore(CONFIG_FILE)
stop_event = threading.Event()
state_lock = threading.Lock()
state = {
    'aimp_state': 'Unknown',
    'aimp_volume': None,
    'external_sources': [],
    'status': 'Starting...',
    'external_trigger': False,
    'media_available': False,
    'media_error': ''
}


def set_state(**kwargs):
    with state_lock:
        state.update(kwargs)


def get_state():
    with state_lock:
        return {
            'aimp_state': state['aimp_state'],
            'aimp_volume': state['aimp_volume'],
            'external_sources': list(state['external_sources']),
            'status': state['status'],
            'external_trigger': state['external_trigger'],
            'media_available': state['media_available'],
            'media_error': state['media_error'],
        }
