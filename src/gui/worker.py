"""
后台工作线程 - 视频延时分析
"""
import cv2
import csv
import os
from pathlib import Path
from datetime import datetime
from PyQt5.QtCore import QThread, pyqtSignal

# 导入时间识别模块
from src.core.time_detector import (
    detect_time_app,
    detect_time_real,
    detect_time_real_optimized,
    parse_time_to_ms
)
from src.core.roi_tracker import ROITracker
from src.core.anomaly_detector import AnomalyDetector


class AnalysisWorker(QThread):
    """视频分析后台线程"""
    
    progress = pyqtSignal(int, int)
    log_message = pyqtSignal(str)
    finished = pyqtSignal(bool, str, str)
    
    def __init__(self, video_path, app_roi, use_gpu, resize_ratio, frame_limit, frame_step, treal_format, output_dir=None, phone_log=None, pc_log=None):
        super().__init__()
        from src.utils.logger import get_logger
        self.logger = get_logger('AnalysisWorker')
        
        self.video_path = video_path
        self.app_roi = app_roi
        self.use_gpu = use_gpu
        self.resize_ratio = resize_ratio
        self.frame_limit = frame_limit
        self.frame_step = frame_step
        self.treal_format = treal_format
        self.output_dir = Path(output_dir) if output_dir else Path.home() / "Desktop" / "视频延时分析"
        self.phone_log = phone_log
        self.pc_log = pc_log
        self.ocr = None
        
        self.logger.info(f"分析worker已创建: video={Path(video_path).name}, gpu={use_gpu}, limit={frame_limit}, step={frame_step}")
    
    def run(self):
        try:
            self.logger.info("开始视频分析任务")
            
            # 初始化OCR引擎
            self.log_message.emit("初始化 OCR 引擎...")
            try:
                from paddleocr import PaddleOCR
                import os
                import sys
                
                # 确定模型路径（支持打包后的exe）
                if getattr(sys, 'frozen', False):
                    # 打包后的exe环境
                    base_path = Path(sys._MEIPASS)
                else:
                    # 开发环境
                    base_path = Path(__file__).parent.parent.parent
                
                models_path = base_path / "models" / "whl"
                
                # 检查本地模型是否存在
                if models_path.exists():
                    self.log_message.emit("使用本地OCR模型...")
                    self.logger.info(f"使用本地模型: {models_path}")
                    
                    # 使用本地模型
                    self.ocr = PaddleOCR(
                        use_angle_cls=False,
                        lang='en',
                        det_model_dir=str(models_path / "det" / "en" / "en_PP-OCRv3_det_infer"),
                        rec_model_dir=str(models_path / "rec" / "en" / "en_PP-OCRv4_rec_infer"),
                        cls_model_dir=str(models_path / "cls" / "ch_ppocr_mobile_v2.0_cls_infer"),
                        show_log=False
                    )
                    self.log_message.emit(f"[OK] OCR 引擎初始化完成（使用本地模型）")
                else:
                    # 使用默认配置（会自动下载模型）
                    self.log_message.emit("首次运行，正在下载OCR模型（约15MB）...")
                    self.logger.info("本地模型不存在，使用默认配置（会自动下载）")
                    
                    self.ocr = PaddleOCR(
                        use_angle_cls=False,
                        lang='en',
                        show_log=False
                    )
                    self.log_message.emit(f"[OK] OCR 引擎初始化完成（已下载模型）")
                
                self.logger.info(f"OCR引擎初始化成功")
            except Exception as e:
                error_msg = f"OCR引擎初始化失败: {e}"
                self.logger.error(error_msg)
                self.finished.emit(False, error_msg, "")
                return
            
            # 初始化ROI跟踪器和异常检测器
            self.roi_tracker = ROITracker()
            
            # 从配置加载硬性延时阈值
            from src.config import ANOMALY_DETECTION
            hard_delay_max = ANOMALY_DETECTION.get('hard_delay_max_ms', 10000)
            self.anomaly_detector = AnomalyDetector(hard_delay_max_ms=hard_delay_max)
            
            self.log_message.emit(f"[OK] ROI跟踪器和异常检测器已初始化（硬性延时上限: {hard_delay_max}ms）")
            
            success, message, report_folder = self.analyze_video()
            self.logger.info(f"分析完成: success={success}, folder={report_folder}")
            self.finished.emit(success, message, report_folder)
        except Exception as e:
            import traceback
            error_msg = f"错误: {str(e)}\n{traceback.format_exc()}"
            self.logger.error(f"分析失败: {error_msg}")
            self.finished.emit(False, error_msg, "")
    
    def analyze_video(self):
        """分析视频"""
        video_path = Path(self.video_path)
        frame_step = self.frame_step
        
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
        
        # 显示分析范围
        if self.frame_limit == float('inf'):
            self.log_message.emit(f"FPS={fps:.2f}, 总帧数={total}, 全量分析")
            self.log_message.emit(f"抽帧间隔: 每{frame_step}帧，预计处理 {total // frame_step} 帧")
        else:
            self.log_message.emit(f"FPS={fps:.2f}, 总帧数={total}, 处理前{self.frame_limit}帧")
            self.log_message.emit(f"抽帧间隔: 每{frame_step}帧")
        
        results = []
        annotated_frames = []
        
        # 帧缓存（用于回溯重识别）
        # 格式：{frame_idx: {'frame': np.array, 'real_roi': tuple}}
        frame_cache = {}
        max_cache_size = 50  # 最多缓存50帧
        
        # 保存CSV（最后统一写入，因为可能有回溯修正）
        csv_path = report_dir / f"{report_folder_name}.csv"
        
        frame_idx = 0
        processed_count = 0
        
        while True:
                # 检查是否超过帧数限制
                if self.frame_limit != float('inf') and frame_idx > self.frame_limit:
                    break
                
                ret, frame = cap.read()
                if not ret:
                    break
                
                if frame_idx % frame_step != 0:
                    frame_idx += 1
                    continue
                
                # 更新进度
                if self.frame_limit != float('inf'):
                    self.progress.emit(frame_idx, int(self.frame_limit))
                else:
                    self.progress.emit(frame_idx, total)
                
                # ========== 时间识别 ==========
                # 1. 识别 T_app（应用内时间）
                if self.app_roi:
                    app_time_str, app_conf = detect_time_app(
                        frame=frame,
                        app_roi=self.app_roi,
                        ocr=self.ocr,
                        time_format='auto',
                        debug=False
                    )
                else:
                    app_time_str = None
                    app_conf = 0.0
                
                # 2. 识别 T_real（真实世界时间）
                real_roi, real_time_str, real_conf = detect_time_real_optimized(
                    frame=frame,
                    frame_idx=frame_idx,
                    roi_tracker=self.roi_tracker,
                    ocr=self.ocr,
                    exclude_roi=self.app_roi,
                    time_format='auto',
                    debug=False
                )
                
                # 缓存帧和ROI（用于可能的重识别）
                frame_cache[frame_idx] = {
                    'frame': frame.copy(),
                    'real_roi': real_roi,
                    'app_time_str': app_time_str,
                    'app_time_ms': None,  # 稍后填充
                    'real_time_str': real_time_str,
                    'real_time_ms': None   # 稍后填充
                }
                
                # 维护缓存大小
                if len(frame_cache) > max_cache_size:
                    oldest_idx = min(frame_cache.keys())
                    del frame_cache[oldest_idx]
                
                # 调试日志
                if frame_idx == 0 or frame_idx % 20 == 0:
                    self.logger.info(
                        f"帧{frame_idx}: T_app={app_time_str}(conf={app_conf:.2f}), "
                        f"T_real={real_time_str}(conf={real_conf:.2f})"
                    )
                
                # 计算延时
                video_time_s = frame_idx / fps if fps > 0 else None
                
                # 解析时间字符串为毫秒
                app_time_ms = parse_time_to_ms(app_time_str) if app_time_str else None
                real_time_ms = parse_time_to_ms(real_time_str) if real_time_str else None
                
                # 更新缓存
                frame_cache[frame_idx]['app_time_ms'] = app_time_ms
                frame_cache[frame_idx]['real_time_ms'] = real_time_ms
                
                # 计算延时
                delay_ms = None
                status = "ok"
                error_reason = ""
                need_recheck = False
                
                # 基本检查
                if app_time_ms is None:
                    status = "app_fail"
                    error_reason = "T_app识别失败"
                elif real_time_ms is None:
                    status = "real_fail"
                    error_reason = "T_real识别失败"
                else:
                    # 两者都识别成功，计算延迟
                    delay_ms = app_time_ms - real_time_ms
                    
                    # ========== 检测器A：跳变一致性检测 ==========
                    is_normal_a, reason_a, need_recheck = self.anomaly_detector.check_detector_a(
                        frame_idx, app_time_ms, real_time_ms, delay_ms
                    )
                    
                    if not is_normal_a and need_recheck:
                        # 跳变不一致 → 重新识别T_real
                        self.logger.info(f"帧{frame_idx}: 检测器A触发 - {reason_a}，重新识别T_real")
                        
                        _, real_time_str_recheck, real_conf_recheck = detect_time_real_optimized(
                            frame=frame,
                            frame_idx=frame_idx,
                            roi_tracker=self.roi_tracker,
                            ocr=self.ocr,
                            exclude_roi=self.app_roi,
                            time_format='auto',
                            debug=False
                        )
                        real_time_ms_recheck = parse_time_to_ms(real_time_str_recheck) if real_time_str_recheck else None
                        
                        if real_time_ms_recheck and real_time_ms_recheck != real_time_ms:
                            # 两次不一致 → 使用重识别值
                            self.logger.info(f"帧{frame_idx}: 重识别不一致，使用新值 {real_time_str_recheck}")
                            real_time_str = real_time_str_recheck
                            real_time_ms = real_time_ms_recheck
                            delay_ms = app_time_ms - real_time_ms
                            status = "ok_rechecked"
                            error_reason = f"重识别修正({reason_a})"
                        else:
                            # 两次一致 → 识别稳定可靠，直接标记为ok
                            self.logger.info(f"帧{frame_idx}: 重识别一致，识别稳定可靠")
                            status = "ok"
                            error_reason = ""
                    
                    elif not is_normal_a:
                        # 硬性错误（如delay超限）
                        status = "wrong"
                        error_reason = reason_a
                        self.logger.warning(f"帧{frame_idx}: 检测器A判定异常 - {reason_a}")
                    
                    else:
                        # 检测器A通过
                        status = "ok"
                        self.anomaly_detector.add_normal_delay(delay_ms)
                        
                        # 统计检测（保留兼容性）
                        if frame_idx % 30 == 0 and frame_idx > 0:
                            is_stat_normal, stat_reason, z_score = self.anomaly_detector.check_statistical(delay_ms)
                            if not is_stat_normal:
                                status = "wrong"
                                error_reason = stat_reason
                                self.logger.warning(f"帧{frame_idx}: 统计异常 - {stat_reason}")
                    
                    # ========== 检测器B：回退检测（检查所有正常帧，只和前2帧比对）==========
                    if status in ["ok", "ok_rechecked"]:
                        # 先检查回退
                        is_normal_b, reason_b = self.anomaly_detector.check_detector_b(frame_idx, real_time_ms)
                        
                        if not is_normal_b:
                            # 回退检测不通过
                            status = "wrong"
                            error_reason = reason_b
                            self.logger.warning(f"帧{frame_idx}: 检测器B判定异常 - {reason_b}")
                        else:
                            # 回退检测通过，更新帧信息
                            self.anomaly_detector.update_frame(frame_idx, app_time_ms, real_time_ms)
                
                # 收集数据（用于HTML报告）
                results.append({
                    'frame_idx': frame_idx,
                    'video_time_s': video_time_s,
                    'app_time_str': app_time_str,
                    'app_time_ms': app_time_ms,
                    'real_time_str': real_time_str,
                    'delay_ms': delay_ms,
                    'status': status,
                    'error_reason': error_reason
                })
                
                # 绘制标定图
                annotated = frame.copy()
                
                # 绘制 T_app ROI
                if self.app_roi:
                    x1, y1, x2, y2 = self.app_roi
                    color = (0, 255, 0) if status == "ok" else (0, 0, 255)
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                    label = f"T_app: {app_time_str}" if app_time_str else "T_app: N/A"
                    cv2.putText(annotated, label, (x1, y1 - 10),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                
                # 绘制 T_real ROI
                if real_roi:
                    x1, y1, x2, y2 = real_roi
                    color = (0, 255, 0) if status == "ok" else (0, 0, 255)
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                    label = f"T_real: {real_time_str}" if real_time_str else "T_real: N/A"
                    cv2.putText(annotated, label, (x1, y1 - 10),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                
                # 显示延时
                if delay_ms is not None:
                    cv2.putText(annotated, f"Delay: {delay_ms}ms", (10, 30),
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
        
        # ========== 统一写入CSV（支持回溯修正） ==========
        self.log_message.emit("正在写入CSV...")
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "video_name", "frame_idx", "video_time_s",
                "app_time_str", "app_time_ms",
                "real_time_str", "real_time_ms",
                "delay_ms", "status", "error_reason"
            ])
            
            for result in results:
                writer.writerow([
                    video_path.name,
                    result['frame_idx'],
                    f"{result['video_time_s']:.6f}" if result['video_time_s'] is not None else "",
                    result.get('app_time_str', '') or "",
                    result.get('app_time_ms', '') or "",
                    result.get('real_time_str', '') or "",
                    result.get('real_time_ms', '') or "",
                    result.get('delay_ms', '') if result.get('delay_ms') is not None else "",
                    result.get('status', ''),
                    result.get('error_reason', '')
                ])
        
        self.log_message.emit("CSV报告已保存: " + csv_path.name)
        self.logger.info(f"CSV已保存: {csv_path}")
        
        # 处理网络日志匹配
        merged_csv_path = None
        if self.phone_log or self.pc_log:
            self.log_message.emit("正在匹配网络日志...")
            self.logger.info("开始网络数据匹配")
            try:
                from src.core.network_matcher import match_network_logs
                
                merged_csv_path = report_dir / f"{report_folder_name}_with_network.csv"
                match_network_logs(
                    video_csv=str(csv_path),
                    phone_csv=self.phone_log,
                    pc_csv=self.pc_log,
                    output_csv=str(merged_csv_path),
                    tolerance=1.0
                )
                
                self.log_message.emit(f"网络数据匹配完成: {merged_csv_path.name}")
                self.logger.info(f"网络数据已匹配: {merged_csv_path}")
            except Exception as e:
                self.log_message.emit(f"⚠️ 网络数据匹配失败: {str(e)}")
                self.logger.error(f"网络匹配失败: {e}")
                merged_csv_path = None
        
        # 生成标定视频
        self.log_message.emit("正在生成标定视频...")
        self.logger.info(f"开始生成标定视频，annotated_frames数量: {len(annotated_frames)}")
        
        video_out_path = report_dir / f"{report_folder_name}.mp4"
        if annotated_frames:
            h, w = annotated_frames[0].shape[:2]
            self.log_message.emit(f"视频尺寸: {w}x{h}, FPS: {fps / frame_step:.2f}")
            self.logger.info(f"视频参数: size={w}x{h}, fps={fps / frame_step:.2f}")
            
            # 尝试多个编码器（优先使用最兼容的）
            codecs = [
                ('mp4v', 'MPEG-4 (最兼容)'),
                ('avc1', 'H.264 (avc1)'),
                ('H264', 'H.264 (H264)'),
                ('X264', 'H.264 (X264)'),
                ('XVID', 'XVID'),
            ]
            
            out = None
            for codec_name, codec_desc in codecs:
                self.logger.info(f"尝试编码器: {codec_desc}")
                fourcc = cv2.VideoWriter_fourcc(*codec_name)
                out = cv2.VideoWriter(str(video_out_path), fourcc, fps / frame_step, (w, h))
                
                if out.isOpened():
                    self.log_message.emit(f"[OK] 使用编码器: {codec_desc}")
                    self.logger.info(f"编码器 {codec_desc} 成功")
                    break
                else:
                    out.release()
            
            if not out or not out.isOpened():
                error_msg = "所有视频编码器都无法使用！"
                self.log_message.emit(f"[ERROR] {error_msg}")
                self.logger.error(error_msg)
            else:
                for ann_frame in annotated_frames:
                    out.write(ann_frame)
                out.release()
                
                if video_out_path.exists():
                    size = video_out_path.stat().st_size
                    self.log_message.emit(f"[OK] 标定视频已保存: {video_out_path.name} ({size/1024:.2f} KB)")
                    self.logger.info(f"视频文件已生成: size={size} bytes")
                    
                    # 可选：使用FFmpeg重新编码（如果可用）
                    try:
                        import subprocess
                        import shutil
                        import sys
                        
                        # 查找ffmpeg路径（支持打包后的exe）
                        ffmpeg_path = None
                        
                        # 1. 检查打包后的内置ffmpeg
                        if getattr(sys, 'frozen', False):
                            base_path = Path(sys._MEIPASS)
                            bundled_ffmpeg = base_path / "ffmpeg" / "ffmpeg.exe"
                            if bundled_ffmpeg.exists():
                                ffmpeg_path = str(bundled_ffmpeg)
                                self.logger.info(f"使用内置ffmpeg: {ffmpeg_path}")
                        
                        # 2. 检查系统PATH中的ffmpeg
                        if not ffmpeg_path:
                            system_ffmpeg = shutil.which('ffmpeg')
                            if system_ffmpeg:
                                ffmpeg_path = system_ffmpeg
                                self.logger.info(f"使用系统ffmpeg: {ffmpeg_path}")
                        
                        if ffmpeg_path:
                            self.log_message.emit("正在转换视频为浏览器兼容格式...")
                            self.logger.info("开始FFmpeg重新编码为H.264")
                            
                            temp_video = video_out_path.with_suffix('.temp.mp4')
                            video_out_path.rename(temp_video)
                            
                            # 使用FFmpeg重新编码为H.264
                            cmd = [
                                ffmpeg_path,
                                '-i', str(temp_video),
                                '-c:v', 'libx264',  # 使用H.264编码器
                                '-preset', 'fast',  # 快速编码
                                '-crf', '23',  # 质量参数（18-28，数字越小质量越高）
                                '-pix_fmt', 'yuv420p',  # 确保像素格式兼容
                                '-y',  # 覆盖输出文件
                                str(video_out_path)
                            ]
                            
                            result = subprocess.run(
                                cmd,
                                capture_output=True,
                                text=True,
                                encoding='utf-8',
                                errors='ignore',
                                timeout=300  # 5分钟超时
                            )
                            
                            if result.returncode == 0 and video_out_path.exists():
                                new_size = video_out_path.stat().st_size
                                self.log_message.emit(f"[OK] 视频已转换为H.264格式 ({new_size/1024:.2f} KB)")
                                self.logger.info(f"FFmpeg转码成功: {new_size} bytes")
                                # 删除临时文件
                                temp_video.unlink()
                            else:
                                self.log_message.emit(f"[WARNING] FFmpeg转码失败，保留原始视频")
                                self.logger.warning(f"FFmpeg转码失败: {result.stderr if result else 'unknown'}")
                                # 恢复原始文件
                                if temp_video.exists():
                                    temp_video.rename(video_out_path)
                        else:
                            self.log_message.emit("[INFO] FFmpeg未安装，跳过视频转码")
                            self.logger.info("FFmpeg不可用，跳过转码")
                    except Exception as e:
                        self.log_message.emit(f"[WARNING] 视频转码出错: {str(e)}，保留原始视频")
                        self.logger.warning(f"FFmpeg转码异常: {e}")
                        # 恢复原始文件
                        try:
                            if 'temp_video' in locals() and temp_video.exists():
                                temp_video.rename(video_out_path)
                        except:
                            pass
                else:
                    self.log_message.emit(f"[ERROR] 错误: 视频文件未创建！")
                    self.logger.error(f"视频文件不存在: {video_out_path}")
        else:
            self.log_message.emit("[ERROR] 错误: annotated_frames 为空")
            self.logger.error("annotated_frames为空")
        
        # 生成HTML报告
        self.log_message.emit("正在生成 HTML 报告...")
        self.logger.info("开始生成HTML报告")
        from src.core.report_generator import ReportGenerator
        html_path = report_dir / f"{report_folder_name}.html"
        ReportGenerator.generate_html(
            results=results,
            video_filename=f"{report_folder_name}.mp4",
            fps=fps,
            frame_step=frame_step,
            output_path=str(html_path),
            network_csv=str(merged_csv_path) if merged_csv_path else None
        )
        self.log_message.emit("HTML报告已保存: " + html_path.name)
        self.logger.info(f"HTML报告已保存: {html_path}")
        
        # 复制本次分析日志到报告文件夹
        self.log_message.emit("正在保存日志...")
        try:
            from src.utils.logger import get_log_file
            import shutil
            
            current_log = get_log_file()
            if current_log and current_log.exists():
                analysis_log = report_dir / "analysis.log"
                shutil.copy2(current_log, analysis_log)
                self.log_message.emit(f"[OK] 分析日志已保存: {analysis_log.name}")
                self.logger.info(f"日志已复制到报告目录: {analysis_log}")
            else:
                self.logger.warning("无法获取当前日志文件，跳过日志复制")
        except Exception as e:
            self.logger.error(f"复制日志失败: {e}")
            # 不影响主流程，继续
        
        self.logger.info(f"分析完成！报告文件夹: {report_dir}")
        return True, f"分析完成！\n报告文件夹: {report_dir}", str(report_dir)
