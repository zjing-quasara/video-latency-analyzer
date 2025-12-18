"""
延迟异常检测模块
使用多层检测策略识别异常延迟值
"""
from typing import List, Optional, Tuple
import statistics


class AnomalyDetector:
    """延迟异常检测器"""
    
    def __init__(self):
        """初始化检测器"""
        self.normal_delays: List[float] = []  # 正常延迟值历史
        self.last_app_time_ms: Optional[float] = None  # 上一帧T_app(ms)
        self.last_real_time_ms: Optional[float] = None  # 上一帧T_real(ms)
        self.median: Optional[float] = None  # 中位数
        self.mad: Optional[float] = None  # MAD值
    
    def check_immediate(
        self,
        app_time_ms: float,
        real_time_ms: float,
        delay_ms: float
    ) -> Tuple[bool, Optional[str]]:
        """
        立即检测（硬阈值）- 在计算延迟时立即调用
        
        检测内容：
        1. 时间倒退
        2. 物理极限（>10秒）
        3. 负延迟太大（<-5秒）
        
        Args:
            app_time_ms: T_app时间（毫秒）
            real_time_ms: T_real时间（毫秒）
            delay_ms: 延迟值（毫秒）
            
        Returns:
            (是否正常, 异常原因)
            - True: 正常，可以加入历史
            - False: 异常，不加入历史
        """
        # 检查1: 时间倒退
        if self.last_app_time_ms is not None:
            if app_time_ms < self.last_app_time_ms:
                return False, "T_app时间倒退"
        
        if self.last_real_time_ms is not None:
            if real_time_ms < self.last_real_time_ms:
                return False, "T_real时间倒退"
        
        # 检查2: 物理极限（延迟>10秒）
        if abs(delay_ms) > 10000:
            return False, f"延迟超过物理极限: {delay_ms/1000:.1f}秒"
        
        # 检查3: 负延迟太大（T_real比T_app早5秒+）
        if delay_ms < -5000:
            return False, f"负延迟过大: {delay_ms/1000:.1f}秒"
        
        # 更新上一帧时间
        self.last_app_time_ms = app_time_ms
        self.last_real_time_ms = real_time_ms
        
        return True, None
    
    def add_normal_delay(self, delay_ms: float):
        """
        添加正常延迟值到历史（通过立即检测后调用）
        
        Args:
            delay_ms: 延迟值（毫秒）
        """
        self.normal_delays.append(delay_ms)
        
        # 保持历史长度在合理范围
        if len(self.normal_delays) > 500:
            self.normal_delays = self.normal_delays[-500:]
    
    def check_statistical(self, delay_ms: float) -> Tuple[bool, Optional[str], Optional[float]]:
        """
        统计检测（MAD方法）- 每30帧批量调用一次
        
        使用MAD (Median Absolute Deviation) 检测异常值
        
        Args:
            delay_ms: 待检测的延迟值
            
        Returns:
            (是否正常, 异常原因, z-score)
        """
        # 前提：至少有30个正常样本
        if len(self.normal_delays) < 30:
            return True, None, None  # 样本不足，暂不检测
        
        # 计算中位数和MAD
        self.median = statistics.median(self.normal_delays)
        
        # MAD = median(|xi - median|)
        absolute_deviations = [abs(d - self.median) for d in self.normal_delays]
        self.mad = statistics.median(absolute_deviations)
        
        # 避免MAD为0（所有值完全相同）
        if self.mad < 0.01:
            self.mad = 0.01
        
        # 计算Modified Z-Score
        # z = 0.6745 * (x - median) / MAD
        z_score = 0.6745 * (delay_ms - self.median) / self.mad
        
        # 阈值：5.0（非常宽松，只抓最离谱的异常）
        if abs(z_score) > 5.0:
            return False, f"统计异常: z-score={z_score:.2f}", z_score
        
        return True, None, z_score
    
    def get_stats(self) -> dict:
        """
        获取统计信息
        
        Returns:
            统计字典
        """
        if len(self.normal_delays) == 0:
            return {
                'sample_count': 0,
                'median': None,
                'mad': None,
                'min': None,
                'max': None,
                'mean': None
            }
        
        return {
            'sample_count': len(self.normal_delays),
            'median': self.median or statistics.median(self.normal_delays),
            'mad': self.mad,
            'min': min(self.normal_delays),
            'max': max(self.normal_delays),
            'mean': statistics.mean(self.normal_delays)
        }
    
    def reset(self):
        """重置检测器"""
        self.normal_delays.clear()
        self.last_app_time_ms = None
        self.last_real_time_ms = None
        self.median = None
        self.mad = None

