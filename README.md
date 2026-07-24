# AIMP Auto Pause/Resume

AIMP Auto Pause/Resume is a Python utility that automatically controls the playback of the AIMP music player based on the state of other audio sessions on your system. When any other application (e.g., a video player) is actively running the utility will pause AIMP. Once these sessions become inactive, AIMP will resume playing.

## Features

- **Automatic Detection:** Monitors system audio sessions using the [pycaw](https://github.com/AndreMiras/pycaw) library.
- **Seamless AIMP Control:** Automatically pauses AIMP when another application is active and resumes playback when all other sessions are inactive.

## Prerequisites

- **Python:** 3.6+
- **Required Python Packages:**
  - [pyaimp](https://pypi.org/project/pyaimp/)
  - [pycaw](https://github.com/AndreMiras/pycaw)

## Installation

1. **Clone the Repository:**

   ```bash
   git clone https://github.com/grootle/muteAIMP.git
   cd muteAIMP
   ```

2. **Create a Virtual Environment (Optional):**

   ```bash
   python -m venv venv
   source venv/Scripts/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

   If you do not have a `requirements.txt`, you can install the packages individually:

   ```bash
   pip install pyaimp pycaw
   ```

## Usage

1. **Ensure AIMP is Installed:**  
   Make sure AIMP is installed on your system and that the executable name is `AIMP.exe`.

2. **Run the Script:**

   ```bash
   python main.py
   ```

   The script will register for audio session notifications on your system. It will monitor the audio sessions and automatically pause AIMP if any other session becomes active, resuming playback when they become inactive.

3. **Logging:**  
   The console output will display debugging messages, such as active session changes and AIMP control actions (pause/resume).

## Customization

- **AIMP Executable Name:**  
  If your AIMP executable has a different name, update the `AIMP_EXE` constant in `main.py`.

- **Polling Interval:**  
  The script uses an infinite loop with a 1-second delay to keep running. Adjust `time.sleep(1)` in the main loop if you need a different interval.
