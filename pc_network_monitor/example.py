"""
快速示例 - 监控10秒
"""
import time
from network_monitor import NetworkMonitor

# 创建监控器
monitor = NetworkMonitor(
    name="测试",
    targets=["www.baidu.com"],  # 改成你要测试的服务器
    interval=1.0,
    verbose=True
)

# 启动
monitor.start()
print("\n监控10秒...\n")

# 运行10秒
time.sleep(10)

# 停止
monitor.stop()

# 保存日志
monitor.save_log("network_log_test.csv")

# 显示统计
stats = monitor.get_statistics()
print(f"\n平均延迟: {stats['avg_ping_ms']:.1f}ms")
print(f"丢包率: {stats['packet_loss_rate']:.1%}")



