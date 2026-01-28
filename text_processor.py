import re


def clean_text(text):
    pattern = r"[^\x00-\x7F]+"
    cleaned = re.sub(pattern, "", text)
    return cleaned


def validate_text(text, last_text=None):
    if not text:
        return False, "Empty text"
    if len(text) > 600:
        return False, f"Length {len(text)} > 600"
    return True, "Valid"


def process_text(text, last_text=None):
    is_valid, msg = validate_text(text, last_text)
    if not is_valid:
        print(f"[Validation] Failed: {msg}")
        return False, None
    chosenWords = clean_text(text)
    if not chosenWords.strip():
        print("[Validation] Failed: Empty after cleaning")
        return False, None
    print(f"[Text] ChosenWords: {chosenWords}")
    return True, chosenWords


# ==================== 阶段四：单词识别函数 ====================
def is_valid_word(text):
    """
    判断字符串是否为合法的英文单词

    规则：
    - 仅包含英文字母、连字符(-)、撇号(')
    - 无空格
    - 长度不超过 35 字符

    Args:
        text: 待检测的字符串

    Returns:
        bool: True 表示是合法单词，False 表示不是
    """
    if not text or not isinstance(text, str):
        return False

    # 去除首尾空白
    text = text.strip()

    # 长度检查
    if len(text) > 35 or len(text) == 0:
        return False

    # 正则表达式：仅英文字母，可包含连字符和撇号（但不能在首尾）
    word_pattern = r"^[a-zA-Z]+(['-][a-zA-Z]+)*$"
    return bool(re.match(word_pattern, text))