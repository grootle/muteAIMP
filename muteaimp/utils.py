import json
import os
import threading
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .logging_setup import CONFIG_DIR, configure_logging

CONFIG_FILE = CONFIG_DIR / 'settings.json'

DEFAULT_SOUND_THRESHOLD_DBFS = -60
DEFAULT_INTERVAL_MS = 500
DEFAULT_RESUME_DELAY_MS = 1000

logger = configure_logging()


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
    """Thread-safe persistent settings storage"""

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self.settings = self.load()

        # Create the default configuration on first launch
        if not self.path.exists():
            self.save()

    def load(self) -> Settings:
        """Load settings while tolerating older configuration files"""

        defaults = asdict(Settings())

        if not self.path.is_file():
            return Settings()

        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(data, dict):
                msg = 'Configuration root must be a JSON object'
                logger.error(msg)
                raise ValueError(msg)  # noqa: TRY004

            # Ignore keys that are no longer part of the Settings schema
            valid_keys = {item.name for item in fields(Settings)}

            merged = {
                **defaults,
                **{
                    key: value
                    for key, value in data.items()
                    if key in valid_keys
                }
            }

            return Settings(**merged)
        except (OSError, ValueError, TypeError):
            logger.exception(f'[SETTINGS] Could not load {self.path}')
            return Settings()

    def save(self):
        """Atomically write settings to disk"""
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self.path.with_name(self.path.name + '.tmp')
            serialized = json.dumps(asdict(self.settings), indent=2, ensure_ascii=False)

            # Flush the temporary file before replacing the old one
            with temporary_path.open('w', encoding='utf-8', newline='\n') as tmp:
                tmp.write(serialized)
                tmp.flush()
                os.fsync(tmp.fileno())

            os.replace(temporary_path, self.path)

    def snapshot(self) -> Settings:
        """Return an independent copy of the current settings"""
        with self.lock:
            return Settings(**asdict(self.settings))

    def update(self, **kwargs):
        """Update known settings and persist them immediately"""

        valid_keys = {item.name for item in fields(Settings)}

        with self.lock:
            for key, value in kwargs.items():
                if key not in valid_keys:
                    msg = f'Unknown setting: {key}'
                    logger.error(msg)
                    raise ValueError(msg)

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
