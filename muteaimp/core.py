import asyncio
import math
from collections.abc import Iterable

import comtypes
from pyaimp import Client, PlayBackState
from pycaw.pycaw import AudioUtilities, IAudioMeterInformation

from .logging_setup import configure_logging
from .utils import (
    Settings,
    set_state,
    stop_event,
    store,
)

AIMP_EXE = 'AIMP.exe'
logger = configure_logging()


def normalize_text(value: str) -> str:
    """Normalize text for case-insensitive matching"""
    return ' '.join(value.casefold().replace('\\', '/').split())


def _identity_values(identities: str | Iterable[str]) -> tuple[str, ...]:
    """Convert one identity or multiple identities to a tuple"""
    if isinstance(identities, str):
        return (identities,) if identities.strip() else ()

    return tuple(
        value for value in identities
        if isinstance(value, str) and value.strip()
    )


def matches_rule(rule: str, identities: str | Iterable[str]) -> bool:
    """Return True when a rule matches one of the identities"""
    needle = normalize_text(rule)
    if not needle:
        return False
    return any(needle in normalize_text(identity) for identity in _identity_values(identities))


def source_allowed(identities: str | Iterable[str], settings: Settings) -> bool:
    """Apply whitelist/blacklist filtering"""
    values = _identity_values(identities)
    
    if not values:
        return False

    if settings.filter_mode == 'whitelist':
        return bool(settings.whitelist) and any(
            matches_rule(rule, values)
            for rule in settings.whitelist
        )

    if settings.filter_mode == 'blacklist':
        return not any(
            matches_rule(rule, values)
            for rule in settings.blacklist
        )

    return True


def is_peak_above_threshold(peak: float, threshold_dbfs: int) -> bool:
    if peak <= 0.0:
        return False
    peak_dbfs = 20.0 * math.log10(max(peak, 1e-12))
    return peak_dbfs >= threshold_dbfs


def enumerate_sources(settings: Settings):
    """Return (triggering_sources, any_external_trigger)"""
    try:
        sessions = AudioUtilities.GetAllSessions()
    except Exception:
        return [], False

    sources = set()

    for session in sessions:
        try:
            process = session.Process
            if process is None:
                continue

            name = process.name()
            # AIMP must never trigger itself
            if name.casefold() == AIMP_EXE.casefold():
                continue

            if settings.trigger_mode == 'audio':  # Detect audio
                meter = session._ctl.QueryInterface(IAudioMeterInformation)
                peak = float(meter.GetPeakValue())
                if not is_peak_above_threshold(peak, settings.sound_threshold_dbfs):
                    continue
            elif settings.trigger_mode == 'media':  # Detect media sessions (can trigger even at zero volume)
                # 0 = Inactive, 1 = Active, 2 = Expired
                state = int(session.State)
                if state != 1:
                    continue

            if not source_allowed(name, settings):
                continue

            sources.add(name)
        except Exception:
            # The process/session may disappear while being inspected
            continue

    result = sorted(sources, key=str.casefold)
    return result, bool(result)


def get_aimp_snapshot(client):
    playback = client.get_playback_state()
    playback_name = {
        PlayBackState.Playing: 'Playing',
        PlayBackState.Paused: 'Paused',
        PlayBackState.Stopped: 'Stopped'
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


def get_windows_master_volume_state() -> tuple[float | None, bool | None]:
    """Return Windows master volume (0.0–1.0) and mute status"""
    try:
        endpoint_volume = AudioUtilities.GetSpeakers().EndpointVolume

        volume = float(endpoint_volume.GetMasterVolumeLevelScalar())
        muted = bool(endpoint_volume.GetMute())

        return volume, muted
    except Exception:
        return None, None


async def monitor_loop():
    auto_paused_external = False
    auto_paused_volume = False
    auto_paused_win_volume = False
    resume_deadline = None
    external_seen_count = 0
    external_clear_count = 0

    last_external_trigger = None
    last_external_sources = None
    last_playback = None
    last_volume_zero = None
    last_win_volume_zero = None

    while not stop_event.is_set():
        settings = store.snapshot()

        if not settings.enabled:
            set_state(status='Automatic monitoring is off')
            await asyncio.sleep(settings.check_interval_ms / 1000.0)
            continue

        external_sources, external_trigger = enumerate_sources(settings)        

        # Simple debounce to avoid reacting to one tiny audio spike
        if external_trigger:
            external_seen_count += 1
            external_clear_count = 0
        else:
            external_clear_count += 1
            external_seen_count = 0

        confirmed_external = external_seen_count >= 2
        confirmed_clear = external_clear_count >= 2

        # Log only stable changes in external activity.
        # We do not log during the debounce period. The state is
        # considered changed only after it has been confirmed.
        if confirmed_external:
            current_external_trigger = True
            current_external_sources = set(external_sources)
        elif confirmed_clear:
            current_external_trigger = False
            current_external_sources = set()
        else:
            # The state is still being debounced, so keep the
            # previously logged state unchanged.
            current_external_trigger = last_external_trigger
            current_external_sources = last_external_sources

        # AIMP state
        try:
            client = Client()
            playback, playback_name, aimp_volume, muted = get_aimp_snapshot(client)
        except RuntimeError:
            set_state(
                aimp_state='Unavailable',
                external_sources=external_sources,
                external_trigger=external_trigger,
                status='AIMP is not running'
            )
            await asyncio.sleep(settings.check_interval_ms / 1000.0)
            continue
        except Exception as exc:
            msg = f'AIMP error: {type(exc).__name__}'
            logger.exception(msg)
            set_state(status=msg)
            await asyncio.sleep(settings.check_interval_ms / 1000.0)
            continue

        set_state(
            aimp_state=playback_name,
            external_sources=external_sources,
            external_trigger=external_trigger
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
                        + ('an external source is active'
                           if len(external_sources) == 1
                           else 'external sources are active')
                    )
                )
            except Exception:
                pass

        # Rule 3: Windows volume is zero / muted -> PAUSE
        win_volume, win_muted = get_windows_master_volume_state()
        win_volume_is_zero = (
            settings.pause_when_win_volume_zero
            and win_volume is not None
            and (win_volume <= 0 or win_muted)
        )

        if win_volume_is_zero and playback == PlayBackState.Playing:
            try:
                client.pause()
                auto_paused_win_volume = True
                set_state(status='Paused because Windows volume is zero')
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

        # Resume after Windows volume is restored
        if auto_paused_win_volume and settings.resume_when_win_volume_restored:
            win_volume_restored = (
                win_volume is not None
                and win_volume > 0
                and not win_muted
            )
            if win_volume_restored and not confirmed_external:
                try:
                    client.play()
                    auto_paused_win_volume = False
                    set_state(status='AIMP resumed after Windows volume was restored')
                except Exception:
                    pass

        if confirmed_external:
            set_state(status='External media/audio is active')
        elif not auto_paused_external:
            if auto_paused_volume:
                if settings.pause_when_aimp_volume_zero and volume_is_zero:
                    set_state(status='AIMP volume is zero')
                else:
                    set_state(status='Monitoring is active')

            if auto_paused_win_volume:
                if settings.pause_when_win_volume_zero and win_volume_is_zero:
                    set_state(status='Windows volume is zero')
                else:
                    set_state(status='Monitoring is active')

        # Logs
        if last_external_trigger is not None:
            if current_external_trigger != last_external_trigger:
                if current_external_trigger:
                    logger.info(
                        'External activity started: %s',
                        ', '.join(
                            sorted(current_external_sources)
                        ) or 'unknown',
                    )
                else:
                    logger.info('External activity ended')
            elif (
                current_external_trigger
                and current_external_sources != last_external_sources
            ):
                logger.info(
                    'External activity changed: %s',
                    ', '.join(
                        sorted(current_external_sources)
                    ) or 'unknown',
                )

        last_external_trigger = current_external_trigger

        last_external_sources = (
            set(current_external_sources)
            if current_external_sources is not None
            else set()
        )

        if volume_is_zero != last_volume_zero:
            if last_volume_zero is not None:
                if volume_is_zero:
                    logger.info('AIMP volume became zero or muted')
                elif settings.resume_when_aimp_volume_restored:
                    logger.info('AIMP volume was restored')

            last_volume_zero = volume_is_zero

        if win_volume_is_zero != last_win_volume_zero:
            if last_win_volume_zero is not None:
                if win_volume_is_zero:
                    logger.info('Windows volume became zero or muted')
                elif settings.resume_when_win_volume_restored:
                    logger.info('Windows volume was restored')

            last_win_volume_zero = win_volume_is_zero

        if playback != last_playback:
            if last_playback is not None:
                logger.info(
                    'AIMP playback state changed: %s',
                    playback_name
                )

            last_playback = playback

        await asyncio.sleep(settings.check_interval_ms / 1000.0)


def monitor_thread_main():
    comtypes.CoInitialize()
    try:
        asyncio.run(monitor_loop())
    except Exception as exc:
        logger.exception('Monitor thread fatal error')
        set_state(status=f'Monitor error: {type(exc).__name__}')
    finally:
        comtypes.CoUninitialize()
