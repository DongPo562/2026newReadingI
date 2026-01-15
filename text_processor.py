import re

def clean_text(text):
    """
    Retains only English letters (case-insensitive), spaces, and symbols - ’ — $ , . ?
    """
    # Regex explanation:
    # [a-zA-Z] : Letters
    # \s : Whitespace
    # \- : Hyphen
    # ’ : Right single quote (often used as apostrophe)
    # — : Em dash
    # \$ : Dollar sign
    # , : Comma
    # \. : Period
    # \? : Question mark
    # [^...] means match any character NOT in this set.
    # We replace those with empty string.
    
    pattern = r"[^a-zA-Z\s\-’—$,.?]"
    cleaned = re.sub(pattern, "", text)
    # Normalize whitespace (optional but good practice) - prompt doesn't explicitly ask, but "spaces" are allowed.
    # Usually we want to collapse multiple spaces.
    # Let's just keep it simple as per prompt: "Retain... others removed".
    return cleaned

def validate_text(text, last_text=None):
    """
    Checks validity conditions:
    1. Not empty (implied by "text format" and useful content)
    2. Length <= 600
    3. Not same as last_text
    """
    if not text:
        return False, "Empty text"
    
    if len(text) > 600:
        return False, f"Length {len(text)} > 600"
        
    if last_text and text == last_text:
        return False, "Duplicate text"
        
    return True, "Valid"

def process_text(text, last_text=None):
    """
    Orchestrates validation and cleaning.
    Returns: (is_valid, chosenWords)
    """
    is_valid, msg = validate_text(text, last_text)
    if not is_valid:
        print(f"[Validation] Failed: {msg}")
        return False, None
        
    chosenWords = clean_text(text)
    
    # Post-cleaning validation: what if cleaning results in empty string?
    if not chosenWords.strip():
        print("[Validation] Failed: Empty after cleaning")
        return False, None
        
    print(f"[Text] ChosenWords: {chosenWords}")
    return True, chosenWords
