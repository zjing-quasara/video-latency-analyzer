# 电脑端网络监控工具

独立的网络监控工具，用于测试时记录电脑的网络状况。

## 功能

- ✅ 持续ping目标服务器
- ✅ 记录延迟和丢包率
- ✅ 时间戳精确到毫秒
- ✅ 导出CSV格式日志
- ✅ 实时显示网络状态

## 快速开始

### 方式1：交互式启动（推荐）

```bash
python start_monitor.py
```

按提示输入：
- 目标服务器（默认：www.baidu.com）
- 监控时长（默认：60秒）
- 采样间隔（默认：1秒）

### 方式2：快速测试

```bash
python example.py
```

监控10秒，生成测试日志。

### 方式3：代码调用

```python
from network_monitor import NetworkMonitor
import time

# 创建监控器
monitor = NetworkMonitor(
    name="电脑端",
    targets=["api.link.aliyun.com"],  # 你的服务器
    interval=1.0,
    verbose=True
)

# 启动监控
monitor.start()

# 进行测试...（录制视频等）
time.sleep(60)

# 停止并保存
monitor.stop()
monitor.save_log("network_log_pc.csv")
```

## 使用场景

### 配合手机端监控使用

**测试流程：**

1. **准备阶段：**
   ```bash
   # 电脑上
   python start_monitor.py
   # 输入目标服务器，按回车开始
   
   # 手机上
   # 打开安卓监控APP，输入同样的服务器地址
   ```

2. **测试阶段：**
   - 手机开始录屏
   - 进行操作测试
   - 同时电脑和手机都在后台监控网络

3. **分析阶段：**
   - 得到3个文件：
     - 视频分析结果 `video_analysis.csv`
     - 手机网络日志 `network_log_phone.csv`
     - 电脑网络日志 `network_log_pc.csv`
   - 导入视频延时分析工具进行关联分析

### 对比诊断

| 手机网络 | 电脑网络 | 诊断 |
|---------|---------|------|
| 延迟高/丢包 | 正常 | 手机WiFi问题 |
| 正常 | 延迟高/丢包 | 电脑网络问题 |
| 都延迟高 | 都延迟高 | 网络环境问题（路由器/宽带/云服务器） |
| 都正常 | 都正常 | 网络正常，延迟是应用层问题 |

## 输出格式

CSV文件包含以下列：

```csv
timestamp,datetime,target,ping_ms,packet_loss,status
1702652400.123,2023-12-15 16:00:00.123,api.link.aliyun.com,45.20,0.00,ok
1702652401.234,2023-12-15 16:00:01.234,api.link.aliyun.com,48.50,0.00,ok
1702652402.345,2023-12-15 16:00:02.345,api.link.aliyun.com,,1.00,timeout
```

**字段说明：**
- `timestamp`: Unix时间戳（秒）
- `datetime`: 可读时间格式
- `target`: 目标服务器地址
- `ping_ms`: ping延迟（毫秒）
- `packet_loss`: 丢包率（0-1）
- `status`: 状态（ok/timeout/error）

## 依赖

纯Python标准库，无需额外安装依赖。

## 注意事项

1. **防火墙：** 确保允许ping（ICMP）
2. **时间同步：** 电脑和手机时间要准确
3. **同一服务器：** 手机和电脑要ping同一个服务器才能对比
4. **同时运行：** 电脑监控和手机监控要同时开始和结束

## 常见问题

### Q: 显示 "ping不通" 怎么办？

**检查：**
1. 服务器地址是否正确
2. 网络是否连接
3. 防火墙是否阻止ping
4. 尝试换个服务器（如 www.baidu.com）

### Q: 延迟一直很高？

**可能原因：**
- 服务器在国外（正常现象）
- 网络拥堵
- 路由器性能差
- 其他程序占用带宽

### Q: CSV文件在哪里？

**默认位置：** 当前目录（`pc_network_monitor/`文件夹）

可以在代码中修改路径：
```python
monitor.save_log("D:/测试日志/network_log.csv")
```

## 技术细节

- **采样精度：** 毫秒级时间戳
- **后台运行：** 使用线程，不阻塞主程序
- **跨平台：** 自动适配Windows/Linux/Mac的ping命令
- **无窗口：** ping命令静默运行，不弹黑窗口

---

**版本:** v1.0  
**更新:** 2025-12-17



