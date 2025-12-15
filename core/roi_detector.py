"""
ROI检测器
负责检测和管理感兴趣区域
"""
import cv2
import json
from pathlib import Path
from config import ROI_DETECTION, ROI_CONFIG_PATH


class ROIDetector:
    """ROI检测和管理"""
    
    def __init__(self):
        """初始化ROI检测器"""
        self.app_roi = None  # T_app的固定ROI
        self.load_config()
    
    def load_config(self):
        """从配置文件加载ROI"""
        if ROI_CONFIG_PATH.exists():
            try:
                with open(ROI_CONFIG_PATH, 'r') as f:
                    config = json.load(f)
                    self.app_roi = tuple(config['app_roi'])
                    print(f"已加载ROI配置: {self.app_roi}")
            except Exception as e:
                print(f"加载ROI配置失败: {e}")
    
    def save_config(self, last_video_dir=None):
        """
        保存ROI到配置文件
        
        Args:
            last_video_dir: 上次选择的视频目录路径
        """
        if self.app_roi:
            try:
                config = {'app_roi': list(self.app_roi)}
                
                # 保存上次视频目录
                if last_video_dir:
                    config['last_video_dir'] = str(last_video_dir)
                
                with open(ROI_CONFIG_PATH, 'w') as f:
                    json.dump(config, f, indent=2)
                print("ROI配置已保存")
            except Exception as e:
                print(f"保存ROI配置失败: {e}")
    
    def get_last_video_dir(self):
        """获取上次选择的视频目录"""
        if ROI_CONFIG_PATH.exists():
            try:
                with open(ROI_CONFIG_PATH, 'r') as f:
                    config = json.load(f)
                    return config.get('last_video_dir', '')
            except Exception as e:
                print(f"读取上次视频目录失败: {e}")
        return ''
    
    def set_app_roi(self, roi: tuple):
        """
        设置T_app的ROI
        
        Args:
            roi: (x1, y1, x2, y2)
        """
        self.app_roi = roi
        self.save_config()
    
    def get_app_roi(self) -> tuple:
        """获取T_app的ROI"""
        return self.app_roi
    
    @staticmethod
    def detect_real_time_roi(frame) -> tuple:
        """
        动态检测T_real的ROI（黑底白字的手机屏幕）
        
        Args:
            frame: OpenCV图像帧
            
        Returns:
            ROI坐标 (x1, y1, x2, y2)，失败返回None
        """
        h, w = frame.shape[:2]
        
        # 转灰度图
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # 二值化（反转，黑色变白色）
        _, binary = cv2.threshold(
            gray, 
            ROI_DETECTION['threshold'], 
            255, 
            cv2.THRESH_BINARY_INV
        )
        
        # 查找轮廓
        contours, _ = cv2.findContours(
            binary, 
            cv2.RETR_EXTERNAL, 
            cv2.CHAIN_APPROX_SIMPLE
        )
        
        # 筛选候选区域
        candidate = None
        max_area = 0
        
        for cnt in contours:
            x, y, w_box, h_box = cv2.boundingRect(cnt)
            area = w_box * h_box
            
            # 面积筛选
            min_area = ROI_DETECTION['min_area_ratio'] * w * h
            max_area_limit = ROI_DETECTION['max_area_ratio'] * w * h
            
            if area < min_area or area > max_area_limit:
                continue
            
            # 宽高比筛选（时间显示通常是横向的）
            ratio = w_box / (h_box + 1e-6)
            if ratio < ROI_DETECTION['min_aspect_ratio'] or ratio > ROI_DETECTION['max_aspect_ratio']:
                continue
            
            # 选择最大的候选区域
            if area > max_area:
                max_area = area
                candidate = (x, y, x + w_box, y + h_box)
        
        return candidate
    
    @staticmethod
    def get_default_app_roi(frame_width: int, frame_height: int) -> tuple:
        """
        获取默认的T_app ROI（底部中间区域）
        
        Args:
            frame_width: 帧宽度
            frame_height: 帧高度
            
        Returns:
            默认ROI坐标 (x1, y1, x2, y2)
        """
        x1 = int(0.30 * frame_width)
        y1 = int(0.75 * frame_height)
        x2 = int(0.70 * frame_width)
        y2 = int(0.95 * frame_height)
        
        return (x1, y1, x2, y2)

