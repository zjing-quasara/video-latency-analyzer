"""
ROI跟踪器
管理T_real的ROI位置，实现快速跟踪和智能搜索
"""
from typing import Optional, Tuple


class ROITracker:
    """T_real ROI跟踪器"""
    
    def __init__(self):
        """初始化跟踪器"""
        self.roi: Optional[Tuple[int, int, int, int]] = None  # (x1, y1, x2, y2)
        self.roi_confidence: float = 0.0  # ROI置信度 0.0-1.0
        self.consecutive_fails: int = 0  # 连续失败次数
        self.last_success_frame: int = -1  # 上次成功的帧号
        self.total_uses: int = 0  # ROI使用次数
        self.success_count: int = 0  # 成功次数
    
    def has_valid_roi(self, current_frame_idx: int) -> bool:
        """
        判断历史ROI是否有效
        
        Args:
            current_frame_idx: 当前帧号
            
        Returns:
            True表示ROI有效，可以使用快速跟踪
        """
        # 条件1: ROI必须存在
        if self.roi is None:
            return False
        
        # 条件2: 连续失败不能超过3次
        if self.consecutive_fails >= 3:
            return False
        
        # 条件3: 时间间隔不能超过100帧
        frame_gap = current_frame_idx - self.last_success_frame
        if frame_gap > 100:
            return False
        
        # 条件4: 置信度必须≥0.5
        if self.roi_confidence < 0.5:
            return False
        
        return True
    
    def get_search_region(self, frame_shape: Tuple[int, int], expand_ratio: float = 0.1) -> Tuple[int, int, int, int]:
        """
        获取搜索区域（历史ROI±expand_ratio）
        
        Args:
            frame_shape: 视频帧尺寸 (height, width)
            expand_ratio: 扩展比例，默认0.1（±10%）
            
        Returns:
            搜索区域 (x1, y1, x2, y2)
        """
        if self.roi is None:
            raise ValueError("ROI不存在，无法获取搜索区域")
        
        h, w = frame_shape
        x1, y1, x2, y2 = self.roi
        
        # 计算ROI的宽高
        roi_w = x2 - x1
        roi_h = y2 - y1
        
        # 扩展
        expand_w = int(roi_w * expand_ratio)
        expand_h = int(roi_h * expand_ratio)
        
        # 新的搜索区域
        new_x1 = max(0, x1 - expand_w)
        new_y1 = max(0, y1 - expand_h)
        new_x2 = min(w, x2 + expand_w)
        new_y2 = min(h, y2 + expand_h)
        
        return (new_x1, new_y1, new_x2, new_y2)
    
    def update_roi(self, roi: Tuple[int, int, int, int], frame_idx: int, success: bool):
        """
        更新ROI状态
        
        Args:
            roi: 新的ROI位置
            frame_idx: 当前帧号
            success: 是否识别成功
        """
        self.total_uses += 1
        
        if success:
            # 识别成功
            self.roi = roi
            self.last_success_frame = frame_idx
            self.consecutive_fails = 0
            self.success_count += 1
            
            # 提升置信度
            if self.roi_confidence < 0.6:
                # 新建状态：快速提升
                self.roi_confidence = min(1.0, self.roi_confidence + 0.1)
            else:
                # 稳定状态：缓慢提升
                self.roi_confidence = min(1.0, self.roi_confidence + 0.05)
        else:
            # 识别失败
            self.consecutive_fails += 1
            
            # 降低置信度
            self.roi_confidence = max(0.0, self.roi_confidence - 0.1)
            
            # 连续失败3次或置信度太低：清除ROI
            if self.consecutive_fails >= 3 or self.roi_confidence < 0.3:
                self.reset()
    
    def establish_roi(self, roi: Tuple[int, int, int, int], frame_idx: int):
        """
        建立新ROI（首次定位成功）
        
        Args:
            roi: ROI位置
            frame_idx: 当前帧号
        """
        self.roi = roi
        self.roi_confidence = 0.5  # 初始置信度
        self.consecutive_fails = 0
        self.last_success_frame = frame_idx
        self.total_uses = 1
        self.success_count = 1
    
    def reset(self):
        """重置跟踪器（清除ROI）"""
        self.roi = None
        self.roi_confidence = 0.0
        self.consecutive_fails = 0
        self.last_success_frame = -1
    
    def get_stats(self) -> dict:
        """
        获取统计信息
        
        Returns:
            统计字典
        """
        success_rate = (self.success_count / self.total_uses * 100) if self.total_uses > 0 else 0.0
        return {
            'has_roi': self.roi is not None,
            'confidence': self.roi_confidence,
            'consecutive_fails': self.consecutive_fails,
            'total_uses': self.total_uses,
            'success_count': self.success_count,
            'success_rate': success_rate,
            'last_success_frame': self.last_success_frame
        }

