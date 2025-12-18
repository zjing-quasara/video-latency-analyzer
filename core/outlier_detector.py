"""
延迟异常值检测器 - 基于MAD（中位数绝对偏差）
"""
import statistics
from typing import Tuple, Optional


class DelayOutlierDetector:
    """
    基于MAD的延迟异常值检测
    
    检测层级：
    1. 物理极限：±10秒
    2. 时间倒退：不允许
    3. MAD统计：偏离中位数（z > 5.0，宽松）
    4. 延迟跳变：相邻帧±500ms（宽松）
    """
    
    def __init__(self, window_size: int = 30):
        """
        Args:
            window_size: 滑动窗口大小，保留最近N帧的正常延迟
        """
        self.valid_delays = []  # 正常延迟历史（用于统计）
        self.window_size = window_size
        
    def is_outlier(self, delay_ms: float, 
                   app_time_ms: Optional[float] = None,
                   real_time_ms: Optional[float] = None,
                   last_app_ms: Optional[float] = None,
                   last_real_ms: Optional[float] = None) -> Tuple[bool, str]:
        """
        判断延迟是否为异常值
        
        Args:
            delay_ms: 当前延迟（毫秒）
            app_time_ms: T_app时间（毫秒）
            real_time_ms: T_real时间（毫秒）
            last_app_ms: 上一帧T_app时间（毫秒）
            last_real_ms: 上一帧T_real时间（毫秒）
            
        Returns:
            (是否异常, 异常原因)
        """
        # ========== 第1层：物理极限 ==========
        PHYSICAL_MAX = 10000  # ±10秒（宽松）
        if abs(delay_ms) > PHYSICAL_MAX:
            return True, f"延迟{delay_ms:.0f}ms超过±10秒"
        
        # ========== 第2层：时间倒退 ==========
        if last_app_ms is not None and app_time_ms is not None:
            if app_time_ms < last_app_ms:
                return True, "T_app时间倒退"
        
        if last_real_ms is not None and real_time_ms is not None:
            if real_time_ms < last_real_ms:
                return True, "T_real时间倒退"
        
        # ========== 第3层：MAD统计（需要至少10帧数据）==========
        if len(self.valid_delays) >= 10:
            median = statistics.median(self.valid_delays)
            deviations = [abs(x - median) for x in self.valid_delays]
            mad = statistics.median(deviations)
            
            # MAD太小，使用默认值
            if mad < 5:
                mad = 20
            
            # 修正的z-score
            modified_z = 0.6745 * (delay_ms - median) / mad
            
            # 宽松阈值：5.0（而非3.5）
            if abs(modified_z) > 5.0:
                return True, f"偏离中位数{median:.0f}ms过大(z={modified_z:.1f})"
        
        # ========== 第4层：延迟跳变 ==========
        if len(self.valid_delays) > 0:
            last_valid = self.valid_delays[-1]
            jump = abs(delay_ms - last_valid)
            
            # 宽松阈值：500ms（而非200ms）
            if jump > 500:
                return True, f"延迟跳变{jump:.0f}ms过大"
        
        # ========== 通过所有检查 ==========
        self._add_valid_delay(delay_ms)
        return False, ""
    
    def _add_valid_delay(self, delay_ms: float):
        """添加正常延迟到历史记录"""
        self.valid_delays.append(delay_ms)
        
        # 维护滑动窗口
        if len(self.valid_delays) > self.window_size:
            self.valid_delays.pop(0)
    
    def get_statistics(self) -> dict:
        """获取当前统计信息（用于调试）"""
        if len(self.valid_delays) < 2:
            return {
                'count': len(self.valid_delays),
                'median': None,
                'mad': None
            }
        
        median = statistics.median(self.valid_delays)
        mad = statistics.median([abs(x - median) for x in self.valid_delays])
        
        return {
            'count': len(self.valid_delays),
            'median': median,
            'mad': mad,
            'min': min(self.valid_delays),
            'max': max(self.valid_delays)
        }

