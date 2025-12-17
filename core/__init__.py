"""
核心业务逻辑模块
此模块可独立运行，不依赖GUI，便于迁移到Web后端
"""
from .ocr_engine import OCREngine
from .roi_detector import ROIDetector
from .analyzer import VideoAnalyzer
from .report_generator import ReportGenerator

__all__ = ['OCREngine', 'ROIDetector', 'VideoAnalyzer', 'ReportGenerator']



