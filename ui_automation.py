import logging
import ctypes
import re
from ctypes import wintypes

# Configure logging
logger = logging.getLogger("UIAutomation")

# Lazy-loaded modules
_comtypes_client = None
_UIAutomationClient = None
_uia = None  # 缓存 UIA 实例

# 需要从文本开头移除的 UI 标签模式
UI_LABEL_PATTERNS = [
    r'^Heading\s*[1-6]\s*',      # Heading 1, Heading 2, ..., Heading 6
    r'^Text\s+',                  # Text 
    r'^Paragraph\s+',             # Paragraph
    r'^Quote\s+',                 # Quote
    r'^Callout\s+',               # Callout
    r'^Toggle\s+',                # Toggle
    r'^Bulleted\s+list\s+item\s+', # Bulleted list item
    r'^Numbered\s+list\s+item\s+', # Numbered list item
    r'^To-do\s+',                 # To-do
]

def _ensure_initialized():
    """延迟初始化 COM 和 UI Automation 库"""
    global _comtypes_client, _UIAutomationClient, _uia

    if _comtypes_client is not None:
        return True

    try:
        import comtypes
        try:
            comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        except OSError:
            pass

        import comtypes.client
        _comtypes_client = comtypes.client

        _comtypes_client.GetModule("UIAutomationCore.dll")
        from comtypes.gen import UIAutomationClient
        _UIAutomationClient = UIAutomationClient

        # 创建并缓存 UIA 实例
        _uia = _comtypes_client.CreateObject(
            _UIAutomationClient.CUIAutomation,
            interface=_UIAutomationClient.IUIAutomation
        )
        return True

    except Exception as e:
        logger.error(f"Failed to initialize UI Automation: {e}")
        return False

def _clean_ui_labels(text):
    """
    清理文本开头的 UI 标签（如 Heading 3、Text 等）
    """
    if not text:
        return text

    cleaned = text
    for pattern in UI_LABEL_PATTERNS:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

    return cleaned.strip()

def _get_element_text(element):
    """尝试从元素获取文本"""
    if not element:
        return ""

    # Try CurrentName
    try:
        name = element.CurrentName
        if name:
            return name
    except Exception:
        pass

    # Try ValuePattern
    try:
        pattern = element.GetCurrentPattern(10002)  # UIA_ValuePatternId
        if pattern:
            val_pattern = pattern.QueryInterface(_UIAutomationClient.IUIAutomationValuePattern)
            if val_pattern:
                val = val_pattern.CurrentValue
                if val:
                    return val
    except Exception:
        pass

    return ""

def _get_all_text_from_element(element, uia, max_depth=3):
    """
    递归获取元素及其所有子元素的文本
    """
    if not element or max_depth <= 0:
        return ""

    texts = []

    current_text = _get_element_text(element)
    if current_text:
        texts.append(current_text)

    try:
        condition = uia.CreateTrueCondition()
        children = element.FindAll(2, condition)  # TreeScope_Children = 2

        if children:
            for i in range(children.Length):
                child = children.GetElement(i)
                child_text = _get_all_text_from_element(child, uia, max_depth - 1)
                if child_text:
                    texts.append(child_text)
    except Exception:
        pass

    return " ".join(texts)

def get_selected_text():
    """
    使用 UI Automation TextPattern 获取当前选中的文本。

    策略：
    1. 获取当前焦点元素
    2. 向上遍历查找支持 TextPattern 的元素
    3. 使用 GetSelection() 获取选中文本
    4. 如果 TextPattern 失败，回退到鼠标位置元素获取

    Returns:
        str: 选中的文本，失败返回空字符串
    """
    if not _ensure_initialized():
        print("[UIA] 初始化失败")
        return ""

    if not _UIAutomationClient or not _uia:
        return ""

    try:
        # ========== 方法1: 使用焦点元素的 TextPattern ==========
        focused = _uia.GetFocusedElement()
        if focused:
            text = _try_get_selection_from_element(focused)
            if text:
                cleaned = _clean_ui_labels(text.strip())
                print(f"[UIA] 焦点元素获取成功: \"{cleaned[:50]}{'...' if len(cleaned) > 50 else ''}\"")
                return cleaned

        # ========== 方法2: 从鼠标位置元素向上查找 TextPattern ==========
        pt = wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        t_pt = _UIAutomationClient.tagPOINT(pt.x, pt.y)

        element = _uia.ElementFromPoint(t_pt)
        if element:
            text = _try_get_selection_from_element(element)
            if text:
                cleaned = _clean_ui_labels(text.strip())
                print(f"[UIA] 鼠标位置获取成功: \"{cleaned[:50]}{'...' if len(cleaned) > 50 else ''}\"")
                return cleaned

        # ========== 方法3: 从前台窗口获取 ==========
        foreground_hwnd = ctypes.windll.user32.GetForegroundWindow()
        if foreground_hwnd:
            fg_element = _uia.ElementFromHandle(foreground_hwnd)
            if fg_element:
                text = _try_get_selection_from_element(fg_element)
                if text:
                    cleaned = _clean_ui_labels(text.strip())
                    print(f"[UIA] 前台窗口获取成功: \"{cleaned[:50]}{'...' if len(cleaned) > 50 else ''}\"")
                    return cleaned

        print("[UIA] 所有方法均未获取到选中文本")
        return ""

    except Exception as e:
        print(f"[UIA] 错误: {e}")
        return ""

def _try_get_selection_from_element(element, max_parents=8):
    """
    尝试从元素或其父元素获取选中文本

    Args:
        element: 起始元素
        max_parents: 最多向上遍历的父元素数量

    Returns:
        str: 选中的文本，失败返回空字符串
    """
    if not element:
        return ""

    current = element
    walker = _uia.ControlViewWalker

    # UIA_TextPatternId = 10014
    # UIA_TextPattern2Id = 10024
    text_pattern_ids = [10014, 10024]

    for depth in range(max_parents + 1):
        if not current:
            break

        for pattern_id in text_pattern_ids:
            try:
                pattern = current.GetCurrentPattern(pattern_id)
                if pattern:
                    # 尝试 IUIAutomationTextPattern2 先
                    if pattern_id == 10024:
                        text_pattern = pattern.QueryInterface(_UIAutomationClient.IUIAutomationTextPattern2)
                    else:
                        text_pattern = pattern.QueryInterface(_UIAutomationClient.IUIAutomationTextPattern)

                    if text_pattern:
                        selection = text_pattern.GetSelection()
                        if selection and selection.Length > 0:
                            text_range = selection.GetElement(0)
                            if text_range:
                                # -1 表示获取全部文本
                                text = text_range.GetText(-1)
                                if text and text.strip():
                                    return text
            except Exception:
                pass

        # 向上遍历父元素
        try:
            current = walker.GetParentElement(current)
        except Exception:
            break

    return ""

def get_text_at_cursor():
    """
    获取鼠标位置下的 UI 元素文本（原有功能，保留用于 Alt 键触发）
    """
    if not _ensure_initialized():
        return ""

    if not _UIAutomationClient or not _uia:
        return ""

    try:
        pt = wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        t_pt = _UIAutomationClient.tagPOINT(pt.x, pt.y)

        element = _uia.ElementFromPoint(t_pt)
        if not element:
            return ""

        current_text = _get_element_text(element)
        best_text = current_text

        walker = _uia.ControlViewWalker
        parent = element

        for _ in range(5):
            try:
                parent = walker.GetParentElement(parent)
                if not parent:
                    break

                parent_text = _get_element_text(parent)

                if not parent_text or len(parent_text) <= len(best_text):
                    parent_text = _get_all_text_from_element(parent, _uia, max_depth=2)

                if parent_text and len(parent_text) > len(best_text):
                    best_text = parent_text
                    if len(best_text) > 100:
                        break

            except Exception:
                break

        cleaned_text = _clean_ui_labels(best_text.strip())
        return cleaned_text

    except Exception as e:
        logger.error(f"UI Automation error: {e}")
        return ""