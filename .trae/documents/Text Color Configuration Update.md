# Text Color Configuration Update

## Overview
I have successfully integrated the list text color parameter into `config.ini`, allowing for easy customization of the UI appearance without modifying the code.

## Changes Implemented
1.  **Configuration (`config.ini`)**:
    *   Added `text_color` parameter under the `[UI]` section.
    *   Set default value to `#FFFFFF` (White) to ensure good contrast against the dark background.

2.  **Config Loader (`config_loader.py`)**:
    *   Added `ui_text_color` property to the `Config` class to read the new parameter.

3.  **UI Logic (`floating_ui.py`)**:
    *   Updated `AudioListItem` to use `app_config.ui_text_color` for the filename label instead of the hardcoded `#333`.

## How to Verify
1.  Open `config.ini`.
2.  Locate `text_color = #FFFFFF`.
3.  Change it to any hex color (e.g., `#FF0000` for red) and restart the application using `start_app.bat` to see the change.
