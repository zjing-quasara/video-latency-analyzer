"""
网络监控使用示例
演示如何使用 NetworkMonitor 和 NetworkMonitorPresets
"""
import time
from core.network_monitor import NetworkMonitor, NetworkMonitorPresets


def example_with_presets():
    """使用预设配置的示例"""
    print("=" * 60)
    print("示例1: 使用预设配置 - 扫地机端监控")
    print("=" * 60)
    
    # 使用预设配置
    config = NetworkMonitorPresets.robot_side(
        robot_ip="192.168.1.100",  # 扫地机IP
        cloud_server="www.baidu.com"  # 改用百度作为测试服务器
    )
    
    print(f"配置: {config}")
    
    monitor = NetworkMonitor(**config)
    monitor.start()
    
    print("监控已启动，将运行10秒...")
    time.sleep(10)
    
    monitor.stop()
    
    # 显示统计信息
    stats = monitor.get_statistics()
    print("\n统计信息:")
    print(f"  总请求数: {stats['total_count']}")
    print(f"  成功数: {stats['success_count']}")
    print(f"  超时数: {stats['timeout_count']}")
    print(f"  丢包率: {stats['packet_loss_rate']:.1%}")
    print(f"  平均延迟: {stats['avg_ping_ms']:.1f}ms")
    print(f"  最小延迟: {stats['min_ping_ms']:.1f}ms")
    print(f"  最大延迟: {stats['max_ping_ms']:.1f}ms")
    print(f"  高延迟次数: {stats['high_latency_count']}")
    
    # 保存日志
    monitor.save_log("data/output/network_log_robot.csv")
    print("\n日志已保存到: data/output/network_log_robot.csv\n")


def example_phone_side():
    """手机端监控示例"""
    print("=" * 60)
    print("示例2: 使用预设配置 - 手机端监控")
    print("=" * 60)
    
    config = NetworkMonitorPresets.phone_side(
        cloud_server="www.baidu.com"  # 使用百度作为测试
    )
    
    print(f"配置: {config}")
    
    monitor = NetworkMonitor(**config)
    monitor.start()
    
    print("监控已启动，将运行10秒...")
    time.sleep(10)
    
    monitor.stop()
    
    # 统计
    stats = monitor.get_statistics()
    print("\n统计信息:")
    print(f"  总请求数: {stats['total_count']}")
    print(f"  成功数: {stats['success_count']}")
    print(f"  超时数: {stats['timeout_count']}")
    print(f"  丢包率: {stats['packet_loss_rate']:.1%}")
    print(f"  平均延迟: {stats['avg_ping_ms']:.1f}ms")
    
    monitor.save_log("data/output/network_log_phone.csv")
    print("\n日志已保存到: data/output/network_log_phone.csv\n")


def example_custom_config():
    """自定义配置示例"""
    print("=" * 60)
    print("示例3: 自定义配置")
    print("=" * 60)
    
    # 回调函数：实时显示网络状态
    def status_callback(status):
        if status.status == 'ok':
            print(f"  ✓ {status.target}: {status.ping_ms:.1f}ms")
        else:
            print(f"  ✗ {status.target}: {status.status}")
    
    monitor = NetworkMonitor(
        name="自定义监控",
        targets=["www.baidu.com", "8.8.8.8"],  # 百度 + Google DNS
        interval=2.0,  # 每2秒采样一次
        timeout=3.0,
        high_latency_threshold=150,  # 150ms算高延迟
        callback=status_callback  # 实时回调
    )
    
    monitor.start()
    
    print("监控已启动（带实时回调），将运行10秒...\n")
    time.sleep(10)
    
    monitor.stop()
    
    stats = monitor.get_statistics()
    print(f"\n统计: 成功={stats['success_count']}/{stats['total_count']}, "
          f"丢包率={stats['packet_loss_rate']:.1%}, "
          f"平均={stats['avg_ping_ms']:.1f}ms\n")


def example_load_and_analyze():
    """加载并分析已保存的日志"""
    print("=" * 60)
    print("示例4: 加载并分析日志")
    print("=" * 60)
    
    try:
        # 先确保有数据
        config = NetworkMonitorPresets.robot_side(
            robot_ip=None,
            cloud_server="www.baidu.com"
        )
        monitor = NetworkMonitor(**config)
        monitor.start()
        print("生成测试数据（5秒）...")
        time.sleep(5)
        monitor.stop()
        
        log_file = "data/output/network_log_test.csv"
        monitor.save_log(log_file)
        
        # 加载日志
        print(f"\n加载日志: {log_file}")
        data = NetworkMonitor.load_log(log_file)
        
        print(f"共加载 {len(data)} 条记录")
        
        # 分析
        success_data = [d for d in data if d.status == 'ok' and d.ping_ms]
        if success_data:
            avg_ping = sum(d.ping_ms for d in success_data) / len(success_data)
            print(f"成功率: {len(success_data)/len(data):.1%}")
            print(f"平均延迟: {avg_ping:.1f}ms")
            
            # 显示前5条记录
            print("\n前5条记录:")
            for i, d in enumerate(data[:5]):
                from datetime import datetime
                dt = datetime.fromtimestamp(d.timestamp).strftime('%H:%M:%S')
                if d.ping_ms:
                    print(f"  {dt} - {d.target}: {d.ping_ms:.1f}ms")
                else:
                    print(f"  {dt} - {d.target}: {d.status}")
        
        print()
    
    except FileNotFoundError:
        print("未找到日志文件，请先运行示例1或2生成日志\n")


if __name__ == '__main__':
    print("\n网络监控模块使用示例\n")
    
    # 运行所有示例
    try:
        example_with_presets()
        example_phone_side()
        example_custom_config()
        example_load_and_analyze()
        
        print("=" * 60)
        print("所有示例运行完成！")
        print("=" * 60)
        
    except KeyboardInterrupt:
        print("\n\n用户中断")
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()


