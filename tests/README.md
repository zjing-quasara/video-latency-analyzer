# 测试文件夹

## 说明
此文件夹用于存放测试数据和临时输出结果，**不上传到 Git 仓库**。

## 目录结构
```
tests/
├── README.md      # 本文件
├── data/          # 测试视频等数据
├── output/        # 测试分析结果（自动生成）
└── logs/          # 测试日志（自动生成）
```

## 如何编写测试脚本

### ⚠️ 核心原则：测试主程序，不重写代码！

```python
# ❌ 错误做法：重写业务逻辑
def test_wrong():
    ocr = PaddleOCR(...)  # 重新初始化
    cap = cv2.VideoCapture(...)  # 重新写视频处理
    # ... 自己实现一遍分析逻辑
    # 这样测试的是测试代码本身，不是主程序！

# ✅ 正确做法：直接调用主程序
def test_correct():
    from src.gui.worker import AnalysisWorker
    worker = AnalysisWorker(...)  # 使用主程序的类
    worker.run()  # 调用主程序的真实方法
    # 验证结果
```

## 规则
1. **所有测试文件必须放在此文件夹**
2. **主项目 `src/` 目录不应包含测试代码**
3. **此文件夹内容已添加到 .gitignore**

