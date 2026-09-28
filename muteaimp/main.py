import time
from pyaimp import Client, PlayBackState
from pycaw.pycaw import AudioUtilities, IAudioMeterInformation

# Constant for the AIMP executable name
AIMP_EXE = 'AIMP.exe'
# Variable to keep track of the last command sent to avoid redundant actions
sent_command = 'play'

last_message = ''
PAUSE_MESSAGE = "AIMP paused due to active session."
RESUME_MESSAGE = "AIMP resumed as no active session found."


def display_message(message):
    global last_message

    if last_message != message:
        print(message)
        last_message = message


def is_peak_value_exist(session) -> bool:
    """Check if the audio session is producing any significant sound"""

    # Query the IAudioMeterInformation interface for peak audio value
    volume = session._ctl.QueryInterface(IAudioMeterInformation)
    peak = volume.GetPeakValue()

    # If the peak value is greater than the threshold, consider it as active
    return peak > 0.00001


def get_audio_sessions() -> list:
    """
    Get a list of process names that are actively producing audio.
    
    Returns:
        List of process names with active audio output.
    """
    sessions = AudioUtilities.GetAllSessions()

    # Filter sessions to include only those with an associated process
    active_sessions = [
        session.Process.name() for session in sessions if session.Process and is_peak_value_exist(session) and session.Process.name() != AIMP_EXE
    ]

    if active_sessions:
        message = f"Active sessions: {' - '.join(active_sessions)}"
        display_message(message)

    return active_sessions


def control_aimp():
    """
    Control AIMP playback based on other active audio sessions.
    
    If AIMP is playing and other processes are producing audio, pause AIMP.
    If AIMP is paused (by this script) and no other audio is active, resume playback.
    """
    global sent_command  # Declare the global variable so we can modify it

    active_sessions = get_audio_sessions()

    try:
        # Create a client instance for AIMP control
        client = Client()
        state = client.get_playback_state()

        # If AIMP is playing and there are other active audio sessions, pause playback.
        if state == PlayBackState.Playing and active_sessions:
            client.pause()
            sent_command = 'pause'
            display_message(PAUSE_MESSAGE)
        # If AIMP is not playing and it was paused by this script, resume playback when no other audio is active.
        elif state != PlayBackState.Playing and sent_command == 'pause' and not active_sessions:
            client.play()
            sent_command = 'play'
            display_message(RESUME_MESSAGE)
    except RuntimeError:
        # In case of errors with AIMP client operations, do nothing.
        pass


def main():
    """Main loop that continuously checks active audio sessions and controls AIMP playback"""
    while True:
        control_aimp()
        # Delay between checks; lower this value for faster response at the expense of higher CPU usage.
        time.sleep(1)


if __name__ == "__main__":
    main()
    # This sleep is redundant because main() has an infinite loop, but kept for safety.
    time.sleep(100)
