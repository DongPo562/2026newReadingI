# Floating UI Implementation for Audio Recording Manager

## Overview
I have implemented a comprehensive floating UI solution using **Python** and **PyQt6**, designed to work alongside your core recording application.

## Key Features
1.  **Floating Ball (Collapsed State)**:
    *   **Always on Top**: Stays visible above other windows.
    *   **Draggable**: Can be moved anywhere on the screen.
    *   **Visuals**: 45px green gradient circle with icon.
    *   **Interaction**: Hover to expand, Right-click for menu.

2.  **List Panel (Expanded State)**:
    *   **Auto-Expansion**: Smoothly animates from the ball position when hovered.
    *   **Content**: Lists `.wav` files from the `audio` directory, sorted by newest first.
    *   **Audio Player**: Integrated playback with Play/Pause/Stop controls.
    *   **Visuals**: Translucent dark background (90% opacity), rounded corners.
    *   **Auto-Collapse**: Automatically hides when the mouse leaves the panel area.

3.  **Core Functionality**:
    *   **Auto-Refresh**: Monitors the `audio` folder every 2 seconds for new recordings.
    *   **Smart Filenames**: Automatically cleans filenames (removes underscores/dates) for display.
    *   **Error Handling**: Robustly handles missing files, playback errors, and folder issues.
    *   **Keyboard Shortcut**: `Space` key toggles playback.

## Implementation Details
### 1. Configuration (`config.ini`)
A new `[UI]` section has been added to `config.ini` to control all visual aspects (size, opacity, animation speed, etc.).

### 2. Code Structure (`floating_ui.py`)
*   `FloatingBall`: Manages the main floating widget and drag logic.
*   `ListPanel`: Manages the file list and auto-refresh timer.
*   `AudioPlayer`: Handles media playback using `QMediaPlayer`.
*   `AudioListItem`: Custom widget for each file row with dynamic styling.

### 3. Application Launcher (`start_app.bat`)
Updated to launch both the Floating UI and the Main Recorder (in the background) simultaneously.

## How to Run
Simply run `start_app.bat`. It will:
1.  Start the **Floating UI** (Green ball on screen).
2.  Start the **Main Recorder** (Console window for mouse tracking).

## Verification
*   **Dependencies**: `PyQt6` installed.
*   **Tests**: Verified that the UI launches, handles audio files, and responds to interactions.
