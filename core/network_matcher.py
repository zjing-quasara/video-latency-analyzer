"""
网络数据匹配器
按时间戳将视频分析数据和网络监控日志进行关联匹配
"""
import csv
from typing import List, Dict, Optional
from pathlib import Path
import bisect


class NetworkMatcher:
    """网络数据匹配器"""
    
    def __init__(self, tolerance: float = 1.0):
        """
        初始化匹配器
        
        Args:
            tolerance: 时间戳匹配容差（秒），默认1秒
        """
        self.tolerance = tolerance
    
    @staticmethod
    def load_network_log(filepath: str) -> List[Dict]:
        """
        加载网络监控日志CSV文件
        
        Args:
            filepath: CSV文件路径
            
        Returns:
            网络日志数据列表，按时间戳排序
        """
        if not Path(filepath).exists():
            raise FileNotFoundError(f"网络日志文件不存在: {filepath}")
        
        data = []
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    data.append({
                        'timestamp': float(row['timestamp']),
                        'datetime': row.get('datetime', ''),
                        'target': row.get('target', ''),
                        'ping_ms': float(row['ping_ms']) if row.get('ping_ms') else None,
                        'status': row.get('status', 'unknown')
                    })
                except (ValueError, KeyError) as e:
                    # 跳过格式错误的行
                    continue
        
        # 按时间戳排序
        data.sort(key=lambda x: x['timestamp'])
        return data
    
    @staticmethod
    def load_video_analysis(filepath: str) -> List[Dict]:
        """
        加载视频分析结果CSV文件
        
        Args:
            filepath: CSV文件路径
            
        Returns:
            视频分析数据列表
        """
        if not Path(filepath).exists():
            raise FileNotFoundError(f"视频分析文件不存在: {filepath}")
        
        data = []
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    data.append({
                        'timestamp': float(row['timestamp']),
                        'datetime': row.get('datetime', ''),
                        'T_app': row.get('T_app', ''),
                        'T_real': row.get('T_real', ''),
                        'delay_ms': float(row['delay_ms']) if row.get('delay_ms') else None
                    })
                except (ValueError, KeyError) as e:
                    continue
        
        return data
    
    def find_nearest_ping(self, network_data: List[Dict], timestamp: float) -> Optional[Dict]:
        """
        查找最接近指定时间戳的ping数据
        
        Args:
            network_data: 网络日志数据（已排序）
            timestamp: 目标时间戳
            
        Returns:
            最近的ping数据，如果超出容差范围返回None
        """
        if not network_data:
            return None
        
        # 使用二分查找定位最近的时间戳
        timestamps = [item['timestamp'] for item in network_data]
        idx = bisect.bisect_left(timestamps, timestamp)
        
        # 检查左右两个候选
        candidates = []
        if idx > 0:
            candidates.append((idx - 1, abs(network_data[idx - 1]['timestamp'] - timestamp)))
        if idx < len(network_data):
            candidates.append((idx, abs(network_data[idx]['timestamp'] - timestamp)))
        
        if not candidates:
            return None
        
        # 选择时间差最小的
        best_idx, time_diff = min(candidates, key=lambda x: x[1])
        
        if time_diff <= self.tolerance:
            return network_data[best_idx].copy()
        
        return None
    
    def match(
        self,
        video_data: List[Dict],
        phone_log: Optional[List[Dict]] = None,
        pc_log: Optional[List[Dict]] = None
    ) -> List[Dict]:
        """
        匹配视频数据和网络日志
        
        Args:
            video_data: 视频分析数据
            phone_log: 手机网络日志（可选）
            pc_log: 电脑网络日志（可选）
            
        Returns:
            合并后的数据
        """
        result = []
        
        for frame in video_data:
            timestamp = frame['timestamp']
            merged = frame.copy()
            
            # 匹配手机ping
            if phone_log:
                phone_ping = self.find_nearest_ping(phone_log, timestamp)
                if phone_ping:
                    merged['phone_ping_ms'] = phone_ping['ping_ms']
                    merged['phone_status'] = phone_ping['status']
                else:
                    merged['phone_ping_ms'] = None
                    merged['phone_status'] = 'no_data'
            
            # 匹配电脑ping
            if pc_log:
                pc_ping = self.find_nearest_ping(pc_log, timestamp)
                if pc_ping:
                    merged['pc_ping_ms'] = pc_ping['ping_ms']
                    merged['pc_status'] = pc_ping['status']
                else:
                    merged['pc_ping_ms'] = None
                    merged['pc_status'] = 'no_data'
            
            result.append(merged)
        
        return result
    
    @staticmethod
    def save_merged_data(data: List[Dict], filepath: str):
        """
        保存合并后的数据到CSV文件
        
        Args:
            data: 合并后的数据
            filepath: 输出文件路径
        """
        if not data:
            return
        
        # 确定所有字段
        fieldnames = list(data[0].keys())
        
        with open(filepath, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)


def match_network_logs(
    video_csv: str,
    phone_csv: Optional[str] = None,
    pc_csv: Optional[str] = None,
    output_csv: Optional[str] = None,
    tolerance: float = 1.0
) -> List[Dict]:
    """
    便捷函数：匹配网络日志
    
    Args:
        video_csv: 视频分析CSV文件路径
        phone_csv: 手机网络日志CSV文件路径（可选）
        pc_csv: 电脑网络日志CSV文件路径（可选）
        output_csv: 输出CSV文件路径（可选）
        tolerance: 时间戳匹配容差（秒）
        
    Returns:
        合并后的数据
    """
    matcher = NetworkMatcher(tolerance=tolerance)
    
    # 加载数据
    video_data = matcher.load_video_analysis(video_csv)
    phone_log = matcher.load_network_log(phone_csv) if phone_csv else None
    pc_log = matcher.load_network_log(pc_csv) if pc_csv else None
    
    # 匹配
    merged_data = matcher.match(video_data, phone_log, pc_log)
    
    # 保存
    if output_csv:
        matcher.save_merged_data(merged_data, output_csv)
    
    return merged_data


