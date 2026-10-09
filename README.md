# MuteAIMP

A lightweight Windows utility that automatically pauses **AIMP** when another application starts playing audio or media.

`MuteAIMP` runs quietly in the background and lives in the Windows system tray. It monitors external applications and can automatically pause and resume AIMP based on configurable rules.

The application is designed to be useful when you want AIMP to stop temporarily while watching a video, listening to another application, receiving media playback from another program, or using another audio source.

## Features

### Automatic AIMP pause

`MuteAIMP` can automatically pause AIMP when another application becomes active.

Depending on the configured trigger mode, external activity can be detected through:

* Audio activity
* Media activity

> **Note:** Media monitoring is independent of sound; this means that any audio or video playing—even if muted—will cause AIMP to pause.

### Configurable audio threshold

For audio-based detection, you can configure the minimum audio level required to trigger an AIMP pause.

The threshold is measured in **dBFS** using the Windows audio session peak level.

For example:

```text
-40 dBFS
-50 dBFS
-60 dBFS
-70 dBFS
```

Lower values make the detector more sensitive.

This setting only applies to audio-based detection. It has no effect when using media-only detection.

### Automatic resume

After external audio/media activity ends, `MuteAIMP` can optionally resume AIMP automatically.

You can configure:

* Whether AIMP should resume automatically
* How long `MuteAIMP` should wait before resuming

The delay helps avoid immediately restarting AIMP when an external source pauses briefly.

If automatic resume is disabled, AIMP remains paused.

### AIMP zero-volume protection

`MuteAIMP` can optionally monitor AIMP's own volume/mute ane Windows volume/mute state.

You can configure it to pause AIMP when:

* AIMP's volume reaches `0%`
* AIMP is muted
* Windows volume reaches `0%`
* Windows is muted

You can also choose whether AIMP should automatically resume when its volume or Windows volume is restored.

### Whitelist and blacklist

External applications can be filtered using three modes:

#### All detected apps

Every detected external application can trigger AIMP.

#### All except blacklist

All detected applications can trigger AIMP except applications explicitly listed in the blacklist.

#### Only whitelist

Only applications listed in the whitelist can trigger AIMP.

Matching is case-insensitive and supports partial matching.

For example `chrome` can match `chrome.exe`

## Installation

### From PyPI

Install the package using pip:

```bash
pip install muteaimp
```

Or with `uv`:

```bash
uv add muteaimp
```

After installation, the `muteaimp` command becomes available.

Run the application with:

```bash
muteaimp
```

View live logs with:

```bash
muteaimp log
```

### Development installation

Clone the repository and install the project with `uv`:

```bash
git clone https://github.com/grootle/muteAIMP.git
cd muteaimp
uv sync
```

Run the application:

```bash
uv run muteaimp
```

## System Tray

`MuteAIMP` runs primarily in the Windows notification area.

The tray icon provides access to a custom popup interface.

The popup includes:

* Automatic monitoring toggle
* Active external sources
* Current status
* Settings
* Exit

## Windows Startup

`MuteAIMP` can optionally start automatically when the current Windows user logs in.

The startup option is available from the General settings page.

When enabled, Windows launches `MuteAIMP` in the background after user login.

The application does not require administrator privileges for this user-level startup entry.

## Logging

`MuteAIMP` includes a persistent logging system for troubleshooting.

Logs are stored in:

```text
%LOCALAPPDATA%\MuteAIMP\muteaimp.log
```

For example:

```text
C:\Users\<User>\AppData\Local\MuteAIMP\muteaimp.log
```

The log can contain events such as:

```text
AIMP playback state changes
External activity starting
External activity ending
Automatic AIMP pause
Automatic AIMP resume
AIMP volume becoming zero
AIMP volume restoration
Unexpected exceptions
```

For example:

```text
External activity started: chrome.exe
AIMP playback state changed: Paused
External activity ended
AIMP playback state changed: Playing
```

### View logs from the command line

Because the project exposes a `muteaimp` command, logs can be viewed using:

```bash
muteaimp log
```

The log viewer:

1. Displays existing log entries.
2. Continues following the file.
3. Displays new log entries live.
4. Can be stopped with `Ctrl+C`.

## Command-line interface

### Start the application

```bash
muteaimp
```

### Show logs

```bash
muteaimp log
```

The main application is exposed as a GUI script so that launching it on Windows does not open an unnecessary console window.

The log viewer can use a console-oriented entry point or console attachment mechanism so that live output is available in the terminal.

## Configuration

Configuration is stored as JSON in:

```text
%LOCALAPPDATA%\MuteAIMP\settings.json
```

Example location:

```text
C:\Users\<User>\AppData\Local\MuteAIMP\settings.json
```

### Example configuration

```json
{
  "enabled": true,
  "trigger_mode": "media",
  "sound_threshold_dbfs": -60,
  "check_interval_ms": 500,
  "resume_after_external": true,
  "resume_delay_ms": 1000,
  "pause_when_aimp_volume_zero": false,
  "resume_when_aimp_volume_restored": true,
  "pause_when_win_volume_zero": false,
  "resume_when_win_volume_restored": true,
  "filter_mode": "all",
  "whitelist": [],
  "blacklist": []
}
```

### Configuration fields

| Setting                            | Description                                  |
| ---------------------------------- | -------------------------------------------- |
| `enabled`                          | Enables or disables automatic monitoring     |
| `trigger_mode`                     | Selects audio or media                       |
| `sound_threshold_dbfs`             | Minimum audio peak used by audio detection   |
| `check_interval_ms`                | Monitoring interval                          |
| `resume_after_external`            | Resume AIMP after external activity ends     |
| `resume_delay_ms`                  | Delay before automatic resume                |
| `pause_when_aimp_volume_zero`      | Pause AIMP when its own volume is zero/muted |
| `resume_when_aimp_volume_restored` | Resume after AIMP volume is restored         |
| `pause_when_win_volume_zero`       | Pause AIMP when Windows volume is zero/muted |
| `resume_when_win_volume_restored`  | Resume after Windows volume is restored      |
| `filter_mode`                      | `all`, `blacklist`, or `whitelist`           |
| `whitelist`                        | Applications allowed to trigger AIMP         |
| `blacklist`                        | Applications ignored by the detector         |

## How pause and resume works

`MuteAIMP` distinguishes between an AIMP pause caused by the application and a pause performed manually by the user. The application only attempts automatic resume when it owns the current pause state. This prevents `MuteAIMP` from unexpectedly starting AIMP after the user manually stopped it.

A manually stopped AIMP should remain stopped rather than being restarted automatically.

## Performance

The monitor runs periodically rather than continuously.

The default interval is: `500 ms`

This provides a reasonable balance between responsiveness and CPU usage.

The interval is configurable from the settings page.

Very small intervals may provide faster response but can increase CPU usage.

## Dependencies

The project uses Windows-specific components including:

* Python 3.9+
* PySide6
* pyaimp
* pycaw
* comtypes

## Troubleshooting

### Relative import error

If you see:

```text
ImportError: attempted relative import with no known parent package
```

do not execute a package file directly:

```bash
python muteaimp/main.py
```

Instead run the module:

```bash
python -m muteaimp.main
```

or use the installed application command:

```bash
muteaimp
```

### `muteaimp` command is not found

Make sure the package environment's executable directory is available in PATH.

For an installed package, verify:

```bash
where muteaimp
```

When using `uv` in a development environment, use:

```bash
uv run muteaimp
```

### The wrong application is triggering AIMP

Use App Rules: `Settings` -> `App Rules` -> `Whitelist / Blacklist`

Use process names or recognizable application identifiers.

Examples:

```text
chrome.exe
vlc.exe
telegram
spotify
```

### Settings are not preserved

Check:

```text
%LOCALAPPDATA%\MuteAIMP\settings.json
```

Settings should be written whenever a setting is changed.

If the file does not exist, verify that the application has permission to write to the user's local application-data directory.
