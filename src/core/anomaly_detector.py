"""
延迟异常检测模块 - 并联检测器架构
使用两个独立的检测器：
1. 检测器A：跳变一致性检测（实时）- 基于时钟同步
2. 检测器B：连续回退检测（回溯）- 基于多数派原则
"""
from typing import List, Optional, Tuple, Dict
import statistics


class AnomalyDetector:
    """
    延迟异常检测器 - 并联架构
    
    设计理念：
    - 不使用中位数窗口（不依赖历史统计）
    - 基于物理约束：两个时钟应该同步
    - 实时检测 + 回溯修正
    """
    
    def __init__(self, hard_delay_max_ms: float = 3000):
        """
        初始化检测器
        
        Args:
            hard_delay_max_ms: 硬性延时上限（毫秒），超过此值直接标记为wrong
        """
        # 基础配置
        self.hard_delay_max_ms = hard_delay_max_ms
        
        # 上一帧的时间（用于计算增量）
        self.last_app_time_ms: Optional[float] = None
        self.last_real_time_ms: Optional[float] = None
        
        # 正常延迟历史（用于统计检测，保留兼容性）
        self.normal_delays: List[float] = []
        
        # 检测器B：正常帧历史记录（用于回退检测）
        # 格式：{frame_idx: {'app_time': xxx, 'real_time': xxx}}
        self.normal_frames: Dict[int, Dict] = {}
        
        # 当前帧号（用于回溯）
        self.current_frame_idx: int = 0
        
        # 帧历史记录（用于回溯重识别）
        # 格式：{frame_idx: {'app_time': xxx, 'real_time': xxx, 'delay': xxx, 'status': xxx}}
        self.frame_history: Dict[int, Dict] = {}
    
    def check_detector_a(
        self,
        frame_idx: int,
        app_time_ms: float,
        real_time_ms: float,
        delay_ms: float
    ) -> Tuple[bool, Optional[str], bool]:
        """
        检测器A：跳变一致性检测（实时触发）
        
        基于物理约束：T_app和T_real应该同步增长
        如果 |ΔT_app - ΔT_real| 太大 → 需要重识别
        
        Args:
            frame_idx: 帧索引
            app_time_ms: T_app时间（毫秒）
            real_time_ms: T_real时间（毫秒）
            delay_ms: 延迟值（毫秒）
            
        Returns:
            (是否正常, 异常原因, 是否需要重识别)
        """
        # 硬性延时上限（最高优先级）
        if delay_ms > self.hard_delay_max_ms:
            return False, f"延迟超过硬性上限{self.hard_delay_max_ms}ms", False
        
        # 物理极限检查
        if abs(delay_ms) > 10000:
            return False, f"延迟超过物理极限: {delay_ms/1000:.1f}秒", False
        
        if delay_ms < -5000:
            return False, f"负延迟过大: {delay_ms/1000:.1f}秒", False
        
        # 如果没有上一帧，跳过跳变检测
        if self.last_app_time_ms is None or self.last_real_time_ms is None:
            return True, None, False
        
        # 计算时间增量
        delta_app = app_time_ms - self.last_app_time_ms
        delta_real = real_time_ms - self.last_real_time_ms
        
        # 跳变一致性检查
        # 阈值：至少500ms 或 delta_app的2倍
        threshold = max(500, abs(delta_app) * 2.0)
        increment_diff = abs(delta_app - delta_real)
        
        if increment_diff > threshold:
            # 跳变不一致 → 需要重识别
            return False, f"时钟不同步(ΔT_app={delta_app:.0f}ms, ΔT_real={delta_real:.0f}ms, 差异={increment_diff:.0f}ms)", True
        
        # 检查通过
        return True, None, False
    
    def check_detector_b(
        self,
        frame_idx: int,
        real_time_ms: float
    ) -> Tuple[bool, Optional[str]]:
        """
        检测器B：回退检测（检查所有正常帧，只和前2帧比对）
        
        检测逻辑：
        检查当前帧是否比前2个正常帧小（回退）
        
        Args:
            frame_idx: 当前帧索引
            real_time_ms: 当前T_real时间
            
        Returns:
            (是否正常, 异常原因)
        """
        tolerance = 1000  # 1秒容错，避免OCR微小抖动
        
        # 获取前2个正常帧（按帧号排序，只取当前帧之前的）
        prev_frames = sorted([idx for idx in self.normal_frames.keys() if idx < frame_idx], reverse=True)[:2]
        
        # 检查是否比前2帧小（回退）
        for prev_idx in prev_frames:
            prev_time = self.normal_frames[prev_idx]['real_time']
            
            if real_time_ms < prev_time - tolerance:
                # 回退了
                return False, f"时间回退(当前={real_time_ms:.0f}ms < 帧{prev_idx}={prev_time:.0f}ms)"
        
        # 没有回退
        return True, None
    
    def add_normal_frame(
        self,
        frame_idx: int,
        app_time_ms: float,
        real_time_ms: float
    ):
        """
        添加正常帧到历史记录（供检测器B使用）
        
        Args:
            frame_idx: 帧索引
            app_time_ms: T_app时间
            real_time_ms: T_real时间
        """
        self.normal_frames[frame_idx] = {
            'app_time': app_time_ms,
            'real_time': real_time_ms
        }
        
        # 维护历史记录大小（最多保留100帧）
        if len(self.normal_frames) > 100:
            # 删除最老的帧
            oldest_idx = min(self.normal_frames.keys())
            del self.normal_frames[oldest_idx]
    
    def update_frame(
        self,
        frame_idx: int,
        app_time_ms: float,
        real_time_ms: float
    ):
        """
        更新当前帧的时间（仅在通过检查后调用）
        同时添加到正常帧历史记录
        
        Args:
            frame_idx: 帧索引
            app_time_ms: T_app时间
            real_time_ms: T_real时间
        """
        self.last_app_time_ms = app_time_ms
        self.last_real_time_ms = real_time_ms
        self.current_frame_idx = frame_idx
        
        # 添加到正常帧历史记录（供检测器B使用）
        self.add_normal_frame(frame_idx, app_time_ms, real_time_ms)
    
    def add_normal_delay(self, delay_ms: float):
        """
        添加正常延迟值到历史（保留兼容性）
        
        Args:
            delay_ms: 延迟值（毫秒）
        """
        self.normal_delays.append(delay_ms)
        
        # 保持历史长度在合理范围
        if len(self.normal_delays) > 500:
            self.normal_delays = self.normal_delays[-500:]
    
    def check_statistical(self, delay_ms: float) -> Tuple[bool, Optional[str], Optional[float]]:
        """
        统计检测（MAD方法）- 保留兼容性
        
        Args:
            delay_ms: 待检测的延迟值
            
        Returns:
            (是否正常, 异常原因, z-score)
        """
        # 前提：至少有30个正常样本
        if len(self.normal_delays) < 30:
            return True, None, None
        
        # 计算中位数和MAD
        median = statistics.median(self.normal_delays)
        
        # MAD = median(|xi - median|)
        absolute_deviations = [abs(d - median) for d in self.normal_delays]
        mad = statistics.median(absolute_deviations)
        
        # 避免MAD为0
        if mad < 0.01:
            mad = 0.01
        
        # 计算Modified Z-Score
        z_score = 0.6745 * (delay_ms - median) / mad
        
        # 阈值：5.0（宽松）
        if abs(z_score) > 5.0:
            return False, f"统计异常: z-score={z_score:.2f}", z_score
        
        return True, None, z_score
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        if len(self.normal_delays) == 0:
            return {
                'sample_count': 0,
                'median': None,
                'min': None,
                'max': None,
                'mean': None
            }
        
        return {
            'sample_count': len(self.normal_delays),
            'median': statistics.median(self.normal_delays),
            'min': min(self.normal_delays),
            'max': max(self.normal_delays),
            'mean': statistics.mean(self.normal_delays)
        }
    
    def reset(self):
        """重置检测器"""
        self.normal_delays.clear()
        self.normal_frames.clear()
        self.frame_history.clear()
        self.last_app_time_ms = None
        self.last_real_time_ms = None
        self.current_frame_idx = 0
