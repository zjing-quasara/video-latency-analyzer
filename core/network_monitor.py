"""
网络监控核心模块
用于在录制视频时同步监控网络状况（双端监控）
"""
import time
import platform
import subprocess
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable, Dict, List
from dataclasses import dataclass
from utils.logger import get_logger


@dataclass
class NetworkStatus:
    """网络状态数据"""
    timestamp: float  # Unix时间戳
    ping_ms: Optional[float]  # ping延迟（毫秒）
    packet_loss: float  # 丢包率（0-1）
    status: str  # ok/timeout/error
    target: str  # 目标地址


class NetworkMonitor:
    """
    网络监控器
    
    使用场景：
    1. 扫地机端监控：ping扫地机局域网IP + 云服务器
    2. 手机端监控：ping云服务器
    
    示例：
        monitor = NetworkMonitor(
            name="扫地机端",
            targets=["192.168.1.100", "cloud.dreame.tech"],
            interval=1.0
        )
        monitor.start()
        # ... 录制视频 ...
        monitor.stop()
        monitor.save_log("network_log_robot.csv")
    """
    
    def __init__(
        self, 
        name: str = "网络监控",
        targets: List[str] = None,
        interval: float = 1.0,
        timeout: float = 2.0,
        high_latency_threshold: int = 100,
        callback: Optional[Callable] = None
    ):
        """
        初始化网络监控器
        
        Args:
            name: 监控器名称（用于日志标识）
            targets: 目标地址列表（IP或域名）
            interval: 采样间隔（秒）
            timeout: ping超时时间（秒）
            high_latency_threshold: 高延迟阈值（毫秒）
            callback: 状态回调函数 callback(status: NetworkStatus)
        """
        self.logger = get_logger(f'NetworkMonitor-{name}')
        self.name = name
        self.targets = targets or ["8.8.8.8"]  # 默认ping Google DNS
        self.interval = interval
        self.timeout = timeout
        self.high_latency_threshold = high_latency_threshold
        self.callback = callback
        
        self.running = False
        self.thread = None
        self.data: List[NetworkStatus] = []
        self.start_time = None
        
        self.logger.info(f"网络监控器初始化: targets={self.targets}, interval={interval}s")
    
    def start(self):
        """启动监控"""
        if self.running:
            self.logger.warning("监控已在运行")
            return
        
        self.running = True
        self.start_time = time.time()
        self.data.clear()
        
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        
        self.logger.info(f"网络监控已启动: {self.name}")
    
    def stop(self):
        """停止监控"""
        if not self.running:
            return
        
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        
        duration = time.time() - self.start_time if self.start_time else 0
        self.logger.info(f"网络监控已停止: {self.name}, 共监控 {duration:.1f}秒, {len(self.data)} 条记录")
    
    def _monitor_loop(self):
        """监控循环（在后台线程运行）"""
        self.logger.info(f"监控循环开始: targets={self.targets}")
        
        while self.running:
            loop_start = time.time()
            
            # 对每个目标进行ping
            for target in self.targets:
                if not self.running:
                    break
                
                status = self._ping_once(target)
                self.data.append(status)
                
                # 回调
                if self.callback:
                    try:
                        self.callback(status)
                    except Exception as e:
                        self.logger.error(f"回调函数异常: {e}")
                
                # 日志
                if status.status == 'ok':
                    if status.ping_ms > self.high_latency_threshold:
                        self.logger.warning(f"高延迟: {target} = {status.ping_ms:.1f}ms")
                else:
                    self.logger.warning(f"Ping失败: {target} = {status.status}")
            
            # 等待到下一个采样时间
            elapsed = time.time() - loop_start
            sleep_time = max(0, self.interval - elapsed)
            time.sleep(sleep_time)
        
        self.logger.info("监控循环结束")
    
    def _ping_once(self, target: str) -> NetworkStatus:
        """
        执行一次ping
        
        Args:
            target: 目标地址（IP或域名）
            
        Returns:
            NetworkStatus对象
        """
        timestamp = time.time()
        
        try:
            # 根据操作系统选择ping命令
            system = platform.system().lower()
            
            if system == 'windows':
                # Windows: ping -n 1 -w 2000 target
                cmd = ['ping', '-n', '1', '-w', str(int(self.timeout * 1000)), target]
            else:
                # Linux/Mac: ping -c 1 -W 2 target
                cmd = ['ping', '-c', '1', '-W', str(int(self.timeout)), target]
            
            # 执行ping命令
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout + 1,
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == 'Windows' else 0
            )
            
            # 解析结果
            if result.returncode == 0:
                # 提取延迟时间
                output = result.stdout
                ping_ms = self._parse_ping_time(output)
                
                if ping_ms is not None:
                    return NetworkStatus(
                        timestamp=timestamp,
                        ping_ms=ping_ms,
                        packet_loss=0.0,
                        status='ok',
                        target=target
                    )
                else:
                    self.logger.warning(f"无法解析ping结果: {target}")
                    return NetworkStatus(
                        timestamp=timestamp,
                        ping_ms=None,
                        packet_loss=1.0,
                        status='parse_error',
                        target=target
                    )
            else:
                # Ping失败（超时或目标不可达）
                return NetworkStatus(
                    timestamp=timestamp,
                    ping_ms=None,
                    packet_loss=1.0,
                    status='timeout',
                    target=target
                )
        
        except subprocess.TimeoutExpired:
            return NetworkStatus(
                timestamp=timestamp,
                ping_ms=None,
                packet_loss=1.0,
                status='timeout',
                target=target
            )
        except Exception as e:
            self.logger.error(f"Ping异常: {target}, {e}")
            return NetworkStatus(
                timestamp=timestamp,
                ping_ms=None,
                packet_loss=1.0,
                status='error',
                target=target
            )
    
    def _parse_ping_time(self, output: str) -> Optional[float]:
        """
        从ping输出中提取延迟时间
        
        Args:
            output: ping命令输出
            
        Returns:
            延迟时间（毫秒）或None
        """
        import re
        
        # Windows: 时间=15ms 或 time=15ms
        # Linux/Mac: time=15.2 ms 或 time=15 ms
        patterns = [
            r'[时间时间time]*[=:]\s*(\d+(?:\.\d+)?)\s*ms',  # 通用模式
            r'平均\s*=\s*(\d+)ms',  # Windows中文
            r'Average\s*=\s*(\d+)ms',  # Windows英文
        ]
        
        for pattern in patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                return float(match.group(1))
        
        return None
    
    def get_statistics(self) -> Dict:
        """
        获取统计数据
        
        Returns:
            统计字典
        """
        if not self.data:
            return {
                'total_count': 0,
                'success_count': 0,
                'timeout_count': 0,
                'packet_loss_rate': 0.0,
                'avg_ping_ms': 0.0,
                'min_ping_ms': 0.0,
                'max_ping_ms': 0.0,
                'high_latency_count': 0
            }
        
        total_count = len(self.data)
        success_data = [d for d in self.data if d.status == 'ok' and d.ping_ms is not None]
        success_count = len(success_data)
        timeout_count = len([d for d in self.data if d.status in ('timeout', 'error')])
        
        if success_data:
            ping_values = [d.ping_ms for d in success_data]
            avg_ping = sum(ping_values) / len(ping_values)
            min_ping = min(ping_values)
            max_ping = max(ping_values)
            high_latency_count = len([p for p in ping_values if p > self.high_latency_threshold])
        else:
            avg_ping = 0.0
            min_ping = 0.0
            max_ping = 0.0
            high_latency_count = 0
        
        return {
            'total_count': total_count,
            'success_count': success_count,
            'timeout_count': timeout_count,
            'packet_loss_rate': timeout_count / total_count if total_count > 0 else 0.0,
            'avg_ping_ms': avg_ping,
            'min_ping_ms': min_ping,
            'max_ping_ms': max_ping,
            'high_latency_count': high_latency_count
        }
    
    def save_log(self, filepath: str):
        """
        保存监控日志到CSV文件
        
        Args:
            filepath: CSV文件路径
        """
        import csv
        
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # 写入表头
            writer.writerow([
                'timestamp',  # Unix时间戳
                'datetime',   # 可读时间
                'target',     # 目标地址
                'ping_ms',    # ping延迟
                'packet_loss',  # 丢包率
                'status'      # 状态
            ])
            
            # 写入数据
            for status in self.data:
                dt = datetime.fromtimestamp(status.timestamp).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                writer.writerow([
                    f"{status.timestamp:.3f}",
                    dt,
                    status.target,
                    f"{status.ping_ms:.2f}" if status.ping_ms is not None else '',
                    f"{status.packet_loss:.2f}",
                    status.status
                ])
        
        # 统计信息
        stats = self.get_statistics()
        self.logger.info(f"网络日志已保存: {filepath}")
        self.logger.info(f"统计: 总数={stats['total_count']}, "
                        f"成功={stats['success_count']}, "
                        f"超时={stats['timeout_count']}, "
                        f"丢包率={stats['packet_loss_rate']:.1%}, "
                        f"平均延迟={stats['avg_ping_ms']:.1f}ms")
    
    @staticmethod
    def load_log(filepath: str) -> List[NetworkStatus]:
        """
        从CSV文件加载网络日志
        
        Args:
            filepath: CSV文件路径
            
        Returns:
            NetworkStatus对象列表
        """
        import csv
        
        data = []
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append(NetworkStatus(
                    timestamp=float(row['timestamp']),
                    ping_ms=float(row['ping_ms']) if row['ping_ms'] else None,
                    packet_loss=float(row['packet_loss']),
                    status=row['status'],
                    target=row['target']
                ))
        
        return data


# 预设配置
class NetworkMonitorPresets:
    """网络监控预设配置"""
    
    @staticmethod
    def robot_side(robot_ip: str = None, cloud_server: str = "cloud.dreame.tech"):
        """
        扫地机端监控配置
        
        Args:
            robot_ip: 扫地机局域网IP（可选）
            cloud_server: 云服务器地址
        """
        targets = []
        if robot_ip:
            targets.append(robot_ip)
        targets.append(cloud_server)
        
        return {
            'name': '扫地机端',
            'targets': targets,
            'interval': 1.0,
            'timeout': 2.0,
            'high_latency_threshold': 100
        }
    
    @staticmethod
    def phone_side(cloud_server: str = "cloud.dreame.tech"):
        """
        手机端监控配置
        
        Args:
            cloud_server: 云服务器地址
        """
        return {
            'name': '手机端',
            'targets': [cloud_server],
            'interval': 1.0,
            'timeout': 2.0,
            'high_latency_threshold': 100
        }

