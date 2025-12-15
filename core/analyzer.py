"""
视频分析器
核心业务逻辑：处理视频、识别时间、计算延时
"""
import cv2
import csv
from pathlib import Path
from .ocr_engine import OCREngine
from .roi_detector import ROIDetector
from config import DEBUG_DIR, DEFAULT_FRAME_STEP


class VideoAnalyzer:
    """视频延时分析器"""
    
    def __init__(self, use_gpu: bool = False, resize_ratio: float = 0.5):
        """
        初始化分析器
        
        Args:
            use_gpu: 是否使用GPU加速OCR
            resize_ratio: OCR图像缩放比例（0.5=50%，降低分辨率提速）
        """
        self.ocr_engine = OCREngine(use_gpu=use_gpu)
        self.roi_detector = ROIDetector()
        self.resize_ratio = resize_ratio
    
    def set_app_roi(self, roi: tuple):
        """设置T_app的ROI"""
        self.roi_detector.set_app_roi(roi)
    
    def get_app_roi(self) -> tuple:
        """获取T_app的ROI"""
        return self.roi_detector.get_app_roi()
    
    def extract_time_from_roi(self, frame, roi) -> str:
        """
        从ROI中提取时间
        
        Args:
            frame: OpenCV图像帧
            roi: ROI坐标 (x1, y1, x2, y2)
            
        Returns:
            时间字符串 "HH:MM:SS.mmm"，失败返回None
        """
        if not roi:
            return None
        
        x1, y1, x2, y2 = roi
        h, w = frame.shape[:2]
        
        # 边界检查
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        
        # 提取ROI
        roi_img = frame[y1:y2, x1:x2]
        if roi_img.size == 0:
            return None
        
        # 根据设置缩放（提速）
        if self.resize_ratio < 1.0:
            roi_img = cv2.resize(
                roi_img, (0, 0), 
                fx=self.resize_ratio, 
                fy=self.resize_ratio, 
                interpolation=cv2.INTER_AREA
            )
        
        # OCR识别
        text = self.ocr_engine.extract_text(roi_img)
        
        # 解析时间
        return self.ocr_engine.parse_time(text)
    
    def analyze_video(
        self, 
        video_path: str, 
        frame_limit: int = 100,
        frame_step: int = DEFAULT_FRAME_STEP,
        progress_callback=None,
        log_callback=None
    ) -> dict:
        """
        分析视频，提取延时数据
        
        Args:
            video_path: 视频文件路径
            frame_limit: 处理的最大帧数
            frame_step: 跳帧步长
            progress_callback: 进度回调函数 callback(current, total)
            log_callback: 日志回调函数 callback(message)
            
        Returns:
            分析结果字典:
            {
                'results': [帧数据列表],
                'annotated_frames': [标定帧列表],
                'fps': 视频FPS,
                'frame_step': 跳帧步长,
                'total_frames': 总帧数
            }
        """
        video_path = Path(video_path)
        
        if log_callback:
            log_callback(f"开始处理视频: {video_path.name}")
        
        # 打开视频
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise ValueError("无法打开视频文件")
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        if log_callback:
            log_callback(f"FPS={fps:.2f}, 总帧数={total_frames}, 处理前{frame_limit}帧")
        
        # 数据收集
        results = []
        annotated_frames = []
        
        frame_idx = 0
        processed_count = 0
        
        # 记录上一帧的时间戳，用于单调性验证
        last_app_time_ms = None
        last_real_time_ms = None
        
        app_roi = self.roi_detector.get_app_roi()
        if not app_roi:
            cap.release()
            raise ValueError("T_app ROI未设置，请先进行标定")
        
        while True:
            if frame_idx > frame_limit:
                break
            
            ret, frame = cap.read()
            if not ret:
                break
            
            # 跳帧处理
            if frame_idx % frame_step != 0:
                frame_idx += 1
                continue
            
            if progress_callback:
                progress_callback(frame_idx, frame_limit)
            
            # 检测T_real的ROI
            real_roi = self.roi_detector.detect_real_time_roi(frame)
            
            # 提取时间
            app_time_str = self.extract_time_from_roi(frame, app_roi)
            real_time_str = self.extract_time_from_roi(frame, real_roi)
            
            # 计算延时
            video_time_s = frame_idx / fps if fps > 0 else None
            app_time_ms = self.ocr_engine.time_to_ms(app_time_str)
            real_time_ms = self.ocr_engine.time_to_ms(real_time_str)
            
            # 时间单调性验证：防止OCR识别错误
            if app_time_ms is not None and last_app_time_ms is not None:
                if app_time_ms < last_app_time_ms:
                    if log_callback:
                        log_callback(
                            f"⚠️ 帧 {frame_idx}: T_app时间倒退 "
                            f"({app_time_str} < 上一帧)，标记为识别失败"
                        )
                    app_time_ms = None
                    app_time_str = None
            
            if real_time_ms is not None and last_real_time_ms is not None:
                if real_time_ms < last_real_time_ms:
                    if log_callback:
                        log_callback(
                            f"⚠️ 帧 {frame_idx}: T_real时间倒退 "
                            f"({real_time_str} < 上一帧)，标记为识别失败"
                        )
                    real_time_ms = None
                    real_time_str = None
            
            # 更新上一帧时间戳
            if app_time_ms is not None:
                last_app_time_ms = app_time_ms
            if real_time_ms is not None:
                last_real_time_ms = real_time_ms
            
            delay_ms = None
            status = "ok"
            
            if app_time_ms is None:
                status = "app_fail"
            if real_time_ms is None:
                status = "real_fail" if status == "ok" else "both_fail"
            if app_time_ms is not None and real_time_ms is not None:
                delay_ms = app_time_ms - real_time_ms
            
            # 收集数据
            results.append({
                'video_name': video_path.name,
                'frame_idx': frame_idx,
                'video_time_s': video_time_s,
                'app_time_str': app_time_str,
                'app_time_ms': app_time_ms,
                'real_time_str': real_time_str,
                'real_time_ms': real_time_ms,
                'delay_ms': delay_ms,
                'status': status
            })
            
            # 绘制标定图
            annotated = self._draw_annotations(
                frame.copy(), 
                app_roi, 
                real_roi, 
                app_time_str, 
                real_time_str, 
                delay_ms
            )
            annotated_frames.append(annotated)
            
            # 日志
            if log_callback:
                if status == "ok":
                    log_callback(
                        f"帧 {frame_idx}: T_app={app_time_str}, T_real={real_time_str}, 延时={delay_ms}ms"
                    )
                else:
                    log_callback(f"帧 {frame_idx}: {status}")
            
            frame_idx += 1
            processed_count += 1
        
        cap.release()
        
        if log_callback:
            log_callback(f"处理完成，共 {processed_count} 帧")
        
        return {
            'results': results,
            'annotated_frames': annotated_frames,
            'fps': fps,
            'frame_step': frame_step,
            'total_frames': total_frames
        }
    
    def _draw_annotations(
        self, 
        frame, 
        app_roi, 
        real_roi, 
        app_time_str, 
        real_time_str, 
        delay_ms
    ):
        """
        在帧上绘制标注
        
        Args:
            frame: 图像帧
            app_roi: T_app的ROI
            real_roi: T_real的ROI
            app_time_str: T_app时间字符串
            real_time_str: T_real时间字符串
            delay_ms: 延时毫秒数
            
        Returns:
            标注后的图像帧
        """
        # 画T_app蓝框
        if app_roi:
            x1, y1, x2, y2 = app_roi
            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
            label = f"T_app: {app_time_str}" if app_time_str else "T_app: N/A"
            cv2.putText(
                frame, label, (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2
            )
        
        # 画T_real绿框
        if real_roi:
            x1, y1, x2, y2 = real_roi
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            label = f"T_real: {real_time_str}" if real_time_str else "T_real: N/A"
            cv2.putText(
                frame, label, (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2
            )
        
        # 显示延时（红色）
        if delay_ms is not None:
            delay_text = f"Delay: {delay_ms}ms"
            cv2.putText(
                frame, delay_text, (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2
            )
        
        return frame
    
    def save_csv_report(self, results: list, output_path: str):
        """
        保存CSV报告
        
        Args:
            results: 分析结果列表
            output_path: 输出文件路径
        """
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                "video_name", "frame_idx", "video_time_s",
                "app_time_str", "app_time_ms",
                "real_time_str", "real_time_ms",
                "delay_ms", "status"
            ])
            
            for r in results:
                writer.writerow([
                    r['video_name'],
                    r['frame_idx'],
                    f"{r['video_time_s']:.6f}" if r['video_time_s'] is not None else "",
                    r['app_time_str'] or "",
                    r['app_time_ms'] or "",
                    r['real_time_str'] or "",
                    r['real_time_ms'] or "",
                    r['delay_ms'] if r['delay_ms'] is not None else "",
                    r['status']
                ])
    
    def save_annotated_video(
        self, 
        annotated_frames: list, 
        output_path: str, 
        fps: float,
        codec: str = 'avc1'
    ):
        """
        保存标定视频
        
        Args:
            annotated_frames: 标注后的帧列表
            output_path: 输出视频路径
            fps: 输出视频的FPS
            codec: 视频编码器
        """
        if not annotated_frames:
            print(f"警告: 没有标注帧可保存")
            return
        
        print(f"开始保存标定视频: {output_path}")
        print(f"  帧数: {len(annotated_frames)}, FPS: {fps}, 编码: {codec}")
        
        h, w = annotated_frames[0].shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*codec)
        out = cv2.VideoWriter(str(output_path), fourcc, fps, (w, h))
        
        if not out.isOpened():
            print(f"错误: 无法创建视频写入器")
            return
        
        for i, frame in enumerate(annotated_frames):
            success = out.write(frame)
            if i == 0:
                print(f"  第一帧写入: {'成功' if success is not False else '失败'}")
        
        out.release()
        
        # 验证文件是否存在
        from pathlib import Path
        if Path(output_path).exists():
            size = Path(output_path).stat().st_size
            print(f"视频保存成功: {output_path}, 大小: {size / 1024:.2f} KB")
        else:
            print(f"错误: 视频文件未创建: {output_path}")

