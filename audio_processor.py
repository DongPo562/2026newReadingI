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
        # Format: name_date.wav -> name@speed_date.wav
        dirname = os.path.dirname(input_path)
        filename = os.path.basename(input_path)
        
        # Requirement: [清洗后的文本]_[YYYY-MM-DD].wav
        parts = filename.rsplit('_', 1)
        if len(parts) != 2:
            print(f"[AudioProcessor] Filename format error: {filename}")
            return
            
        text_part = parts[0]
        date_part = parts[1] # includes .wav
        
        for speed in speeds:
            new_filename = f"{text_part}@{speed}_{date_part}"
            output_path = os.path.join(dirname, new_filename)
            
            # 1. Try Rubberband (High Quality)
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
                    continue
                else:
                    # If failed (e.g. filter not available), log and fall through
                    # print(f"[AudioProcessor] Rubberband filter failed: {result.stderr.strip()}")
                    pass
                    
            except Exception as e:
                print(f"[AudioProcessor] Error trying rubberband: {e}")

            # 2. Fallback to Atempo (Standard Quality)
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
                
            except Exception as e:
                print(f"[AudioProcessor] Failed to generate {speed}x version: {e}")
                
    except Exception as e:
        print(f"[AudioProcessor] Error processing {input_path}: {e}")

if __name__ == "__main__":
    # Test
    pass
