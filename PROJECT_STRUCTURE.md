# 项目结构说明

## 目录结构

```
视频延时分析工具/
├── main.py                      # 主程序入口
├── config.py                    # 全局配置
├── requirements.txt             # Python依赖
├── build_exe.spec              # PyInstaller打包配置
│
├── core/                        # 核心功能模块
│   ├── adaptive_ocr.py         # 自适应OCR识别引擎（多策略）
│   ├── smart_calibrator.py     # 智能校准器（自动调参）
│   ├── smart_roi_detector.py   # 智能ROI检测器
│   ├── network_monitor.py      # 网络监控核心（双端）
│   ├── network_matcher.py      # 网络数据匹配器
│   └── report_generator.py     # HTML报告生成器
│
├── gui/                         # GUI界面模块
│   ├── main_window.py          # 主窗口（PyQt5）
│   └── worker.py               # 后台工作线程
│
├── utils/                       # 工具函数
│   └── logger.py               # 日志管理
│
├── data/                        # 数据目录
│   ├── config/                 # 配置文件
│   │   └── roi_config.json    # ROI区域配置
│   ├── output/                 # 分析输出（被.gitignore忽略）
│   └── debug/                  # 调试数据（被.gitignore忽略）
│
├── docs/                        # 文档
│   └── 使用说明.md
│
├── logs/                        # 运行日志（被.gitignore忽略）
│
├── pc_network_monitor/          # PC端独立网络监控工具
│   ├── network_monitor.py      # 独立监控器
│   ├── start_monitor.py        # 启动脚本
│   ├── example.py              # 使用示例
│   └── README.md               # 说明文档
│
└── README.md                    # 项目说明
```

## 核心模块说明

### 1. 自适应OCR系统
- **adaptive_ocr.py**: 多策略OCR引擎，自动尝试最佳识别方案
- **smart_calibrator.py**: 智能校准，自动选择最优参数
- **smart_roi_detector.py**: 智能ROI检测，自适应定位时间区域

### 2. 网络监控系统
- **network_monitor.py**: 核心监控模块，支持双端（手机+PC）同步监控
- **network_matcher.py**: 将视频分析数据与网络日志精确匹配

### 3. 报告系统
- **report_generator.py**: 生成包含延时分析、网络监控的综合HTML报告
- 支持双Y轴图表（延时+网络Ping）
- 网络异常状态可视化标记

### 4. GUI系统
- **main_window.py**: PyQt5主界面，用户交互
- **worker.py**: 后台分析线程，避免界面卡顿

## 数据流

```
视频 + 网络日志
    ↓
[ROI检测] → [OCR识别] → [时间解析]
    ↓
[延时计算] + [网络数据匹配]
    ↓
[HTML报告生成] + [标定视频输出]
```

## 代码规范

- **命名规范**: 使用有意义的英文命名，遵循PEP8
- **注释**: 关键逻辑有详细中文注释
- **日志**: 使用统一的logger模块，分级记录
- **错误处理**: 完善的异常捕获和用户友好的错误提示

## Git管理

- 构建产物（build/、dist/）不上传
- 用户数据（视频、日志、报告）不上传
- 模型文件（PaddleOCR）不上传
- 保持目录结构（使用.gitkeep）

## 开发指南

### 添加新功能
1. 在对应的core模块中实现功能
2. 在worker.py中集成
3. 在main_window.py中添加UI（如需要）
4. 更新文档

### 调试
- 日志文件: `logs/app_YYYYMMDD_HHMMSS.log`
- 调试图像: `data/debug/`
- 测试输出: `data/output/`

### 打包发布
```bash
pyinstaller build_exe.spec
```

## 依赖管理

详见 `requirements.txt`

主要依赖:
- PyQt5: GUI框架
- OpenCV: 图像处理
- PaddleOCR: OCR识别
- Pandas: 数据处理
- Numpy: 数值计算

