import asyncio
import math

import comtypes
from pyaimp import Client, PlayBackState
from pycaw.pycaw import AudioUtilities, IAudioMeterInformation

from .utils import (
    Settings,
    set_state,
    stop_event,
    store,
)

AIMP_EXE = 'AIMP.exe'


def normalize_text(value: str) -> str:
    return ' '.join(value.lower().replace('\\', '/').split())


def matches_rule(rule: str, identities: list[str]) -> bool:
    needle = normalize_text(rule)
    if not needle:
        return False
    return any(needle in normalize_text(identity) for identity in identities if identity)


def source_allowed(identities: list[str], settings: Settings) -> bool:
    if settings.filter_mode == 'whitelist':
        if not settings.whitelist:
            return False
        return any(matches_rule(rule, identities) for rule in settings.whitelist)

    if settings.filter_mode == 'blacklist':
        return not any(matches_rule(rule, identities) for rule in settings.blacklist)

    return True


def is_peak_above_threshold(peak: float, threshold_dbfs: int) -> bool:
    if peak <= 0.0:
        return False
    peak_dbfs = 20.0 * math.log10(max(peak, 1e-12))
    return peak_dbfs >= threshold_dbfs


def enumerate_audio_sources(settings: Settings):
    """Return (triggering_sources, any_audio_trigger)"""
    try:
        sessions = AudioUtilities.GetAllSessions()
    except Exception:
        return [], False

    sources = []
    any_trigger = False

    for session in sessions:
        try:
            process = session.Process
            if process is None:
                continue

            exe = process.name()
            if exe.casefold() == AIMP_EXE.casefold():
                continue

            meter = session._ctl.QueryInterface(IAudioMeterInformation)
            peak = float(meter.GetPeakValue())

            if not is_peak_above_threshold(peak, settings.sound_threshold_dbfs):
                continue

            identities = [exe]
            if not source_allowed(identities, settings):
                continue

            sources.append(exe)
            any_trigger = True
        except Exception:
            continue

    return sorted(set(sources), key=str.casefold), any_trigger


def get_aimp_snapshot(client):
    playback = client.get_playback_state()
    playback_name = {
        PlayBackState.Playing: 'Playing',
        PlayBackState.Paused: 'Paused'
    }.get(playback, 'Unknown')

    volume = None
    try:
        volume = int(client.get_volume())
    except Exception:
        pass

    muted = False
    try:
        muted = bool(client.is_muted())
    except Exception:
        pass

    return playback, playback_name, volume, muted


class MediaSessionDetector:
    def __init__(self):
        self.manager = None
        self.app_name_cache: dict[str, str] = {}

    async def ensure_manager(self):
        if self.manager is not None:
            return True
        try:
            from winrt.windows.media.control import (
                GlobalSystemMediaTransportControlsSessionManager as SessionManager,
            )
            self.manager = await SessionManager.request_async()
            return True
        except Exception as exc:
            self.manager = None
            set_state(media_available=False, media_error=str(exc))
            return False

    def display_name(self, source_id: str) -> str:
        source_id = source_id or 'Unknown media app'
        if source_id in self.app_name_cache:
            return self.app_name_cache[source_id]

        name = source_id
        try:
            from winrt.windows.applicationmodel import AppInfo
            app = AppInfo.get_from_app_user_model_id(source_id)
            name = str(getattr(app, 'display_name', '') or '').strip() or source_id
        except Exception:
            # Common fallback: make a long AUMID a little more readable
            candidate = source_id.split('!')[0]
            candidate = candidate.split('_')[0]
            if candidate:
                name = candidate

        self.app_name_cache[source_id] = name
        return name

    async def get_playing_sources(self, settings: Settings):
        if not await self.ensure_manager():
            return [], False

        try:
            from winrt.windows.media.control import (
                GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
            )

            sources = []
            for session in self.manager.get_sessions():
                try:
                    info = session.get_playback_info()
                    if info.playback_status != PlaybackStatus.PLAYING:
                        continue

                    source_id = str(session.source_app_user_model_id or '')
                    name = self.display_name(source_id)

                    # Never let AIMP's own media session trigger itself
                    identity = [name, source_id]
                    if 'aimp' in normalize_text(' '.join(identity)):
                        continue

                    if not source_allowed(identity, settings):
                        continue

                    sources.append(name)
                except Exception:
                    continue

            set_state(media_available=True, media_error='')
            return sorted(set(sources), key=str.casefold), bool(sources)
        except Exception as exc:
            set_state(media_available=False, media_error=str(exc))
            self.manager = None
            return [], False


async def monitor_loop():
    media_detector = MediaSessionDetector()

    auto_paused_external = False
    auto_paused_volume = False
    resume_deadline = None
    external_seen_count = 0
    external_clear_count = 0

    while not stop_event.is_set():
        settings = store.snapshot()

        if not settings.enabled:
            set_state(status='Automatic monitoring is off')
            await asyncio.sleep(settings.check_interval_ms / 1000.0)
            continue

        # Detect audio
        audio_sources, audio_trigger = ([], False)
        if settings.trigger_mode in ('audio', 'audio_or_media'):
            audio_sources, audio_trigger = enumerate_audio_sources(settings)

        # Detect media sessions (can trigger even at zero volume)
        media_sources, media_trigger = ([], False)
        if settings.trigger_mode in ('media', 'audio_or_media'):
            media_sources, media_trigger = await media_detector.get_playing_sources(settings)

        external_sources = sorted(
            set(audio_sources + media_sources),
            key=str.casefold
        )
        external_trigger = bool(audio_trigger or media_trigger)

        # Simple debounce to avoid reacting to one tiny audio spike
        if external_trigger:
            external_seen_count += 1
            external_clear_count = 0
        else:
            external_clear_count += 1
            external_seen_count = 0

        confirmed_external = external_seen_count >= 2
        confirmed_clear = external_clear_count >= 2

        # AIMP state
        try:
            client = Client()
            playback, playback_name, aimp_volume, muted = get_aimp_snapshot(client)
        except RuntimeError:
            set_state(
                aimp_state='Unavailable',
                aimp_volume=None,
                external_sources=external_sources,
                audio_trigger=audio_trigger,
                media_trigger=media_trigger,
                status='AIMP is not running'
            )
            await asyncio.sleep(settings.check_interval_ms / 1000.0)
            continue
        except Exception as exc:
            set_state(status=f'AIMP error: {type(exc).__name__}')
            await asyncio.sleep(settings.check_interval_ms / 1000.0)
            continue

        set_state(
            aimp_state=playback_name,
            aimp_volume=aimp_volume,
            external_sources=external_sources,
            audio_trigger=audio_trigger,
            media_trigger=media_trigger
        )

        # Rule 1: AIMP app volume is zero / muted -> PAUSE
        volume_is_zero = (
            settings.pause_when_aimp_volume_zero
            and aimp_volume is not None
            and (aimp_volume <= 0 or muted)
        )

        if volume_is_zero and playback == PlayBackState.Playing:
            try:
                client.pause()
                auto_paused_volume = True
                set_state(status='Paused because AIMP volume is zero')
            except Exception:
                pass

        # Rule 2: external source -> PAUSE
        if confirmed_external and playback == PlayBackState.Playing:
            try:
                client.pause()
                auto_paused_external = True
                set_state(
                    status=(
                        'Paused because '
                        + ', '.join(external_sources[:3])
                        + (' is active' if len(external_sources) == 1 else ' are active')
                    )
                )
            except Exception:
                pass

        # Resume after external trigger ends
        now = asyncio.get_running_loop().time()
        if confirmed_clear and auto_paused_external:
            if settings.resume_after_external:
                if resume_deadline is None:
                    resume_deadline = now + settings.resume_delay_ms / 1000.0
            else:
                auto_paused_external = False
                resume_deadline = None

        if auto_paused_external and settings.resume_after_external and \
            resume_deadline is not None and now >= resume_deadline:
            # Still clear, and volume isn't zero
            volume_ok = not (
                settings.pause_when_aimp_volume_zero
                and aimp_volume is not None
                and (aimp_volume <= 0 or muted)
            )
            if volume_ok:
                try:
                    current_state = client.get_playback_state()
                    if current_state == PlayBackState.Paused:
                        client.play()
                    auto_paused_external = False
                    resume_deadline = None
                    set_state(status='AIMP resumed after the external media ended')
                except Exception:
                    pass

        if external_trigger:
            resume_deadline = None

        # Resume after AIMP volume is restored
        if auto_paused_volume and settings.resume_when_aimp_volume_restored:
            volume_restored = (
                aimp_volume is not None
                and aimp_volume > 0
                and not muted
            )
            if volume_restored and not confirmed_external:
                try:
                    client.play()
                    auto_paused_volume = False
                    set_state(status='AIMP resumed after its volume was restored')
                except Exception:
                    pass

        if confirmed_external:
            set_state(status='External media/audio is active')
        elif not auto_paused_volume and not auto_paused_external:
            if settings.pause_when_aimp_volume_zero and aimp_volume == 0:
                set_state(status='AIMP volume is zero')
            else:
                set_state(status='Monitoring is active')

        await asyncio.sleep(settings.check_interval_ms / 1000.0)


def monitor_thread_main():
    comtypes.CoInitialize()
    try:
        asyncio.run(monitor_loop())
    except Exception as exc:
        print('Monitor thread fatal error:', exc)
        set_state(status=f'Monitor error: {type(exc).__name__}')
    finally:
        comtypes.CoUninitialize()
