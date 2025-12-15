"""
配置管理模块
集中管理所有配置项，便于环境切换
"""
import os
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent

# 数据目录
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_DIR = DATA_DIR / "config"
DEBUG_DIR = DATA_DIR / "debug"

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

# 自动创建目录
for dir_path in [DATA_DIR, CONFIG_DIR, DEBUG_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

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
DEFAULT_RESIZE_RATIO = 0.5 # 默认OCR分辨率缩放比例

# GPU设置
def set_gpu_device(use_gpu: bool):
    """设置GPU设备"""
    if use_gpu:
        os.environ['CUDA_VISIBLE_DEVICES'] = '0'
    else:
        os.environ['CUDA_VISIBLE_DEVICES'] = '-1'

# ROI检测参数
ROI_DETECTION = {
    'threshold': 30,           # 二值化阈值（用于检测黑底白字）
    'min_area_ratio': 0.05,    # 最小面积比例
    'max_area_ratio': 0.5,     # 最大面积比例
    'min_aspect_ratio': 2.0,   # 最小宽高比
    'max_aspect_ratio': 6.0    # 最大宽高比
}

# 报告配置
REPORT_CONFIG = {
    'csv_name': 'analysis_report.csv',
    'html_name': 'analysis_report.html',
    'video_name': 'annotated_video.mp4',
    'video_codec': 'mp4v'  # MPEG-4编码，兼容性最好
}

