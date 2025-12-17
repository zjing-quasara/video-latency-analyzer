"""
快速测试网络监控 - 基于您提供的代码示例
"""
import time
from core.network_monitor import NetworkMonitor, NetworkMonitorPresets


# 使用预设配置
config = NetworkMonitorPresets.robot_side(
    robot_ip="192.168.1.100",  # 您的扫地机IP
    cloud_server="www.baidu.com"  # 改用百度测试（可以改回 api.link.aliyun.com）
)

print(f"监控配置: {config}")
print(f"监控目标: {config['targets']}")
print()

# 创建监控器
monitor = NetworkMonitor(**config)

# 启动监控
monitor.start()
print("网络监控已启动...")

# 监控中...（这里模拟15秒的监控时间）
try:
    for i in range(15):
        time.sleep(1)
        print(f"  监控中... {i+1}秒")
except KeyboardInterrupt:
    print("\n用户中断")

# 停止监控
monitor.stop()
print("\n网络监控已停止")

# 显示统计
stats = monitor.get_statistics()
print("\n" + "="*50)
print("监控统计:")
print("="*50)
print(f"总请求数:   {stats['total_count']}")
print(f"成功数:     {stats['success_count']}")
print(f"超时数:     {stats['timeout_count']}")
print(f"丢包率:     {stats['packet_loss_rate']:.1%}")
print(f"平均延迟:   {stats['avg_ping_ms']:.1f}ms")
print(f"最小延迟:   {stats['min_ping_ms']:.1f}ms")
print(f"最大延迟:   {stats['max_ping_ms']:.1f}ms")
print(f"高延迟次数: {stats['high_latency_count']}")
print("="*50)

# 保存日志
log_file = "data/output/network_log.csv"
monitor.save_log(log_file)
print(f"\n日志已保存: {log_file}")


