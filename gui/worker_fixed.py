"""
后台工作线程 - 直接复制自temp_delay_gui.py的能工作的版本
"""
import cv2
import csv
import re
import json
from pathlib import Path
from datetime import datetime
from PyQt5.QtCore import QThread, pyqtSignal
from paddleocr import PaddleOCR


class AnalysisWorker(QThread):
    """视频分析后台线程 - 使用temp_delay_gui.py中验证过的实现"""
    
    progress = pyqtSignal(int, int)
    log_message = pyqtSignal(str)
    finished = pyqtSignal(bool, str, str)
    
    def __init__(self, video_path, app_roi, use_gpu, resize_ratio, frame_limit=30, output_dir=None):
        super().__init__()
        self.video_path = video_path
        self.app_roi = app_roi
        self.use_gpu = use_gpu
        self.resize_ratio = resize_ratio
        self.frame_limit = frame_limit
        self.output_dir = Path(output_dir) if output_dir else Path.home() / "Desktop" / "视频延时分析"
        self.ocr_engine = None
    
    def run(self):
        try:
            # 初始化OCR
            import os
            os.environ['CUDA_VISIBLE_DEVICES'] = '0' if self.use_gpu else '-1'
            self.ocr_engine = PaddleOCR(lang="en")
            self.log_message.emit("PaddleOCR 初始化完成")
            
            success, message, report_folder = self.analyze_video()
            self.finished.emit(success, message, report_folder)
        except Exception as e:
            import traceback
            self.finished.emit(False, f"错误: {str(e)}\n{traceback.format_exc()}", "")
    
    def detect_real_time_roi(self, frame):
        """动态检测 T_real"""
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        _, th = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY_INV)
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
        
        if self.resize_ratio < 1.0:
            roi_img = cv2.resize(roi_img, (0, 0), fx=self.resize_ratio, fy=self.resize_ratio, interpolation=cv2.INTER_AREA)
        roi_rgb = cv2.cvtColor(roi_img, cv2.COLOR_BGR2RGB)
        
        try:
            ocr_result = self.ocr_engine.ocr(roi_rgb)
            if not ocr_result or len(ocr_result) == 0:
                return None
            
            result_list = ocr_result[0] if ocr_result else []
            if not result_list:
                return None
            
            texts = []
            for item in result_list:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    text_info = item[1]
                    if isinstance(text_info, (list, tuple)) and len(text_info) >= 1:
                        texts.append(str(text_info[0]))
            
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
        """分析视频 - 直接复制自temp_delay_gui.py"""
        video_path = Path(self.video_path)
        frame_step = 5
        
        # 创建报告文件夹
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        video_name = video_path.stem
        report_folder_name = f"{video_name}_{timestamp}"
        report_dir = self.output_dir / report_folder_name
        report_dir.mkdir(parents=True, exist_ok=True)
        
        self.log_message.emit(f"创建报告文件夹: {report_dir}")
        self.log_message.emit(f"开始处理视频: {video_path.name}")
        
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return False, "无法打开视频", ""
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.log_message.emit(f"FPS={fps:.2f}, 总帧数={total}, 处理前{self.frame_limit}帧")
        
        results = []
        annotated_frames = []
        
        # 保存CSV
        csv_path = report_dir / f"{report_folder_name}.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
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
                
                # 收集数据
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
                if self.app_roi:
                    x1, y1, x2, y2 = self.app_roi
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (255, 0, 0), 2)
                    label = f"T_app: {app_time_str}" if app_time_str else "T_app: N/A"
                    cv2.putText(annotated, label, (x1, y1 - 10),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
                
                if real_roi:
                    x1, y1, x2, y2 = real_roi
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    label = f"T_real: {real_time_str}" if real_time_str else "T_real: N/A"
                    cv2.putText(annotated, label, (x1, y1 - 10),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                
                if delay_ms is not None:
                    delay_text = f"Delay: {delay_ms}ms"
                    cv2.putText(annotated, delay_text, (10, 30),
                               cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
                
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
        self.log_message.emit("CSV报告已保存: " + csv_path.name)
        
        # 生成标定视频 - 使用temp_delay_gui.py的方式
        self.log_message.emit("正在生成标定视频...")
        video_out_path = report_dir / f"{report_folder_name}.mp4"
        if annotated_frames:
            h, w = annotated_frames[0].shape[:2]
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')  # 使用mp4v编码
            out = cv2.VideoWriter(str(video_out_path), fourcc, fps / frame_step, (w, h))
            for ann_frame in annotated_frames:
                out.write(ann_frame)
            out.release()
            
            if video_out_path.exists():
                size = video_out_path.stat().st_size
                self.log_message.emit(f"标定视频已保存: {video_out_path.name} ({size/1024:.2f} KB)")
            else:
                self.log_message.emit("警告: 视频文件未创建")
        
        # 生成HTML报告
        self.log_message.emit("正在生成 HTML 报告...")
        from core.report_generator import ReportGenerator
        html_path = report_dir / f"{report_folder_name}.html"
        ReportGenerator.generate_html(
            results=results,
            video_filename=f"{report_folder_name}.mp4",
            fps=fps,
            frame_step=frame_step,
            output_path=str(html_path)
        )
        self.log_message.emit("HTML报告已保存: " + html_path.name)
        
        return True, f"分析完成！\n报告文件夹: {report_dir}", str(report_dir)



