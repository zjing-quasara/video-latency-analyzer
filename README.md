# 视频延时分析工具

自动化分析录屏视频中应用内时间与真实世界时间的延迟差异，支持批量处理、智能异常检测和可视化报告生成。

## 功能特性

**核心功能**
- 基于PaddleOCR的高精度时间识别，支持ROI自动追踪
- 自动计算并分析每帧的延时差异（应用内时间 T_app 与真实世界时间 T_real）
- 智能异常检测：基于跳变一致性和回退检测的并联检测器架构
- 网络日志匹配：关联网络延迟数据（手机Ping、电脑Ping）


## 快速开始

```bash
# 安装依赖（推荐使用虚拟环境）
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt

# 启动程序
python main.py
```

## 环境要求

**Python依赖**
- Python 3.10+
- PaddlePaddle 2.6.2 (CPU)
- PaddleOCR 2.7.3
- PyQt5 5.15.11
- OpenCV 4.6.0.66
- NumPy < 2.0

**可选依赖**
- FFmpeg（视频转码，提升浏览器兼容性）

## 打包发布

**准备工作**（这些文件不在git仓库中）：
- `models/` - OCR模型文件（PaddleOCR会自动下载，或手动放置）
- `ffmpeg/` - 下载ffmpeg.exe放到此文件夹（用于视频转码）

**打包指令**：
taskkill /IM "VideoDelayAnalyzer_v1.0.exe" /F 2>$null; Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue; pyinstaller --onefile --windowed --name=VideoDelayAnalyzer_v1.0 --add-data="models;models" --add-data="ffmpeg;ffmpeg" --collect-all=paddle --collect-all=paddleocr --collect-all=shapely --collect-all=pyclipper --collect-all=lmdb --collect-all=rapidfuzz --collect-all=imgaug --collect-all=imageio --collect-all=skimage --hidden-import=imghdr --hidden-import=cv2 --hidden-import=numpy --hidden-import=PIL --exclude-module=Cython main.py


## 项目结构

```
src/
├── core/              # 核心算法模块
│   ├── time_detector.py       # OCR时间识别
│   ├── anomaly_detector.py    # 异常检测
│   ├── roi_tracker.py         # ROI区域追踪
│   ├── report_generator.py    # HTML报告生成
│   └── network_matcher.py     # 网络日志匹配
├── gui/               # 图形界面
│   ├── main_window.py         # 主窗口
│   └── worker.py              # 后台分析线程
├── utils/             # 工具模块
│   └── logger.py              # 日志系统
└── config.py          # 配置参数
```


