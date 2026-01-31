"""
样式管理模块
负责加载和管理 QSS 样式表
"""
import os
from pathlib import Path

class StyleManager:
    """QSS 样式表管理器"""
    
    # 样式文件目录（已从 styles/ 迁移到项目根目录）
    STYLES_DIR = Path(__file__).parent
    
    # 缓存已加载的样式
    _cache = {}
    
    @classmethod
    def load_stylesheet(cls, filename: str, use_cache: bool = True) -> str:
        """
        加载 QSS 样式文件
        
        Args:
            filename: 样式文件名（如 'review_window.qss'）
            use_cache: 是否使用缓存（开发时可设为 False）
        
        Returns:
            样式表字符串
        """
        if use_cache and filename in cls._cache:
            return cls._cache[filename]
        
        filepath = cls.STYLES_DIR / filename
        
        if not filepath.exists():
            print(f"[StyleManager] 警告：样式文件不存在 {filepath}")
            return ""
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                stylesheet = f.read()
            
            if use_cache:
                cls._cache[filename] = stylesheet
            
            print(f"[StyleManager] 已加载样式：{filename}")
            return stylesheet
        
        except Exception as e:
            print(f"[StyleManager] 加载样式失败：{e}")
            return ""
    
    @classmethod
    def reload_stylesheet(cls, filename: str) -> str:
        """
        强制重新加载样式文件（用于热更新）
        """
        if filename in cls._cache:
            del cls._cache[filename]
        return cls.load_stylesheet(filename, use_cache=True)
    
    @classmethod
    def clear_cache(cls):
        """清空样式缓存"""
        cls._cache.clear()