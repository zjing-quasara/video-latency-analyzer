"""
日志管理器
统一管理应用日志，支持文件日志和GUI日志
"""
import logging
import sys
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler


class LogManager:
    """日志管理器"""
    
    def __init__(self, log_dir="logs"):
        """初始化日志管理器"""
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        
        # 创建日志文件名（带时间戳）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"app_{timestamp}.log"
        
        # 配置日志格式
        self.formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 创建根logger
        self.logger = logging.getLogger('VideoDelayAnalyzer')
        self.logger.setLevel(logging.DEBUG)
        
        # 清除已有的handlers
        self.logger.handlers.clear()
        
        # 添加文件handler（自动轮转，最大10MB，保留5个备份）
        file_handler = RotatingFileHandler(
            self.log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(self.formatter)
        self.logger.addHandler(file_handler)
        
        # 添加控制台handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(self.formatter)
        self.logger.addHandler(console_handler)
        
        # 记录系统信息
        self._log_system_info()
    
    def _log_system_info(self):
        """记录系统信息"""
        import platform
        import cv2
        # TODO: 时间识别引擎版本检查
        # try:
        #     from paddleocr import __version__ as paddleocr_version
        # except:
        #     paddleocr_version = "unknown"
        
        self.logger.info("=" * 60)
        self.logger.info("视频延时分析工具启动")
        self.logger.info("=" * 60)
        self.logger.info(f"系统: {platform.system()} {platform.release()}")
        self.logger.info(f"Python: {platform.python_version()}")
        self.logger.info(f"OpenCV: {cv2.__version__}")
        # self.logger.info(f"PaddleOCR: {paddleocr_version}")
        self.logger.info(f"日志文件: {self.log_file.absolute()}")
        self.logger.info("=" * 60)
    
    def get_logger(self, name=None):
        """获取logger实例"""
        if name:
            return logging.getLogger(f'VideoDelayAnalyzer.{name}')
        return self.logger
    
    def get_log_file(self):
        """获取当前日志文件路径"""
        return self.log_file
    
    def exception(self, msg, exc_info=True):
        """记录异常"""
        self.logger.exception(msg, exc_info=exc_info)


# 全局日志管理器实例
_log_manager = None


def init_logger(log_dir="logs"):
    """初始化全局日志管理器"""
    global _log_manager
    if _log_manager is None:
        _log_manager = LogManager(log_dir)
    return _log_manager


def get_logger(name=None):
    """获取logger实例"""
    global _log_manager
    if _log_manager is None:
        _log_manager = init_logger()
    return _log_manager.get_logger(name)


def get_log_file():
    """获取当前日志文件路径"""
    global _log_manager
    if _log_manager is None:
        _log_manager = init_logger()
    return _log_manager.get_log_file()


def log_exception(msg):
    """记录异常（快捷方法）"""
    global _log_manager
    if _log_manager is None:
        _log_manager = init_logger()
    _log_manager.exception(msg)



