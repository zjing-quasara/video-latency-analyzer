# 视频延时分析工具

智能分析录屏视频中的时间戳延迟。

## 🚀 快速开始

```bash
# 安装依赖（虚拟环境）
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt

# 启动程序
python main.py
```

## ⚙️ 环境配置

本项目已配置正确的依赖版本：
- **PaddlePaddle**: 2.6.2 (CPU版本)
- **PaddleOCR**: 2.7.3
- **NumPy**: < 2.0 (兼容性要求)
- **OpenCV**: 4.6.0.66

> 注意：使用虚拟环境可以避免包版本冲突

## 📋 使用流程

1. **选择视频** → 点击"选择视频"
2. **标定T_app** → 用滑块调整到应用内时间戳位置
3. **开始分析** → 自动生成报告

## 📊 输出结果

报告文件夹包含：
- `xxx.csv` - 原始数据
- `xxx.html` - 可视化报告
- `xxx.mp4` - 标注视频
- `analysis.log` - 分析日志

## 🔧 核心功能

- **时间识别**：OCR识别T_app和T_real
- **延时计算**：自动计算时间差
- **网络日志匹配**：支持手机/电脑网络数据对齐
- **异常值检测**：自动识别数据异常
- **可视化报告**：HTML图表展示

## 📦 项目结构

```
src/
├── core/              # 核心模块
│   ├── time_detector.py      # 时间识别
│   ├── report_generator.py   # 报告生成
│   ├── network_matcher.py    # 网络匹配
│   └── outlier_detector.py   # 异常检测
├── gui/               # GUI界面
│   ├── main_window.py
│   └── worker.py
└── utils/             # 工具
    └── logger.py
```

## 🧪 使用说明

### 基础分析

1. **首次使用**：运行程序后，先选择视频并标定T_app区域（应用内时间戳位置）
2. **ROI配置**：标定后的ROI会自动保存到 `data/config/roi_config.json`
3. **参数调整**：可以调整帧步长、帧限制等参数优化分析速度

### 网络分析（可选）

如果需要分析网络延迟与视频延时的关系：

1. **启用网络分析**：勾选"网络监控日志分析"选项
2. **选择日志文件**：
   - **手机日志**：记录手机网络ping的CSV文件
   - **电脑日志**：记录电脑网络ping的CSV文件
3. **时间戳匹配**：
   - 手机和电脑的网络日志都是在测试时记录的
   - 程序会自动根据视频中识别的 **T_app（手机应用时间）** 计算时间偏移量
   - 将视频的相对时间戳转换为绝对时间戳，然后匹配网络日志
   - **支持FFmpeg裁剪后的视频**：自动计算时间偏移量，无需担心起始时间不一致

4. **日志格式要求**：
   ```csv
   timestamp,datetime,target,ping_ms,status
   1734595770.246,2024-12-18 19:29:30,api.link.aliyun.com,50,ok
   ```
   - `timestamp`: Unix时间戳（秒）
   - `ping_ms`: ping延迟（毫秒）
   - `status`: 状态（ok/timeout/error）

## 🔄 后端迁移

核心模块可独立运行，迁移到FastAPI：

```python
from src.core.time_detector import detect_time_app, detect_time_real
from src.core.report_generator import ReportGenerator

@app.post("/analyze")
async def analyze_video(video: UploadFile):
    # 调用核心模块处理
    ...
```

## 📝 依赖

- opencv-python - 视频处理
- paddleocr - OCR识别
- PyQt5 - GUI界面
- pandas - 数据处理
