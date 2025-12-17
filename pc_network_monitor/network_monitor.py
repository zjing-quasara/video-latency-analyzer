"""
电脑端网络监控工具
独立版本 - 用于测试时记录网络状况
"""
import time
import platform
import subprocess
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable, List
from dataclasses import dataclass


@dataclass
class NetworkStatus:
    """网络状态数据"""
    timestamp: float  # Unix时间戳
    ping_ms: Optional[float]  # ping延迟（毫秒）
    packet_loss: float  # 丢包率（0-1）
    status: str  # ok/timeout/error
    target: str  # 目标地址


class NetworkMonitor:
    """网络监控器"""
    
    def __init__(
        self, 
        name: str = "网络监控",
        targets: List[str] = None,
        interval: float = 1.0,
        timeout: float = 2.0,
        high_latency_threshold: int = 100,
        callback: Optional[Callable] = None,
        verbose: bool = True
    ):
        """
        初始化网络监控器
        
        Args:
            name: 监控器名称
            targets: 目标地址列表（IP或域名）
            interval: 采样间隔（秒）
            timeout: ping超时时间（秒）
            high_latency_threshold: 高延迟阈值（毫秒）
            callback: 状态回调函数
            verbose: 是否打印日志
        """
        self.name = name
        self.targets = targets or ["8.8.8.8"]
        self.interval = interval
        self.timeout = timeout
        self.high_latency_threshold = high_latency_threshold
        self.callback = callback
        self.verbose = verbose
        
        self.running = False
        self.thread = None
        self.data: List[NetworkStatus] = []
        self.start_time = None
        
        if self.verbose:
            print(f"[{self.name}] 初始化完成")
            print(f"  监控目标: {self.targets}")
            print(f"  采样间隔: {interval}秒")
    
    def start(self):
        """启动监控"""
        if self.running:
            if self.verbose:
                print(f"[{self.name}] 警告：监控已在运行")
            return
        
        self.running = True
        self.start_time = time.time()
        self.data.clear()
        
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        
        if self.verbose:
            print(f"[{self.name}] ✓ 监控已启动")
    
    def stop(self):
        """停止监控"""
        if not self.running:
            return
        
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        
        duration = time.time() - self.start_time if self.start_time else 0
        if self.verbose:
            print(f"[{self.name}] ✓ 监控已停止")
            print(f"  运行时长: {duration:.1f}秒")
            print(f"  记录数量: {len(self.data)}条")
    
    def _monitor_loop(self):
        """监控循环（后台线程）"""
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
                        if self.verbose:
                            print(f"[{self.name}] 回调异常: {e}")
                
                # 高延迟或失败警告
                if self.verbose:
                    if status.status == 'ok':
                        if status.ping_ms > self.high_latency_threshold:
                            print(f"  ⚠️ 高延迟: {target} = {status.ping_ms:.0f}ms")
                    else:
                        print(f"  ✗ Ping失败: {target} ({status.status})")
            
            # 等待到下一个采样时间
            elapsed = time.time() - loop_start
            sleep_time = max(0, self.interval - elapsed)
            time.sleep(sleep_time)
    
    def _ping_once(self, target: str) -> NetworkStatus:
        """执行一次ping"""
        timestamp = time.time()
        
        try:
            # 根据操作系统选择ping命令
            system = platform.system().lower()
            
            if system == 'windows':
                cmd = ['ping', '-n', '1', '-w', str(int(self.timeout * 1000)), target]
            else:
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
                    return NetworkStatus(
                        timestamp=timestamp,
                        ping_ms=None,
                        packet_loss=1.0,
                        status='parse_error',
                        target=target
                    )
            else:
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
            if self.verbose:
                print(f"[{self.name}] Ping异常: {target}, {e}")
            return NetworkStatus(
                timestamp=timestamp,
                ping_ms=None,
                packet_loss=1.0,
                status='error',
                target=target
            )
    
    def _parse_ping_time(self, output: str) -> Optional[float]:
        """从ping输出中提取延迟时间"""
        import re
        
        patterns = [
            r'[时间time]*[=:]\s*(\d+(?:\.\d+)?)\s*ms',
            r'平均\s*=\s*(\d+)ms',
            r'Average\s*=\s*(\d+)ms',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                return float(match.group(1))
        
        return None
    
    def get_statistics(self) -> dict:
        """获取统计数据"""
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
        """保存监控日志到CSV文件"""
        import csv
        
        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # 写入表头
            writer.writerow([
                'timestamp',
                'datetime',
                'target',
                'ping_ms',
                'packet_loss',
                'status'
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
        if self.verbose:
            print(f"\n[{self.name}] ✓ 日志已保存: {filepath}")
            print(f"  总数: {stats['total_count']}")
            print(f"  成功: {stats['success_count']}")
            print(f"  超时: {stats['timeout_count']}")
            print(f"  丢包率: {stats['packet_loss_rate']:.1%}")
            print(f"  平均延迟: {stats['avg_ping_ms']:.1f}ms")
            print(f"  延迟范围: {stats['min_ping_ms']:.1f} - {stats['max_ping_ms']:.1f}ms")



