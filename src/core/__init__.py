"""
核心业务逻辑模块
此模块可独立运行，不依赖GUI，便于迁移到Web后端
"""
from .report_generator import ReportGenerator
from .network_matcher import NetworkMatcher
from .outlier_detector import DelayOutlierDetector
from .time_detector import (
    detect_time_app,
    detect_time_real,
    detect_time_in_region,
    parse_time_to_ms,
    parse_time_auto,
    parse_time_format_colon,
    parse_time_format_digits,
    calculate_overlap
)

__all__ = [
    'ReportGenerator',
    'NetworkMatcher',
    'DelayOutlierDetector',
    'detect_time_app',
    'detect_time_real',
    'detect_time_in_region',
    'parse_time_to_ms',
    'parse_time_auto',
    'parse_time_format_colon',
    'parse_time_format_digits',
    'calculate_overlap',
]
