"""
网络数据匹配器
按时间戳将视频分析数据和网络监控日志进行关联匹配
"""
import csv
from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime, timedelta
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
    def parse_time_to_timestamp(time_str: str, base_date: Optional[datetime] = None) -> Optional[float]:
        """
        将时间字符串（HH:MM:SS.mmm）转换为Unix时间戳
        
        Args:
            time_str: 时间字符串，格式如 "19:29:30.246"
            base_date: 基准日期（可选，默认今天）
            
        Returns:
            Unix时间戳（秒），如果解析失败返回None
        """
        if not time_str:
            return None
        
        try:
            # 解析时间部分
            time_parts = time_str.split(':')
            if len(time_parts) != 3:
                return None
            
            hour = int(time_parts[0])
            minute = int(time_parts[1])
            
            # 解析秒和毫秒
            sec_parts = time_parts[2].split('.')
            second = int(sec_parts[0])
            microsecond = 0
            if len(sec_parts) > 1:
                # 毫秒转微秒
                ms_str = sec_parts[1].ljust(6, '0')[:6]  # 补齐到6位
                microsecond = int(ms_str)
            
            # 使用基准日期或今天
            if base_date is None:
                base_date = datetime.now()
            
            # 构造完整的datetime
            dt = datetime(
                year=base_date.year,
                month=base_date.month,
                day=base_date.day,
                hour=hour,
                minute=minute,
                second=second,
                microsecond=microsecond
            )
            
            # 转换为Unix时间戳
            return dt.timestamp()
            
        except (ValueError, IndexError):
            return None
    
    @staticmethod
    def calculate_time_offset(video_data: List[Dict], network_data: List[Dict], time_field: str = 'T_real') -> Optional[float]:
        """
        计算视频相对时间和网络绝对时间之间的偏移量
        
        通过匹配视频中的时间字段（T_real或T_app）和网络日志的时间戳来计算偏移量
        
        Args:
            video_data: 视频分析数据（包含timestamp和T_real/T_app）
            network_data: 网络日志数据（包含timestamp）
            time_field: 使用哪个时间字段进行匹配（'T_real' 或 'T_app'）
            
        Returns:
            时间偏移量（秒），video_timestamp + offset = network_timestamp
            如果无法计算返回None
        """
        if not video_data or not network_data:
            return None
        
        # 找到第一个有有效时间字段的视频帧
        first_valid_frame = None
        for frame in video_data:
            if frame.get(time_field):
                first_valid_frame = frame
                break
        
        if not first_valid_frame:
            print(f"[WARNING] 视频数据中没有找到{time_field}，无法计算时间偏移量")
            return None
        
        # 获取网络日志的第一个时间戳，用它的日期作为基准
        network_first_ts = network_data[0]['timestamp']
        base_date = datetime.fromtimestamp(network_first_ts)
        
        # 将时间字段转换为绝对时间戳
        time_str = first_valid_frame[time_field]
        time_timestamp = NetworkMatcher.parse_time_to_timestamp(time_str, base_date)
        
        if time_timestamp is None:
            print(f"[WARNING] 无法解析{time_field}时间: {time_str}")
            return None
        
        # 计算偏移量
        video_relative_time = first_valid_frame['timestamp']
        offset = time_timestamp - video_relative_time
        
        print(f"[INFO] 时间偏移量计算 ({time_field}):")
        print(f"  - 视频相对时间: {video_relative_time:.3f}s")
        print(f"  - {time_field}: {time_str}")
        print(f"  - {time_field}绝对时间戳: {time_timestamp:.3f}")
        print(f"  - 计算出的偏移量: {offset:.3f}s")
        print(f"  - 基准日期: {base_date.strftime('%Y-%m-%d')}")
        
        return offset
    
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
                    # 兼容两种时间戳列名: timestamp 和 video_time_s
                    timestamp_value = row.get('timestamp') or row.get('video_time_s')
                    if not timestamp_value:
                        continue
                    
                    data.append({
                        'timestamp': float(timestamp_value),
                        'datetime': row.get('datetime', ''),
                        'T_app': row.get('app_time_str', row.get('T_app', '')),
                        'T_real': row.get('real_time_str', row.get('T_real', '')),
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
        pc_log: Optional[List[Dict]] = None,
        auto_offset: bool = True
    ) -> List[Dict]:
        """
        匹配视频数据和网络日志
        
        重要：
        - T_app（手机应用时间）对应手机端网络日志
        - T_real（真实世界时间）对应电脑端网络日志
        
        Args:
            video_data: 视频分析数据
            phone_log: 手机网络日志（可选）
            pc_log: 电脑网络日志（可选）
            auto_offset: 是否自动计算时间偏移量（默认True）
            
        Returns:
            合并后的数据
        """
        result = []
        phone_offset = None
        pc_offset = None
        
        # 自动计算时间偏移量
        if auto_offset:
            # T_app 对应手机端日志
            if phone_log:
                phone_offset = self.calculate_time_offset(video_data, phone_log, time_field='T_app')
                if phone_offset is None:
                    print("[WARNING] 无法根据T_app计算手机端时间偏移量")
                    print("[WARNING] 这可能导致无法匹配手机网络数据")
            
            # T_real 对应电脑端日志
            if pc_log:
                pc_offset = self.calculate_time_offset(video_data, pc_log, time_field='T_real')
                if pc_offset is None:
                    print("[WARNING] 无法根据T_real计算电脑端时间偏移量")
                    print("[WARNING] 这可能导致无法匹配电脑网络数据")
        
        for frame in video_data:
            timestamp = frame['timestamp']
            merged = frame.copy()
            
            # 匹配手机ping（使用T_app对应的偏移量）
            if phone_log:
                phone_absolute_ts = timestamp + phone_offset if phone_offset is not None else timestamp
                phone_ping = self.find_nearest_ping(phone_log, phone_absolute_ts)
                if phone_ping:
                    merged['phone_ping_ms'] = phone_ping['ping_ms']
                    merged['phone_status'] = phone_ping['status']
                else:
                    merged['phone_ping_ms'] = None
                    merged['phone_status'] = 'no_data'
            
            # 匹配电脑ping（使用T_real对应的偏移量）
            if pc_log:
                pc_absolute_ts = timestamp + pc_offset if pc_offset is not None else timestamp
                pc_ping = self.find_nearest_ping(pc_log, pc_absolute_ts)
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
    tolerance: float = 1.0,
    auto_offset: bool = True
) -> List[Dict]:
    """
    便捷函数：匹配网络日志
    
    Args:
        video_csv: 视频分析CSV文件路径
        phone_csv: 手机网络日志CSV文件路径（可选）
        pc_csv: 电脑网络日志CSV文件路径（可选）
        output_csv: 输出CSV文件路径（可选）
        tolerance: 时间戳匹配容差（秒）
        auto_offset: 是否自动计算时间偏移量（默认True）
        
    Returns:
        合并后的数据
    """
    matcher = NetworkMatcher(tolerance=tolerance)
    
    # 加载数据
    video_data = matcher.load_video_analysis(video_csv)
    phone_log = matcher.load_network_log(phone_csv) if phone_csv else None
    pc_log = matcher.load_network_log(pc_csv) if pc_csv else None
    
    # 匹配
    merged_data = matcher.match(video_data, phone_log, pc_log, auto_offset=auto_offset)
    
    # 保存
    if output_csv:
        matcher.save_merged_data(merged_data, output_csv)
    
    return merged_data


