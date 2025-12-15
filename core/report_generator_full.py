"""
视频延时分析工具 - 完整版
功能：
1. T_app 手动标定并保存
2. T_real 动态检测
3. 每帧保存标定图
4. 生成标定视频
5. 生成延时曲线
6. 输出 HTML 报告
"""
import sys
import cv2
import numpy as np
import re
import csv
import json
import subprocess
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QProgressBar, QFileDialog, 
    QMessageBox, QDialog, QSlider, QCheckBox, QComboBox, QGroupBox
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from PyQt5.QtGui import QPixmap, QImage

try:
    from paddleocr import PaddleOCR
except ImportError:
    PaddleOCR = None

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
except ImportError:
    matplotlib = None
    plt = None


class ROIAdjustDialog(QDialog):
    """T_app ROI 手动调整对话框"""
    def __init__(self, frame, initial_roi, parent=None):
        super().__init__(parent)
        self.setWindowTitle("调整 T_app 区域")
        self.setModal(True)
        self.frame = frame
        self.h, self.w = frame.shape[:2]
        
        # 初始 ROI
        x1, y1, x2, y2 = initial_roi
        self.x1_ratio = x1 / self.w
        self.x2_ratio = x2 / self.w
        self.y1_ratio = y1 / self.h
        self.y2_ratio = y2 / self.h
        
        self.confirmed = False
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 显示图片
        self.img_label = QLabel()
        self.update_preview()
        layout.addWidget(self.img_label)
        
        # 调整滑块
        controls = QVBoxLayout()
        
        self.slider_x1 = self.create_slider("左边界", 0, 50, int(self.x1_ratio * 100))
        self.slider_x2 = self.create_slider("右边界", 50, 100, int(self.x2_ratio * 100))
        self.slider_y1 = self.create_slider("上边界", 50, 95, int(self.y1_ratio * 100))
        self.slider_y2 = self.create_slider("下边界", 75, 100, int(self.y2_ratio * 100))
        
        controls.addLayout(self.slider_x1[1])
        controls.addLayout(self.slider_x2[1])
        controls.addLayout(self.slider_y1[1])
        controls.addLayout(self.slider_y2[1])
        layout.addLayout(controls)
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_confirm = QPushButton("确认使用")
        btn_confirm.clicked.connect(self.on_confirm)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_confirm)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)
    
    def create_slider(self, name, min_val, max_val, initial):
        """创建滑块控件"""
        layout = QHBoxLayout()
        label = QLabel(f"{name}: {initial}%")
        slider = QSlider(Qt.Horizontal)
        slider.setMinimum(min_val)
        slider.setMaximum(max_val)
        slider.setValue(initial)
        slider.valueChanged.connect(lambda v: self.on_slider_changed(name, v, label))
        layout.addWidget(QLabel(name))
        layout.addWidget(slider)
        layout.addWidget(label)
        return (slider, layout, label)
    
    def on_slider_changed(self, name, value, label):
        """滑块变化回调"""
        label.setText(f"{name}: {value}%")
        
        # 更新比例
        if name == "左边界":
            self.x1_ratio = value / 100.0
        elif name == "右边界":
            self.x2_ratio = value / 100.0
        elif name == "上边界":
            self.y1_ratio = value / 100.0
        elif name == "下边界":
            self.y2_ratio = value / 100.0
        
        self.update_preview()
    
    def update_preview(self):
        """更新预览图"""
        x1 = int(self.x1_ratio * self.w)
        x2 = int(self.x2_ratio * self.w)
        y1 = int(self.y1_ratio * self.h)
        y2 = int(self.y2_ratio * self.h)
        
        preview = self.frame.copy()
        cv2.rectangle(preview, (x1, y1), (x2, y2), (255, 0, 0), 3)
        cv2.putText(preview, "T_app", (x1, y1 - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
        
        # 转换为 QPixmap
        rgb = cv2.cvtColor(preview, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        q_img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(q_img)
        
        # 缩放
        max_width = 1000
        if pixmap.width() > max_width:
            pixmap = pixmap.scaledToWidth(max_width, Qt.SmoothTransformation)
        
        self.img_label.setPixmap(pixmap)
    
    def on_confirm(self):
        """确认"""
        self.confirmed = True
        self.accept()
    
    def get_roi(self):
        """获取调整后的 ROI"""
        x1 = int(self.x1_ratio * self.w)
        x2 = int(self.x2_ratio * self.w)
        y1 = int(self.y1_ratio * self.h)
        y2 = int(self.y2_ratio * self.h)
        return (x1, y1, x2, y2)


class AnalysisWorker(QThread):
    """后台分析线程"""
    progress = pyqtSignal(int, int)
    log_message = pyqtSignal(str)
    finished = pyqtSignal(bool, str)
    
    def __init__(self, video_path, app_roi, use_gpu=False, resize_ratio=0.5):
        super().__init__()
        self.video_path = video_path
        self.app_roi = app_roi
        self.use_gpu = use_gpu
        self.resize_ratio = resize_ratio
        self.ocr_engine = None
        self.frame_limit = 30
    
    def run(self):
        try:
            self.log_message.emit("正在初始化 PaddleOCR...")
            if PaddleOCR is None:
                self.finished.emit(False, "未安装 PaddleOCR")
                return
            
            # 初始化 OCR（新版本自动检测 GPU）
            import os
            if self.use_gpu:
                # 启用 GPU（通过环境变量，新版本自动检测）
                os.environ['CUDA_VISIBLE_DEVICES'] = '0'
                self.log_message.emit("OCR 运行模式: GPU (自动检测)")
            else:
                # 禁用 GPU，强制使用 CPU
                os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
                self.log_message.emit("OCR 运行模式: CPU")
            
            try:
                # PaddleOCR 2.6+ 版本，只指定语言，其他参数使用默认值
                self.ocr_engine = PaddleOCR(lang="en")
                self.log_message.emit(f"OCR 分辨率缩放: {int(self.resize_ratio*100)}%")
            except Exception as e:
                self.log_message.emit(f"OCR 初始化失败: {str(e)}")
                raise
            self.log_message.emit("PaddleOCR 初始化完成")
            
            success, message = self.analyze_video()
            self.finished.emit(success, message)
        except Exception as e:
            import traceback
            self.finished.emit(False, f"错误: {str(e)}\n{traceback.format_exc()}")
    
    def detect_real_time_roi(self, frame):
        """动态检测 T_real（黑底白字的手机屏幕）"""
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        _, th = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY_INV)  # 降低阈值到30
        contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        candidate = None
        max_area = 0
        for cnt in contours:
            x, y, w_box, h_box = cv2.boundingRect(cnt)
            area = w_box * h_box
            if area < 0.05 * w * h or area > 0.5 * w * h:
                continue
            ratio = w_box / (h_box + 1e-6)
            if ratio < 2.0 or ratio > 6.0:
                continue
            if area > max_area:
                max_area = area
                candidate = (x, y, x + w_box, y + h_box)
        
        return candidate
    
    def extract_time_from_roi(self, frame, roi):
        """从 ROI 提取时间"""
        if not roi:
            return None
        
        x1, y1, x2, y2 = roi
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        
        roi_img = frame[y1:y2, x1:x2]
        if roi_img.size == 0:
            return None
        
        # 根据设置缩小分辨率加速 OCR
        if self.resize_ratio < 1.0:
            roi_img = cv2.resize(roi_img, (0, 0), fx=self.resize_ratio, fy=self.resize_ratio, interpolation=cv2.INTER_AREA)
        roi_rgb = cv2.cvtColor(roi_img, cv2.COLOR_BGR2RGB)
        
        try:
            ocr_result = self.ocr_engine.ocr(roi_rgb)
            
            if not ocr_result or len(ocr_result) == 0:
                return None
            
            # PaddleOCR 2.7.3 返回格式: [[[box], (text, score)], ...]
            result_list = ocr_result[0] if ocr_result else []
            
            if not result_list:
                return None
            
            # 提取所有文本
            texts = []
            for item in result_list:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    text_info = item[1]
                    if isinstance(text_info, (list, tuple)) and len(text_info) >= 1:
                        texts.append(str(text_info[0]))
            
            # 在所有文本中查找时间格式
            time_pattern = re.compile(r"\d{2}:\d{2}:\d{2}[.:]\d{1,3}")
            for txt in texts:
                filtered = "".join(ch for ch in txt if ch in "0123456789:.")
                m = time_pattern.search(filtered)
                if m:
                    return m.group(0)
        except Exception:
            pass
        
        return None
    
    def parse_time_to_ms(self, time_str):
        """时间字符串转毫秒"""
        try:
            if "." in time_str:
                hms, ms_part = time_str.split(".")
            else:
                hms, ms_part = time_str, "0"
            h, m, s = map(int, hms.split(":"))
            ms = int(ms_part.ljust(3, "0")[:3])
            return ((h * 3600 + m * 60 + s) * 1000) + ms
        except Exception:
            return None
    
    def analyze_video(self):
        """分析视频"""
        video_path = Path(self.video_path)
        frame_step = 5
        
        debug_dir = Path("temp_phone_ts_debug")
        debug_dir.mkdir(exist_ok=True)
        
        # 清空旧的调试图
        for old_file in debug_dir.glob("frame_*.png"):
            old_file.unlink()
        
        report_path = Path("temp_phone_ts_report.csv")
        
        self.log_message.emit(f"开始处理视频: {video_path.name}")
        
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return False, "无法打开视频"
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.log_message.emit(f"FPS={fps:.2f}, 总帧数={total}, 处理前{self.frame_limit}帧")
        
        # 数据收集
        results = []
        annotated_frames = []
        
        with report_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "video_name", "frame_idx", "video_time_s",
                "app_time_str", "app_time_ms",
                "real_time_str", "real_time_ms",
                "delay_ms", "status"
            ])
            
            frame_idx = 0
            processed_count = 0
            
            while True:
                if frame_idx > self.frame_limit:
                    break
                
                ret, frame = cap.read()
                if not ret:
                    break
                
                if frame_idx % frame_step != 0:
                    frame_idx += 1
                    continue
                
                self.progress.emit(frame_idx, self.frame_limit)
                
                # 检测和识别
                real_roi = self.detect_real_time_roi(frame)
                app_time_str = self.extract_time_from_roi(frame, self.app_roi)
                real_time_str = self.extract_time_from_roi(frame, real_roi)
                
                # 计算延时
                video_time_s = frame_idx / fps if fps > 0 else None
                app_time_ms = self.parse_time_to_ms(app_time_str) if app_time_str else None
                real_time_ms = self.parse_time_to_ms(real_time_str) if real_time_str else None
                
                delay_ms = None
                status = "ok"
                if app_time_ms is None:
                    status = "app_fail"
                if real_time_ms is None:
                    status = "real_fail" if status == "ok" else "both_fail"
                if app_time_ms is not None and real_time_ms is not None:
                    delay_ms = app_time_ms - real_time_ms
                
                # 保存到 CSV
                writer.writerow([
                    video_path.name, frame_idx,
                    f"{video_time_s:.6f}" if video_time_s is not None else "",
                    app_time_str or "", app_time_ms or "",
                    real_time_str or "", real_time_ms or "",
                    delay_ms if delay_ms is not None else "", status
                ])
                
                # 收集数据用于曲线
                results.append({
                    'frame_idx': frame_idx,
                    'video_time_s': video_time_s,
                    'app_time_str': app_time_str,
                    'real_time_str': real_time_str,
                    'delay_ms': delay_ms,
                    'status': status
                })
                
                # 绘制标定图
                annotated = frame.copy()
                # 画 T_app (蓝框)
                if self.app_roi:
                    x1, y1, x2, y2 = self.app_roi
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (255, 0, 0), 2)
                    label = f"T_app: {app_time_str}" if app_time_str else "T_app: N/A"
                    cv2.putText(annotated, label, (x1, y1 - 10),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
                
                # 画 T_real (绿框)
                if real_roi:
                    x1, y1, x2, y2 = real_roi
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    label = f"T_real: {real_time_str}" if real_time_str else "T_real: N/A"
                    cv2.putText(annotated, label, (x1, y1 - 10),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                
                # 显示延时
                if delay_ms is not None:
                    delay_text = f"Delay: {delay_ms}ms"
                    cv2.putText(annotated, delay_text, (10, 30),
                               cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
                
                # 保存标定图
                debug_path = debug_dir / f"frame_{frame_idx:06d}.png"
                cv2.imwrite(str(debug_path), annotated)
                annotated_frames.append(annotated)
                
                # 日志
                if status == "ok":
                    self.log_message.emit(
                        f"帧 {frame_idx}: T_app={app_time_str}, T_real={real_time_str}, 延时={delay_ms}ms"
                    )
                else:
                    self.log_message.emit(f"帧 {frame_idx}: {status}")
                
                frame_idx += 1
                processed_count += 1
            
            cap.release()
        
        self.log_message.emit(f"处理完成，共 {processed_count} 帧")
        
        # 生成标定视频
        self.log_message.emit("正在生成标定视频...")
        video_out_path = Path("temp_annotated_video.mp4")
        if annotated_frames:
            h, w = annotated_frames[0].shape[:2]
            fourcc = cv2.VideoWriter_fourcc(*'avc1')  # 改用 H.264 编码，浏览器支持更好
            out = cv2.VideoWriter(str(video_out_path), fourcc, fps / frame_step, (w, h))
            for ann_frame in annotated_frames:
                out.write(ann_frame)
            out.release()
            self.log_message.emit(f"标定视频已保存: {video_out_path.resolve()}")
        else:
            video_out_path = None
        
        # 生成延时曲线数据
        self.log_message.emit("正在准备延时曲线数据...")
        curve_data = self.generate_delay_curve(results)
        
        # 生成 HTML 报告
        self.log_message.emit("正在生成 HTML 报告...")
        html_path = self.generate_html_report(results, video_out_path, curve_data, fps, frame_step)
        
        return True, f"HTML 报告: {html_path.resolve()}"
    
    def generate_delay_curve(self, results):
        """生成延时曲线数据（用于 Chart.js）"""
        valid_data = [r for r in results if r['delay_ms'] is not None]
        if not valid_data:
            return None
        
        # 返回 JSON 格式的数据，供前端 Chart.js 使用
        curve_data = {
            'frames': [r['frame_idx'] for r in valid_data],
            'delays': [r['delay_ms'] for r in valid_data],
            'times': [r['video_time_s'] for r in valid_data]
        }
        return curve_data
    
    def generate_html_report(self, results, video_path, curve_data, fps=59.84, frame_step=5):
        """生成 HTML 报告"""
        # 生成带时间戳的报告名
        from datetime import datetime
        report_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        html_path = Path("temp_phone_ts_report.html")
        
        valid_data = [r for r in results if r['delay_ms'] is not None]
        avg_delay = sum(r['delay_ms'] for r in valid_data) / len(valid_data) if valid_data else 0
        min_delay = min((r['delay_ms'] for r in valid_data), default=0)
        max_delay = max((r['delay_ms'] for r in valid_data), default=0)
        
        # 准备曲线数据
        chart_frames_json = json.dumps(curve_data['frames']) if curve_data else '[]'
        chart_delays_json = json.dumps(curve_data['delays']) if curve_data else '[]'
        chart_times_json = json.dumps(curve_data['times']) if curve_data else '[]'
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>视频延时分析报告 - {report_time}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: Arial, sans-serif; background: #f5f5f5; overflow: hidden; }}
        
        .main-layout {{ display: flex; height: 100vh; }}
        
        /* 左侧视频区域 - 固定 */
        .left-panel {{ 
            width: 45%; 
            background: #2c3e50; 
            padding: 20px; 
            display: flex; 
            flex-direction: column;
            justify-content: center;
            align-items: center;
        }}
        .left-panel h1 {{ 
            color: white; 
            margin-bottom: 20px; 
            text-align: center;
        }}
        .video-container {{ 
            width: 100%; 
            max-width: 800px;
        }}
        video {{ 
            width: 100%; 
            border: 3px solid #34495e; 
            border-radius: 8px; 
            box-shadow: 0 4px 20px rgba(0,0,0,0.3);
        }}
        .video-tip {{ 
            background: #34495e; 
            color: #ecf0f1;
            padding: 15px; 
            border-radius: 5px; 
            margin-top: 15px;
            text-align: center;
        }}
        .video-info {{
            background: #34495e;
            color: #ecf0f1;
            padding: 20px;
            border-radius: 5px;
            margin-top: 15px;
        }}
        .video-info h3 {{
            margin: 0 0 15px 0;
            font-size: 18px;
            text-align: center;
            border-bottom: 2px solid #4a5f7f;
            padding-bottom: 10px;
        }}
        .info-item {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #4a5f7f;
        }}
        .info-item:last-child {{
            border-bottom: none;
        }}
        .info-label {{
            color: #95a5a6;
            font-size: 14px;
        }}
        .info-value {{
            color: #ecf0f1;
            font-weight: bold;
            font-size: 14px;
        }}
        
        /* 右侧内容区域 - 可滚动 */
        .right-panel {{ 
            width: 55%; 
            background: white; 
            overflow-y: auto;
            padding: 30px;
        }}
        
        h2 {{ color: #2c3e50; margin-top: 30px; margin-bottom: 15px; border-bottom: 2px solid #3498db; padding-bottom: 8px; }}
        .section {{ margin: 20px 0; }}
        
        .stats {{ display: flex; justify-content: space-around; margin: 20px 0; flex-wrap: wrap; }}
        .stat-box {{ 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; 
            padding: 20px; 
            border-radius: 10px; 
            text-align: center; 
            flex: 1; 
            margin: 10px; 
            min-width: 150px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .stat-box h3 {{ margin: 0; font-size: 28px; }}
        .stat-box p {{ margin: 8px 0 0 0; font-size: 14px; opacity: 0.9; }}
        
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        th, td {{ padding: 14px; text-align: left; border-bottom: 1px solid #ecf0f1; }}
        th {{ background-color: #3498db; color: white; font-weight: 600; }}
        tbody tr {{ cursor: pointer; transition: background-color 0.2s; }}
        tbody tr:hover {{ background-color: #e8f4f8; }}
        tbody tr.selected {{ background-color: #d4e9f7; }}
        .status-ok {{ color: #27ae60; font-weight: bold; }}
        .status-fail {{ color: #e74c3c; font-weight: bold; }}
        
        .tip {{ 
            background: #fff9e6; 
            padding: 15px; 
            border-radius: 8px; 
            margin: 15px 0; 
            border-left: 4px solid #f39c12;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }}
        
        canvas {{ max-width: 100%; }}
    </style>
</head>
<body>
    <div class="main-layout">
        <!-- 左侧：视频固定 -->
        <div class="left-panel">
            <h1>视频延时分析报告</h1>
            <p style="color: #ecf0f1; margin-bottom: 15px; font-size: 14px;">{report_time}</p>
            <div class="video-container">
                <video id="mainVideo" controls>
                    <source src="temp_annotated_video.mp4" type="video/mp4">
                    您的浏览器不支持视频播放
                </video>
                <div class="video-tip" id="current-frame-display">
                    <div><strong>蓝框:</strong> T_app <span id="current-app" style="color: #5dade2;">(--)</span></div>
                    <div><strong>绿框:</strong> T_real <span id="current-real" style="color: #58d68d;">(--)</span></div>
                    <div><strong>红字:</strong> 延时 <span id="current-delay" style="color: #ec7063;">--</span></div>
                </div>
                <div class="video-info">
                    <h3>视频信息</h3>
                    <div class="info-item">
                        <span class="info-label">总帧数:</span>
                        <span class="info-value">{len(results)} 帧</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">有效帧数:</span>
                        <span class="info-value">{len(valid_data)} 帧</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">分析时长:</span>
                        <span class="info-value">{(results[-1]['video_time_s'] if results else 0):.2f} 秒</span>
                    </div>
                </div>
                <div class="video-info">
                    <h3>统计数据</h3>
                    <div class="info-item">
                        <span class="info-label">平均延时:</span>
                        <span class="info-value">{avg_delay:.2f} ms</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">最小延时:</span>
                        <span class="info-value">{min_delay:.2f} ms</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">最大延时:</span>
                        <span class="info-value">{max_delay:.2f} ms</span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">有效比例:</span>
                        <span class="info-value">{len(valid_data)}/{len(results)}</span>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- 右侧：可滚动内容 -->
        <div class="right-panel">
            <div class="tip">
                <strong>交互提示：</strong> 鼠标悬停在曲线或表格上，左侧视频会自动定位到对应帧
            </div>
            
            <h2>1. 延时曲线</h2>
            <div class="section">
                <canvas id="delayChart"></canvas>
            </div>
        
            <h2>2. 详细数据</h2>
            <div class="section">
                <table>
                    <thead>
                        <tr>
                            <th>帧号</th>
                            <th>视频时间(s)</th>
                            <th>T_app</th>
                            <th>T_real</th>
                            <th>延时(ms)</th>
                            <th>状态</th>
                        </tr>
                    </thead>
                    <tbody>
"""
        
        for i, r in enumerate(results):
            status_class = "status-ok" if r['status'] == 'ok' else "status-fail"
            video_time = r['video_time_s'] if r['video_time_s'] else 0
            video_time_str = f"{r['video_time_s']:.3f}" if r['video_time_s'] else 'N/A'
            app_time_display = r['app_time_str'] or 'N/A'
            real_time_display = r['real_time_str'] or 'N/A'
            delay_display = r['delay_ms'] if r['delay_ms'] is not None else 'N/A'
            
            html_content += f"""
            <tr onmouseenter="seekVideo({i}, this)" data-time="{video_time}" data-frame-index="{i}">
                <td>{r['frame_idx']}</td>
                <td>{video_time_str}</td>
                <td>{app_time_display}</td>
                <td>{real_time_display}</td>
                <td>{delay_display}</td>
                <td class="{status_class}">{r['status']}</td>
            </tr>
"""
        
        html_content += """
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    </div>
    
    <script>
        const video = document.getElementById('mainVideo');
        let currentRow = null;
        let pendingSeekData = null; // 存储待更新的帧数据（frameIndex + row）
        
        function seekVideo(frameIndex, row) {
            // 存储待更新的数据，等待 seeked 事件触发后再更新显示
            pendingSeekData = { frameIndex, row };
            
            // 设置手动seek标志，防止 updateFrameDisplay 覆盖
            isManualSeeking = true;
            
            // 调试输出
            console.log('[seekVideo] frameIndex=', frameIndex, 'delay=', frameData[frameIndex]?.delay_ms);
            
            // 【关键修复】跳到帧的"中点"时间，避免浏览器seek到前一帧
            // 如果跳到帧起点 (frameIndex / FPS)，浏览器可能因为精度问题跳到前一帧
            // 所以我们跳到 (frameIndex + 0.5) / FPS，确保落在目标帧范围内
            const exactTime = (frameIndex + 0.5) / annotatedFPS;
            console.log('[seekVideo] 跳转到帧中点时间=', exactTime.toFixed(4), '秒');
            
            // 确保视频已暂停
            if (!video.paused) {
                video.pause();
            }
            
            // 设置时间（触发 seeking -> seeked 事件）
            video.currentTime = exactTime;
        }
        
        // 更新显示数据的辅助函数
        function updateDisplayData(frameIndex) {
            if (frameIndex >= 0 && frameIndex < frameData.length) {
                const frame = frameData[frameIndex];
                console.log('[更新显示] 原始帧', frame.frame_idx, '延时', frame.delay_ms + 'ms');
                document.getElementById('current-app').textContent = frame.app_time_str ? '(' + frame.app_time_str + ')' : '(--)';
                document.getElementById('current-real').textContent = frame.real_time_str ? '(' + frame.real_time_str + ')' : '(--)';
                document.getElementById('current-delay').textContent = frame.delay_ms !== null ? frame.delay_ms + 'ms' : '--';
                currentFrameIndex = frameIndex;
            }
        }
        
        // 点击行也可以定位（防止悬停后又移开）
        const rows = document.querySelectorAll('tbody tr');
        rows.forEach(row => {{
            row.addEventListener('click', function() {{
                const frameIndex = parseInt(this.dataset.frameIndex);
                seekVideo(frameIndex, this);
                // 滚动到视频位置
                video.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
            }});
        }});
        
        // 初始化延时曲线图
        const chartFrames = __CHART_FRAMES__;
        const chartDelays = __CHART_DELAYS__;
        const chartTimes = __CHART_TIMES__;
        
        if (chartFrames.length > 0) {{
            const ctx = document.getElementById('delayChart').getContext('2d');
            const delayChart = new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: chartFrames,
                    datasets: [{{
                        label: '延时 (ms)',
                        data: chartDelays,
                        borderColor: 'rgb(75, 192, 192)',
                        backgroundColor: 'rgba(75, 192, 192, 0.2)',
                        borderWidth: 2,
                        pointRadius: 5,
                        pointHoverRadius: 8,
                        tension: 0.1
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: true,
                    interaction: {{
                        mode: 'index',
                        intersect: false
                    }},
                    plugins: {{
                        legend: {{
                            display: true,
                            position: 'top'
                        }},
                        tooltip: {{
                            callbacks: {{
                                afterLabel: function(context) {{
                                    return '点击定位到视频';
                                }}
                            }}
                        }}
                    }},
                    scales: {{
                        x: {{
                            title: {{
                                display: true,
                                text: '帧号'
                            }}
                        }},
                        y: {{
                            title: {{
                                display: true,
                                text: '延时 (ms)'
                            }}
                        }}
                    }},
                    onHover: function(event, activeElements) {{
                        if (activeElements.length > 0) {{
                            const idx = activeElements[0].index;
                            console.log('[Chart hover] idx=', idx);
                            seekVideo(idx, null);
                        }}
                    }},
                    onClick: function(event, activeElements) {{
                        if (activeElements.length > 0) {{
                            const idx = activeElements[0].index;
                            console.log('[Chart click] idx=', idx);
                            seekVideo(idx, null);
                            video.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                        }}
                    }}
                }}
            }});
        }}
        
        // 准备帧数据（用于当前帧显示）
        const frameData = __FRAME_DATA__;
        let currentFrameIndex = 0;
        
        // 标定视频的FPS（原始FPS / frame_step）
        const annotatedFPS = __ANNOTATED_FPS__;
        
        // 标志：是否正在手动seek（避免事件冲突）
        let isManualSeeking = false;
        
        // 更新当前帧数据显示
        function updateFrameDisplay() {{
            // 如果正在手动seek，不执行自动更新（避免覆盖手动设置的数据）
            if (isManualSeeking) {{
                return;
            }}
            
            const currentTime = video.currentTime;
            
            // 找到最接近当前时间的帧
            let closestFrame = frameData[0];
            let minDiff = Infinity;
            
            frameData.forEach((frame, index) => {{
                const frameTime = frame.video_time_s !== null && frame.video_time_s !== undefined ? frame.video_time_s : 0;
                const diff = Math.abs(currentTime - frameTime);
                if (diff < minDiff) {{
                    minDiff = diff;
                    closestFrame = frame;
                    currentFrameIndex = index;
                }}
            }});
            
            // 更新左侧当前帧数据显示
            document.getElementById('current-app').textContent = closestFrame.app_time_str ? '(' + closestFrame.app_time_str + ')' : '(--)';
            document.getElementById('current-real').textContent = closestFrame.real_time_str ? '(' + closestFrame.real_time_str + ')' : '(--)';
            document.getElementById('current-delay').textContent = closestFrame.delay_ms !== null ? closestFrame.delay_ms + 'ms' : '--';
        }}
        
        // 视频事件监听（播放时自动更新）
        video.addEventListener('timeupdate', updateFrameDisplay);
        video.addEventListener('loadeddata', updateFrameDisplay);
        
        // 在seeked事件中处理待更新的帧数据（最可靠的方法）
        video.addEventListener('seeked', () => {{
            console.log('[seeked] video.currentTime=', video.currentTime.toFixed(4));
            
            // 如果有待更新的数据，延迟200ms更新显示（等待浏览器渲染画面）
            if (pendingSeekData) {{
                const {{ frameIndex, row }} = pendingSeekData;
                console.log('[seeked] 将在200ms后更新显示: frameIndex=', frameIndex, 'delay=', frameData[frameIndex]?.delay_ms);
                
                setTimeout(() => {{
                    console.log('[延迟更新] 现在更新显示: frameIndex=', frameIndex);
                    // 更新左侧数据显示
                    updateDisplayData(frameIndex);
                    
                    // 高亮当前行
                    if (row) {{
                        if (currentRow) {{
                            currentRow.classList.remove('selected');
                        }}
                        currentRow = row;
                        currentRow.classList.add('selected');
                    }}
                    
                    // 清除待更新数据
                    pendingSeekData = null;
                    
                    // 清除手动seek标志
                    isManualSeeking = false;
                    console.log('[完成] isManualSeeking = false');
                }}, 200);
            }} else {{
                // 没有待更新数据，直接清除标志
                setTimeout(() => {{
                    isManualSeeking = false;
                    console.log('[清除标志] isManualSeeking = false');
                }}, 100);
            }}
        }});
    </script>
</body>
</html>
"""
        
        # 准备帧数据JSON（用于当前帧显示）
        frame_data_json = json.dumps([{
            'frame_idx': r['frame_idx'],
            'video_time_s': r['video_time_s'],
            'app_time_str': r['app_time_str'],
            'real_time_str': r['real_time_str'],
            'delay_ms': r['delay_ms']
        } for r in results])
        
        # 计算标定视频的FPS
        annotated_fps = fps / frame_step if fps > 0 and frame_step > 0 else 25
        
        # 替换所有占位符
        html_content = html_content.replace('__CHART_FRAMES__', chart_frames_json)
        html_content = html_content.replace('__CHART_DELAYS__', chart_delays_json)
        html_content = html_content.replace('__CHART_TIMES__', chart_times_json)
        html_content = html_content.replace('__FRAME_DATA__', frame_data_json)
        html_content = html_content.replace('__ANNOTATED_FPS__', str(annotated_fps))
        
        # 修复双大括号问题（f-string 转义导致的）
        html_content = html_content.replace('{{', '{').replace('}}', '}')
        
        with html_path.open("w", encoding="utf-8") as f:
            f.write(html_content)
        
        return html_path


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.video_path = None
        self.app_roi = None
        self.config_path = Path("roi_config.json")
        self.worker = None
        self.use_gpu = False
        self.resize_ratio = 0.5
        self.init_ui()
        self.load_config()
    
    def init_ui(self):
        self.setWindowTitle("视频延时分析工具")
        self.setGeometry(100, 100, 900, 700)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # 视频选择
        file_layout = QHBoxLayout()
        self.video_label = QLabel("未选择视频")
        btn_select = QPushButton("选择视频")
        btn_select.clicked.connect(self.select_video)
        file_layout.addWidget(QLabel("视频文件:"))
        file_layout.addWidget(self.video_label, 1)
        file_layout.addWidget(btn_select)
        layout.addLayout(file_layout)
        
        # ROI 状态
        roi_layout = QHBoxLayout()
        self.roi_status_label = QLabel("T_app ROI: 未配置")
        btn_calibrate = QPushButton("标定 T_app")
        btn_calibrate.clicked.connect(self.calibrate_roi)
        roi_layout.addWidget(self.roi_status_label, 1)
        roi_layout.addWidget(btn_calibrate)
        layout.addLayout(roi_layout)
        
        # 性能设置
        perf_group = QGroupBox("性能设置")
        perf_layout = QHBoxLayout()
        
        # GPU 开关
        self.gpu_checkbox = QCheckBox("使用 GPU 加速")
        self.gpu_checkbox.setChecked(False)
        self.gpu_checkbox.stateChanged.connect(self.on_gpu_changed)
        perf_layout.addWidget(self.gpu_checkbox)
        
        # 分辨率缩放
        perf_layout.addWidget(QLabel("OCR 分辨率:"))
        self.resize_combo = QComboBox()
        self.resize_combo.addItem("50% (最快)", 0.5)
        self.resize_combo.addItem("75% (平衡)", 0.75)
        self.resize_combo.addItem("100% (最清晰)", 1.0)
        self.resize_combo.setCurrentIndex(0)
        self.resize_combo.currentIndexChanged.connect(self.on_resize_changed)
        perf_layout.addWidget(self.resize_combo)
        
        perf_group.setLayout(perf_layout)
        layout.addWidget(perf_group)
        
        # 开始分析
        self.btn_start = QPushButton("开始分析")
        self.btn_start.clicked.connect(self.start_analysis)
        self.btn_start.setEnabled(False)
        layout.addWidget(self.btn_start)
        
        # 进度条
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        
        # 日志
        layout.addWidget(QLabel("处理日志:"))
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)
        
        # 结果按钮
        result_layout = QHBoxLayout()
        self.btn_open_html = QPushButton("打开 HTML 报告")
        self.btn_open_html.clicked.connect(self.open_html_report)
        self.btn_open_html.setEnabled(False)
        
        self.btn_open_csv = QPushButton("打开 CSV 数据")
        self.btn_open_csv.clicked.connect(self.open_csv_report)
        self.btn_open_csv.setEnabled(False)
        
        result_layout.addWidget(self.btn_open_html)
        result_layout.addWidget(self.btn_open_csv)
        layout.addLayout(result_layout)
    
    def load_config(self):
        """加载配置"""
        if self.config_path.exists():
            try:
                with self.config_path.open("r") as f:
                    config = json.load(f)
                    self.app_roi = tuple(config['app_roi'])
                    self.roi_status_label.setText(f"T_app ROI: {self.app_roi}")
                    self.append_log("已加载保存的 ROI 配置")
            except Exception as e:
                self.append_log(f"加载配置失败: {e}")
    
    def save_config(self):
        """保存配置"""
        if self.app_roi:
            try:
                config = {'app_roi': list(self.app_roi)}
                with self.config_path.open("w") as f:
                    json.dump(config, f, indent=2)
                self.append_log("ROI 配置已保存")
            except Exception as e:
                self.append_log(f"保存配置失败: {e}")
    
    def select_video(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择视频文件", "", "视频文件 (*.mp4 *.avi *.mov)"
        )
        if file_path:
            self.video_path = file_path
            self.video_label.setText(Path(file_path).name)
            self.update_start_button()
            self.append_log(f"已选择视频: {file_path}")
    
    def calibrate_roi(self):
        """标定 ROI"""
        if not self.video_path:
            QMessageBox.warning(self, "提示", "请先选择视频文件")
            return
        
        # 读取第1帧
        cap = cv2.VideoCapture(self.video_path)
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            QMessageBox.critical(self, "错误", "无法读取视频第1帧")
            return
        
        h, w = frame.shape[:2]
        
        # 使用上次保存的位置，或默认位置
        if self.app_roi:
            initial_roi = self.app_roi
            self.append_log("使用上次保存的 ROI 位置")
        else:
            # 默认 ROI（底部中间）
            initial_roi = (int(0.30 * w), int(0.75 * h), int(0.70 * w), int(0.95 * h))
            self.append_log("使用默认 ROI 位置")
        
        # 打开调整对话框
        dialog = ROIAdjustDialog(frame, initial_roi, self)
        if dialog.exec_() == QDialog.Accepted and dialog.confirmed:
            self.app_roi = dialog.get_roi()
            self.roi_status_label.setText(f"T_app ROI: {self.app_roi}")
            self.save_config()
            self.update_start_button()
            self.append_log(f"T_app ROI 已更新: {self.app_roi}")
    
    def on_gpu_changed(self, state):
        """GPU 选项变化"""
        self.use_gpu = (state == Qt.Checked)
        status = "已启用" if self.use_gpu else "已禁用"
        self.append_log(f"GPU 加速: {status}")
    
    def on_resize_changed(self, index):
        """分辨率选项变化"""
        self.resize_ratio = self.resize_combo.currentData()
        self.append_log(f"OCR 分辨率缩放: {int(self.resize_ratio*100)}%")
    
    def update_start_button(self):
        """更新开始按钮状态"""
        self.btn_start.setEnabled(self.video_path is not None and self.app_roi is not None)
    
    def start_analysis(self):
        if not self.video_path or not self.app_roi:
            return
        
        self.btn_start.setEnabled(False)
        self.btn_open_html.setEnabled(False)
        self.btn_open_csv.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_text.clear()
        
        self.worker = AnalysisWorker(self.video_path, self.app_roi, self.use_gpu, self.resize_ratio)
        self.worker.progress.connect(self.update_progress)
        self.worker.log_message.connect(self.append_log)
        self.worker.finished.connect(self.analysis_finished)
        self.worker.start()
    
    def update_progress(self, current, total):
        progress = int((current / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(progress)
    
    def append_log(self, message):
        self.log_text.append(message)
    
    def analysis_finished(self, success, message):
        self.btn_start.setEnabled(True)
        
        if success:
            self.btn_open_html.setEnabled(True)
            self.btn_open_csv.setEnabled(True)
            QMessageBox.information(self, "完成", f"分析完成!\n\n{message}")
        else:
            QMessageBox.critical(self, "错误", f"分析失败\n\n{message}")
    
    def open_html_report(self):
        html_path = Path("temp_phone_ts_report.html")
        if html_path.exists():
            subprocess.run(["explorer", str(html_path.resolve())])
    
    def open_csv_report(self):
        csv_path = Path("temp_phone_ts_report.csv")
        if csv_path.exists():
            subprocess.run(["explorer", "/select,", str(csv_path.resolve())])


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
