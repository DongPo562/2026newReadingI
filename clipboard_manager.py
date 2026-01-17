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
    2. Clear clipboard.
    3. Ctrl+C.
    4. Wait for new content (retry mechanism).
    5. Restore old clipboard.
    Returns: new_content
    """
    old_clipboard = get_clipboard_content()
    
    # Clear clipboard to ensure we capture fresh content
    set_clipboard_content("")
    time.sleep(0.05) 
    
    perform_copy()
    
    # Wait for new content with timeout (up to 0.8s)
    new_content = ""
    for _ in range(10):
        time.sleep(0.05)
        new_content = get_clipboard_content()
        if new_content:
            break
    
    # If still empty, it means copy failed or selection was empty.
    # We return empty string in that case (which will fail validation later or be ignored)
    
    # Restore old clipboard
    # We can do this immediately or wait a bit. 
    # Original code waited 0.5s before restore.
    time.sleep(0.8)
    set_clipboard_content(old_clipboard)
    
    print(f"[Clipboard] Backup: {repr(old_clipboard)[:50]}...")
    print(f"[Clipboard] Captured: {repr(new_content)[:50]}...")
    
    return new_content

