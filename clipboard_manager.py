import time
import pyperclip
from pynput.keyboard import Key, Controller

keyboard = Controller()

def get_clipboard_content():
    try:
        return pyperclip.paste()
    except Exception as e:
        print(f"Error reading clipboard: {e}")
        return ""

def set_clipboard_content(content):
    try:
        pyperclip.copy(content)
    except Exception as e:
        print(f"Error writing clipboard: {e}")

def perform_copy():
    """Simulates Ctrl+C"""
    with keyboard.pressed(Key.ctrl):
        keyboard.press('c')
        keyboard.release('c')

def capture_selection():
    """
    Orchestrates the capture process:
    1. Backup old clipboard.
    2. Ctrl+C.
    3. Get new content.
    4. Restore old clipboard.
    Returns: (new_content, old_clipboard_content)
    """
    old_clipboard = get_clipboard_content()
    
    # Clear clipboard to detect if copy worked? 
    # Actually, prompt says: Backup -> Ctrl+C -> Wait 0.1s -> Read -> Wait 0.5s -> Restore.
    # We shouldn't clear it because we might lose data if Ctrl+C fails.
    # But if we don't clear, how do we know if Ctrl+C copied something new vs just reading old data?
    # The prompt implies we just read "new content". If it happens to be the same, the deduplication logic handles it.
    
    perform_copy()
    time.sleep(0.1)
    
    new_content = get_clipboard_content()
    
    # Restore happens later in the flow? 
    # "Restore: After another 0.5s delay, write oldClipboard back".
    # The prompt says: "Validation & Cleaning... If valid, start recording".
    # The restore logic is part of step 2.
    
    # We should probably return the old_clipboard so the caller can restore it when appropriate,
    # or just restore it here.
    # If we restore it *immediately* here, we might overwrite the clipboard before the user pastes?
    # No, the user selected text -> we copied it to *our* internal variable -> we restore their old clipboard.
    # This way their clipboard is untouched effectively (except for the split second).
    
    time.sleep(0.5)
    set_clipboard_content(old_clipboard)
    
    print(f"[Clipboard] Backup: {repr(old_clipboard)[:50]}...")
    print(f"[Clipboard] Captured: {repr(new_content)[:50]}...")
    
    return new_content

