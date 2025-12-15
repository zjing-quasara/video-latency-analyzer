"""
后台工作线程
在GUI中执行耗时的视频分析任务
"""
from PyQt5.QtCore import QThread, pyqtSignal
from pathlib import Path
from datetime import datetime
from core import VideoAnalyzer, ReportGenerator
from config import DEFAULT_OUTPUT_DIR, REPORT_CONFIG, set_gpu_device


class AnalysisWorker(QThread):
    """视频分析后台线程"""
    
    # 信号定义
    progress = pyqtSignal(int, int)  # 当前进度, 总进度
    log_message = pyqtSignal(str)     # 日志消息
    finished = pyqtSignal(bool, str, str)  # 成功/失败, 消息, 报告文件夹路径
    
    def __init__(self, video_path, app_roi, use_gpu, resize_ratio, frame_limit=300, output_dir=None):
        """
        初始化分析线程
        
        Args:
            video_path: 视频文件路径
            app_roi: T_app的ROI坐标
            use_gpu: 是否使用GPU
            resize_ratio: OCR分辨率缩放比例
            frame_limit: 处理的最大帧数
            output_dir: 输出目录路径
        """
        super().__init__()
        self.video_path = video_path
        self.app_roi = app_roi
        self.use_gpu = use_gpu
        self.resize_ratio = resize_ratio
        self.frame_limit = frame_limit
        self.output_dir = Path(output_dir) if output_dir else DEFAULT_OUTPUT_DIR
    
    def run(self):
        """线程执行函数"""
        try:
            # 设置GPU
            set_gpu_device(self.use_gpu)
            
            # 创建分析器
            analyzer = VideoAnalyzer(
                use_gpu=self.use_gpu,
                resize_ratio=self.resize_ratio
            )
            analyzer.set_app_roi(self.app_roi)
            
            # 执行分析
            analysis_result = analyzer.analyze_video(
                video_path=self.video_path,
                frame_limit=self.frame_limit,
                frame_step=5,
                progress_callback=self._on_progress,
                log_callback=self._on_log
            )
            
            results = analysis_result['results']
            annotated_frames = analysis_result['annotated_frames']
            fps = analysis_result['fps']
            frame_step = analysis_result['frame_step']
            
            # 创建带时间戳的输出文件夹
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            video_name = Path(self.video_path).stem
            report_folder_name = f"{video_name}_{timestamp}"
            report_dir = self.output_dir / report_folder_name
            report_dir.mkdir(parents=True, exist_ok=True)
            
            self.log_message.emit(f"创建报告文件夹: {report_dir}")
            
            # 保存CSV报告
            csv_path = report_dir / f"{report_folder_name}.csv"
            analyzer.save_csv_report(results, str(csv_path))
            self.log_message.emit(f"CSV报告已保存: {csv_path.name}")
            
            # 生成标定视频（直接使用OpenCV，参考temp_delay_gui.py）
            self.log_message.emit("正在生成标定视频...")
            video_path = report_dir / f"{report_folder_name}.mp4"
            
            if annotated_frames:
                import cv2
                self.log_message.emit(f"标注帧数量: {len(annotated_frames)}")
                h, w = annotated_frames[0].shape[:2]
                self.log_message.emit(f"视频尺寸: {w}x{h}, FPS: {fps / frame_step:.2f}")
                
                # 尝试多个编码器，找到可用的
                codecs_to_try = [
                    ('mp4v', 'MPEG-4'),
                    ('avc1', 'H.264'),
                    ('X264', 'X264'),
                    ('XVID', 'XVID'),
                ]
                
                out = None
                used_codec = None
                
                for codec, codec_name in codecs_to_try:
                    try:
                        fourcc = cv2.VideoWriter_fourcc(*codec)
                        out = cv2.VideoWriter(str(video_path), fourcc, fps / frame_step, (w, h))
                        if out.isOpened():
                            used_codec = codec_name
                            self.log_message.emit(f"使用编码器: {codec_name} ({codec})")
                            break
                        else:
                            out.release()
                    except:
                        pass
                
                if not out or not out.isOpened():
                    self.log_message.emit("错误: 所有编码器都无法打开！")
                    self.log_message.emit("请检查OpenCV安装: pip install opencv-python==4.6.0.66")
                else:
                    self.log_message.emit(f"保存路径: {video_path}")
                    self.log_message.emit("开始写入帧...")
                    
                    for i, ann_frame in enumerate(annotated_frames):
                        out.write(ann_frame)
                        if i == 0:
                            self.log_message.emit(f"第一帧已写入")
                    
                    out.release()
                    self.log_message.emit(f"所有 {len(annotated_frames)} 帧已写入，VideoWriter 已释放")
                    
                    # 验证文件
                    if video_path.exists():
                        size = video_path.stat().st_size
                        self.log_message.emit(f"✓ 标定视频已保存: {video_path.name} ({size/1024:.2f} KB)")
                    else:
                        self.log_message.emit(f"✗ 错误: 视频文件未创建！路径: {video_path}")
            else:
                self.log_message.emit("错误: annotated_frames 为空，无法生成视频")
            
            # 生成HTML报告（使用相对路径引用视频）
            html_path = report_dir / f"{report_folder_name}.html"
            ReportGenerator.generate_html(
                results=results,
                video_filename=f"{report_folder_name}.mp4",  # 相对路径
                fps=fps,
                frame_step=frame_step,
                output_path=str(html_path)
            )
            self.log_message.emit(f"HTML报告已保存: {html_path.name}")
            
            self.finished.emit(True, f"分析完成！\n报告文件夹: {report_dir}", str(report_dir))
        
        except Exception as e:
            error_msg = f"分析失败: {str(e)}"
            self.log_message.emit(error_msg)
            import traceback
            self.log_message.emit(traceback.format_exc())
            self.finished.emit(False, error_msg, "")
    
    def _on_progress(self, current, total):
        """进度回调"""
        self.progress.emit(current, total)
    
    def _on_log(self, message):
        """日志回调"""
        self.log_message.emit(message)

