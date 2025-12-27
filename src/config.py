"""
配置管理模块
集中管理所有配置项，便于环境切换
"""
import os
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 配置目录（运行时数据）
CONFIG_DIR = PROJECT_ROOT / "data" / "config"

# 日志目录（运行时自动创建）
LOGS_DIR = PROJECT_ROOT / "logs"

# 默认输出目录（桌面）
try:
    import winreg
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                         r'Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders')
    DESKTOP_PATH = Path(winreg.QueryValueEx(key, 'Desktop')[0])
    winreg.CloseKey(key)
except:
    # 降级方案
    DESKTOP_PATH = Path.home() / "Desktop"

DEFAULT_OUTPUT_DIR = DESKTOP_PATH / "视频延时分析"

# 自动创建必要目录（运行时数据）
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ROI配置文件路径
ROI_CONFIG_PATH = CONFIG_DIR / "roi_config.json"

# 视频处理配置
DEFAULT_FRAME_STEP = 5      # 默认跳帧步长（每5帧处理1帧）

# 分析模式配置
ANALYSIS_MODES = {
    'debug': {
        'name': '调试分析',
        'frame_limit': 100,
        'description': '快速测试，仅分析前100帧'
    },
    'full': {
        'name': '全量分析',
        'frame_limit': float('inf'),  # 无限制
        'description': '完整分析整个视频'
    }
}

# OCR配置
DEFAULT_USE_GPU = False    # 默认不使用GPU

# 异常检测配置
ANOMALY_DETECTION = {
    'hard_delay_max_ms': 10000,      # 硬性延时上限（毫秒），超过标记为wrong
    'physical_limit_ms': 10000,     # 物理极限（毫秒），绝对异常
    'negative_limit_ms': -10000,     # 负延迟下限（毫秒）
    'statistical_z_threshold': 5.0,  # 统计异常z-score阈值
}

# 报告配置
REPORT_CONFIG = {
    'csv_name': 'analysis_report.csv',
    'html_name': 'analysis_report.html',
    'video_name': 'annotated_video.mp4',
    'video_codec': 'mp4v'  # MPEG-4编码，兼容性最好
}

