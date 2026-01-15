# High-Quality Audio Stretching Upgrade

## Overview
I have replaced the `librosa` based time-stretching with a robust **FFmpeg** implementation to address the audio quality issues.

## Key Changes
1.  **Switch to FFmpeg**:
    *   The application now calls `ffmpeg` directly to generate the 0.5x and 0.75x speed versions.
    *   **Rubberband Filter**: It prioritizes the `rubberband` filter (built into your installed FFmpeg version), which is the industry standard for high-quality time stretching without pitch artifacts.
    *   **Fallback**: If for some reason the rubberband filter fails, it gracefully falls back to the `atempo` filter (WSOLA algorithm), which is still superior to basic phase vocoders for speech.

2.  **Cleanup**:
    *   Removed `librosa` from `requirements.txt` and `audio_processor.py` as it is no longer needed.

## Verification
1.  **Record** a new clip.
2.  **Listen** to the generated slow versions. They should sound much clearer, with preserved transients and natural pitch, compared to the previous version.
3.  **Check Console**: You should see `[AudioProcessor] Generated (Rubberband): ...` indicating the high-quality filter was used.

You do not need to install anything new as `ffmpeg` is already present on your system with the required capabilities.
