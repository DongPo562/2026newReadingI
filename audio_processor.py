import os
import subprocess
import shutil

def generate_slow_audio(input_path, speeds=[0.5, 0.75]):
    """
    Generates slow versions of the input audio file using FFmpeg.
    Prioritizes 'rubberband' filter for high quality, falls back to 'atempo'.

    Args:
        input_path (str): Path to the original audio file.
        speeds (list): List of speed factors (e.g., [0.5, 0.75]).
    """
    if not os.path.exists(input_path):
        print(f"[AudioProcessor] Input file not found: {input_path}")
        return

    ffmpeg_cmd = shutil.which("ffmpeg")
    if not ffmpeg_cmd:
        print("[AudioProcessor] FFmpeg not found! Please install FFmpeg to generate slow audio.")
        return

    try:
        # Parse filename
        # New Format: {number}.wav -> {number}@{speed}.wav
        dirname = os.path.dirname(input_path)
        filename = os.path.basename(input_path)
        name_without_ext = os.path.splitext(filename)[0]
        ext = os.path.splitext(filename)[1]

        generated_files = []

        for speed in speeds:
            new_filename = f"{name_without_ext}@{speed}{ext}"
            output_path = os.path.join(dirname, new_filename)

            # 1. Try Rubberband (High Quality)
            success = False
            try:
                # rubberband=tempo=X
                cmd = [
                    ffmpeg_cmd, '-y', '-v', 'error',
                    '-i', input_path,
                    '-af', f'rubberband=tempo={speed}',
                    output_path
                ]
                # We capture output to check for errors (like "No such filter")
                result = subprocess.run(cmd, capture_output=True, text=True)

                if result.returncode == 0:
                    print(f"[AudioProcessor] Generated (Rubberband): {new_filename}")
                    success = True
                else:
                    # If failed (e.g. filter not available), log and fall through
                    # print(f"[AudioProcessor] Rubberband filter failed: {result.stderr.strip()}")
                    pass

            except Exception as e:
                print(f"[AudioProcessor] Error trying rubberband: {e}")

            # 2. Fallback to Atempo (Standard Quality)
            if not success:
                try:
                    # atempo supports 0.5 to 2.0
                    cmd = [
                        ffmpeg_cmd, '-y', '-v', 'error',
                        '-i', input_path,
                        '-af', f'atempo={speed}',
                        output_path
                    ]
                    subprocess.run(cmd, check=True, capture_output=True)
                    print(f"[AudioProcessor] Generated (Atempo): {new_filename}")
                    success = True

                except Exception as e:
                    print(f"[AudioProcessor] Failed to generate {speed}x version: {e}")

            if success:
                generated_files.append(output_path)

        return generated_files

    except Exception as e:
        print(f"[AudioProcessor] Error processing {input_path}: {e}")
        return []

if __name__ == "__main__":
    # Test
    pass