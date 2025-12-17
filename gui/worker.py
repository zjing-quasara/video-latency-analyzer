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
from utils.logger import get_logger


class AnalysisWorker(QThread):
    """视频分析后台线程 - 使用temp_delay_gui.py中验证过的实现"""
    
    progress = pyqtSignal(int, int)
    log_message = pyqtSignal(str)
    finished = pyqtSignal(bool, str, str)
    
    def __init__(self, video_path, app_roi, use_gpu, resize_ratio, frame_limit, frame_step, treal_format, output_dir=None, phone_log=None, pc_log=None):
        super().__init__()
        self.logger = get_logger('AnalysisWorker')
        self.video_path = video_path
        self.app_roi = app_roi
        self.use_gpu = use_gpu
        self.resize_ratio = resize_ratio
        self.frame_limit = frame_limit
        self.frame_step = frame_step
        self.treal_format = treal_format  # 'standard' 或 'digits'
        self.output_dir = Path(output_dir) if output_dir else Path.home() / "Desktop" / "视频延时分析"
        self.phone_log = phone_log  # 手机网络日志路径
        self.pc_log = pc_log  # 电脑网络日志路径
        self.ocr_engine = None
        
        self.logger.info(f"分析worker已创建: video={Path(video_path).name}, gpu={use_gpu}, ratio={resize_ratio}, limit={frame_limit}, step={frame_step}, format={treal_format}, phone_log={phone_log is not None}, pc_log={pc_log is not None}")
    
    def run(self):
        try:
            self.logger.info("开始视频分析任务")
            
            # 初始化OCR
            import os
            gpu_mode = '0' if self.use_gpu else '-1'
            os.environ['CUDA_VISIBLE_DEVICES'] = gpu_mode
            self.logger.info(f"OCR GPU模式: {'启用' if self.use_gpu else '禁用'} (CUDA_VISIBLE_DEVICES={gpu_mode})")
            
            self.ocr_engine = PaddleOCR(lang="en")
            self.log_message.emit("PaddleOCR 初始化完成")
            self.logger.info("PaddleOCR 初始化成功")
            
            success, message, report_folder = self.analyze_video()
            self.logger.info(f"分析完成: success={success}, folder={report_folder}")
            self.finished.emit(success, message, report_folder)
        except Exception as e:
            import traceback
            error_msg = f"错误: {str(e)}\n{traceback.format_exc()}"
            self.logger.error(f"分析失败: {error_msg}")
            self.finished.emit(False, error_msg, "")
    
    def detect_real_time_roi(self, frame):
        """动态检测 T_real（改进版，支持泛红屏幕）"""
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # 尝试多个阈值，找到最佳的
        thresholds = [30, 50, 70, 90]
        all_candidates = []
        
        for thresh in thresholds:
            _, th = cv2.threshold(gray, thresh, 255, cv2.THRESH_BINARY_INV)
            contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for cnt in contours:
                x, y, w_box, h_box = cv2.boundingRect(cnt)
                area = w_box * h_box
                
                # 面积筛选
                if area < 0.05 * w * h or area > 0.5 * w * h:
                    continue
                
                # 宽高比筛选
                ratio = w_box / (h_box + 1e-6)
                if ratio < 2.0 or ratio > 6.0:
                    continue
                
                candidate_roi = (x, y, x + w_box, y + h_box)
                
                # 计算得分（面积越大，优先级越高）
                score = area
                all_candidates.append({
                    'roi': candidate_roi,
                    'area': area,
                    'score': score,
                    'threshold': thresh
                })
        
        # 选择得分最高的候选
        if all_candidates:
            best = max(all_candidates, key=lambda c: c['score'])
            return best['roi']
        
        return None
    
    def extract_time_from_roi(self, frame, roi, exclude_roi=None):
        """
        从 ROI 提取时间
        exclude_roi: 要排除的区域（用于避免读取重叠的T_app内容）
        """
        if not roi:
            return None
        
        x1, y1, x2, y2 = roi
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        
        roi_img = frame[y1:y2, x1:x2].copy()  # copy防止修改原图
        if roi_img.size == 0:
            return None
        
        # 如果有需要排除的区域（T_app），把它涂黑
        if exclude_roi:
            ex1, ey1, ex2, ey2 = exclude_roi
            # 转换为roi_img的相对坐标
            rel_x1 = max(0, ex1 - x1)
            rel_y1 = max(0, ey1 - y1)
            rel_x2 = min(roi_img.shape[1], ex2 - x1)
            rel_y2 = min(roi_img.shape[0], ey2 - y1)
            
            # 检查是否有重叠
            if rel_x1 < rel_x2 and rel_y1 < rel_y2:
                # 把T_app区域涂黑（避免OCR读到）
                roi_img[rel_y1:rel_y2, rel_x1:rel_x2] = 0
                self.logger.debug(f"排除T_app区域: ({rel_x1},{rel_y1})-({rel_x2},{rel_y2})")
        
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
            
            # 格式1: 标准时间格式 HH:MM:SS.mmm
            time_pattern = re.compile(r"\d{2}:\d{2}:\d{2}[.:]\d{1,3}")
            for txt in texts:
                filtered = "".join(ch for ch in txt if ch in "0123456789:.")
                m = time_pattern.search(filtered)
                if m:
                    return m.group(0)
            
            # 格式2: 纯数字格式（如图片所示: 161213185）
            # 只在用户选择了纯数字格式时才尝试
            if self.treal_format == "digits":
                all_text = "".join(texts)
                digits = "".join(ch for ch in all_text if ch.isdigit())
                
                # 至少6位数字（HHMMSS）
                if len(digits) >= 6:
                    self.logger.debug(f"检测到纯数字: {digits}, 原始文本: {texts}")
                    return digits
            
        except Exception as e:
            self.logger.debug(f"OCR异常: {e}")
            pass
        
        return None
    
    def parse_time_to_ms(self, time_str):
        """时间字符串转毫秒（支持多种格式）"""
        if not time_str:
            return None
        
        try:
            # 格式1: HH:MM:SS.mmm 或 HH:MM:SS:mmm
            if ":" in time_str:
                if "." in time_str:
                    hms, ms_part = time_str.split(".")
                else:
                    hms, ms_part = time_str, "0"
                h, m, s = map(int, hms.split(":"))
                ms = int(ms_part.ljust(3, "0")[:3])
                return ((h * 3600 + m * 60 + s) * 1000) + ms
            
            # 格式2: 纯数字（HHMMSSMMM 或 HHMMSS）
            digits = "".join(ch for ch in time_str if ch.isdigit())
            
            if len(digits) >= 6:
                h = int(digits[0:2])
                m = int(digits[2:4])
                s = int(digits[4:6])
                ms = int(digits[6:9]) if len(digits) >= 9 else 0
                
                # 验证合法性
                if 0 <= h < 24 and 0 <= m < 60 and 0 <= s < 60 and 0 <= ms < 1000:
                    return ((h * 3600 + m * 60 + s) * 1000) + ms
            
            return None
        except Exception:
            return None
    
    def format_time_display(self, time_str):
        """格式化时间显示（纯数字转为标准格式）"""
        if not time_str:
            return None
        
        # 如果已经是标准格式，直接返回
        if ":" in time_str:
            return time_str
        
        # 纯数字格式，转换为 HH:MM:SS.mmm
        digits = "".join(ch for ch in time_str if ch.isdigit())
        if len(digits) >= 6:
            h = digits[0:2]
            m = digits[2:4]
            s = digits[4:6]
            ms = digits[6:9] if len(digits) >= 9 else "000"
            return f"{h}:{m}:{s}.{ms}"
        
        return time_str
    
    def analyze_video(self):
        """分析视频 - 直接复制自temp_delay_gui.py"""
        video_path = Path(self.video_path)
        frame_step = self.frame_step  # 使用用户设置的抽帧间隔
        
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
            self.log_message.emit(f"FPS={fps:.2f}, 总帧数={total}, 全量分析（整个视频）")
            self.log_message.emit(f"抽帧间隔: 每{frame_step}帧，预计处理 {total // frame_step} 帧")
        else:
            self.log_message.emit(f"FPS={fps:.2f}, 总帧数={total}, 处理前{self.frame_limit}帧")
            self.log_message.emit(f"抽帧间隔: 每{frame_step}帧")
        
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
            
            # 时间单调性验证
            last_app_time_ms = None
            last_real_time_ms = None
            
            # 记住上次成功的T_real ROI位置（优先使用，失败时重新检测）
            last_successful_real_roi = None
            
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
                    # 全量分析显示当前帧数
                    self.progress.emit(frame_idx, total)
                
                # 检测和识别 - 智能策略
                # 1. 优先使用上次成功的ROI位置
                if last_successful_real_roi:
                    real_time_str_temp = self.extract_time_from_roi(frame, last_successful_real_roi, exclude_roi=self.app_roi)
                    if real_time_str_temp:
                        # 在上次位置成功识别到时间
                        real_roi = last_successful_real_roi
                        real_time_str = real_time_str_temp
                    else:
                        # 在上次位置识别失败，重新检测
                        real_roi = self.detect_real_time_roi(frame)
                        real_time_str = self.extract_time_from_roi(frame, real_roi, exclude_roi=self.app_roi) if real_roi else None
                else:
                    # 首次或之前一直失败，直接检测
                    real_roi = self.detect_real_time_roi(frame)
                    real_time_str = self.extract_time_from_roi(frame, real_roi, exclude_roi=self.app_roi) if real_roi else None
                
                # 更新成功的ROI位置
                if real_time_str and real_roi:
                    last_successful_real_roi = real_roi
                
                # 记录检测状态
                if real_roi:
                    self.logger.debug(f"帧 {frame_idx}: T_real ROI={real_roi}, 识别={'成功' if real_time_str else '失败'}")
                else:
                    self.logger.warning(f"帧 {frame_idx}: T_real ROI检测失败")
                
                # 调试：保存第一帧和失败帧的检测结果
                if frame_idx == 0 or (frame_idx <= 100 and real_roi is None and processed_count <= 3):
                    # 保存原图+ROI标记
                    debug_frame = frame.copy()
                    if real_roi:
                        x1, y1, x2, y2 = real_roi
                        cv2.rectangle(debug_frame, (x1, y1), (x2, y2), (0, 255, 0), 3)
                        cv2.putText(debug_frame, "T_real ROI (auto)", (x1, y1-10),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                    else:
                        cv2.putText(debug_frame, f"Frame {frame_idx}: T_real NOT FOUND", (10, 60),
                                   cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 3)
                    
                    if self.app_roi:
                        x1, y1, x2, y2 = self.app_roi
                        cv2.rectangle(debug_frame, (x1, y1), (x2, y2), (255, 0, 0), 3)
                        cv2.putText(debug_frame, "T_app ROI (manual)", (x1, y1-10),
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)
                    
                    debug_path = report_dir / f"debug_frame_{frame_idx}.png"
                    cv2.imwrite(str(debug_path), debug_frame)
                    
                    # 只在第一帧保存阈值图
                    if frame_idx == 0:
                        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                        cv2.imwrite(str(report_dir / "debug_gray.png"), gray)
                        
                        for thresh in [30, 50, 70, 90]:
                            _, th = cv2.threshold(gray, thresh, 255, cv2.THRESH_BINARY_INV)
                            cv2.imwrite(str(report_dir / f"debug_threshold_{thresh}.png"), th)
                        
                        self.log_message.emit(f"调试图已保存到报告文件夹")
                
                app_time_str = self.extract_time_from_roi(frame, self.app_roi)
                # real_time_str 已在上面获取
                
                # 格式化显示（纯数字转为标准格式）
                app_time_str_display = self.format_time_display(app_time_str) if app_time_str else None
                real_time_str_display = self.format_time_display(real_time_str) if real_time_str else None
                
                # 计算延时
                video_time_s = frame_idx / fps if fps > 0 else None
                app_time_ms = self.parse_time_to_ms(app_time_str) if app_time_str else None
                real_time_ms = self.parse_time_to_ms(real_time_str) if real_time_str else None
                
                # 保存原始识别结果（用于显示）
                if not app_time_str_display:
                    app_time_str_display = app_time_str
                if not real_time_str_display:
                    real_time_str_display = real_time_str
                
                # 时间单调性验证标记
                app_time_wrong = False
                real_time_wrong = False
                
                if app_time_ms is not None and last_app_time_ms is not None:
                    if app_time_ms < last_app_time_ms:
                        self.log_message.emit(
                            f"⚠️ 帧 {frame_idx}: T_app时间倒退 ({app_time_str} < 上一帧)，标记为(wrong)"
                        )
                        app_time_wrong = True
                        app_time_str_display = f"{app_time_str} (wrong)"
                        # 不用于延时计算，但保留显示
                        app_time_ms = None
                
                if real_time_ms is not None and last_real_time_ms is not None:
                    if real_time_ms < last_real_time_ms:
                        self.log_message.emit(
                            f"⚠️ 帧 {frame_idx}: T_real时间倒退 ({real_time_str} < 上一帧)，标记为(wrong)"
                        )
                        real_time_wrong = True
                        real_time_str_display = f"{real_time_str} (wrong)"
                        # 不用于延时计算，但保留显示
                        real_time_ms = None
                
                # 更新上一帧时间戳（只有正确的才更新）
                if app_time_ms is not None and not app_time_wrong:
                    last_app_time_ms = app_time_ms
                if real_time_ms is not None and not real_time_wrong:
                    last_real_time_ms = real_time_ms
                
                delay_ms = None
                status = "ok"
                if app_time_ms is None:
                    status = "app_fail"
                if real_time_ms is None:
                    status = "real_fail" if status == "ok" else "both_fail"
                if app_time_ms is not None and real_time_ms is not None:
                    delay_ms = app_time_ms - real_time_ms
                
                # 保存到 CSV（使用带标记的显示值）
                writer.writerow([
                    video_path.name, frame_idx,
                    f"{video_time_s:.6f}" if video_time_s is not None else "",
                    app_time_str_display or "", app_time_ms or "",
                    real_time_str_display or "", real_time_ms or "",
                    delay_ms if delay_ms is not None else "", status
                ])
                
                # 收集数据（使用带标记的显示值）
                results.append({
                    'frame_idx': frame_idx,
                    'video_time_s': video_time_s,
                    'app_time_str': app_time_str_display,
                    'real_time_str': real_time_str_display,
                    'delay_ms': delay_ms,
                    'status': status,
                    'app_time_wrong': app_time_wrong,
                    'real_time_wrong': real_time_wrong
                })
                
                # 绘制标定图
                annotated = frame.copy()
                if self.app_roi:
                    x1, y1, x2, y2 = self.app_roi
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (255, 0, 0), 2)
                    label = f"T_app: {app_time_str_display}" if app_time_str_display else "T_app: N/A"
                    cv2.putText(annotated, label, (x1, y1 - 10),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
                
                if real_roi:
                    x1, y1, x2, y2 = real_roi
                    # 如果时间错误，用红色框标记
                    color = (0, 0, 255) if real_time_wrong else (0, 255, 0)
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                    label = f"T_real: {real_time_str_display}" if real_time_str_display else "T_real: N/A"
                    cv2.putText(annotated, label, (x1, y1 - 10),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                
                if delay_ms is not None:
                    delay_text = f"Delay: {delay_ms}ms"
                    cv2.putText(annotated, delay_text, (10, 30),
                               cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
                elif real_time_wrong or app_time_wrong:
                    # 显示错误标记
                    error_text = "OCR Error (wrong)"
                    cv2.putText(annotated, error_text, (10, 30),
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
        self.logger.info(f"CSV已保存: {csv_path}")
        
        # 处理网络日志匹配
        merged_csv_path = None
        if self.phone_log or self.pc_log:
            self.log_message.emit("正在匹配网络日志...")
            self.logger.info("开始网络数据匹配")
            try:
                from core.network_matcher import match_network_logs
                
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
        
        # 生成标定视频 - 完全复制temp_delay_gui.py的实现
        self.log_message.emit("正在生成标定视频...")
        self.logger.info(f"开始生成标定视频，annotated_frames数量: {len(annotated_frames)}")
        self.log_message.emit(f"annotated_frames 数量: {len(annotated_frames)}")
        
        video_out_path = report_dir / f"{report_folder_name}.mp4"
        if annotated_frames:
            h, w = annotated_frames[0].shape[:2]
            self.log_message.emit(f"视频尺寸: {w}x{h}, FPS: {fps / frame_step:.2f}")
            self.logger.info(f"视频参数: size={w}x{h}, fps={fps / frame_step:.2f}")
            
            # 尝试多个编码器
            codecs = [
                ('avc1', 'H.264 (avc1)'),
                ('H264', 'H.264 (H264)'),
                ('X264', 'H.264 (X264)'),
                ('mp4v', 'MPEG-4'),
                ('XVID', 'XVID'),
            ]
            
            out = None
            used_codec = None
            
            for codec_name, codec_desc in codecs:
                self.logger.info(f"尝试编码器: {codec_desc}")
                fourcc = cv2.VideoWriter_fourcc(*codec_name)
                out = cv2.VideoWriter(str(video_out_path), fourcc, fps / frame_step, (w, h))
                
                if out.isOpened():
                    used_codec = codec_desc
                    self.log_message.emit(f"✓ 使用编码器: {codec_desc}")
                    self.logger.info(f"编码器 {codec_desc} 成功打开")
                    break
                else:
                    self.logger.warning(f"编码器 {codec_desc} 打开失败")
                    out.release()
            
            if not out or not out.isOpened():
                error_msg = "所有视频编码器都无法使用！"
                self.log_message.emit(f"✗ {error_msg}")
                self.logger.error(error_msg)
            else:
                self.log_message.emit(f"保存路径: {video_out_path}")
                self.logger.info(f"VideoWriter路径: {video_out_path}")
                
                for ann_frame in annotated_frames:
                    out.write(ann_frame)
                out.release()
                self.log_message.emit("VideoWriter.release() 完成")
                self.logger.info("VideoWriter已释放")
                
                if video_out_path.exists():
                    size = video_out_path.stat().st_size
                    self.log_message.emit(f"✓ 标定视频已保存: {video_out_path.name} ({size/1024:.2f} KB)")
                    self.logger.info(f"视频文件已生成: size={size} bytes")
                    
                    # 如果使用的不是H.264，尝试用ffmpeg转换
                    if used_codec and 'H.264' not in used_codec:
                        self.log_message.emit(f"检测到使用非H.264编码({used_codec})，尝试转换为浏览器兼容格式...")
                        self.logger.info(f"尝试使用ffmpeg转换视频")
                        
                        try:
                            import subprocess
                            temp_path = video_out_path.parent / f"temp_{video_out_path.name}"
                            
                            # 使用ffmpeg转换为H.264
                            cmd = [
                                'ffmpeg', '-y', '-i', str(video_out_path),
                                '-c:v', 'libx264', '-preset', 'fast',
                                '-crf', '23', str(temp_path)
                            ]
                            
                            result = subprocess.run(
                                cmd, 
                                capture_output=True, 
                                timeout=60,
                                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
                            )
                            
                            if result.returncode == 0 and temp_path.exists():
                                # 替换原文件
                                video_out_path.unlink()
                                temp_path.rename(video_out_path)
                                new_size = video_out_path.stat().st_size
                                self.log_message.emit(f"✓ 视频已转换为H.264格式 ({new_size/1024:.2f} KB)")
                                self.logger.info(f"ffmpeg转换成功: {new_size} bytes")
                            else:
                                self.log_message.emit(f"⚠️ ffmpeg转换失败，使用原始视频")
                                self.logger.warning(f"ffmpeg转换失败: {result.stderr.decode('utf-8', errors='ignore')}")
                                if temp_path.exists():
                                    temp_path.unlink()
                        except FileNotFoundError:
                            self.log_message.emit(f"⚠️ 未找到ffmpeg，使用原始视频（浏览器可能无法播放）")
                            self.logger.warning("ffmpeg未安装")
                        except subprocess.TimeoutExpired:
                            self.log_message.emit(f"⚠️ ffmpeg转换超时，使用原始视频")
                            self.logger.warning("ffmpeg转换超时")
                        except Exception as e:
                            self.log_message.emit(f"⚠️ ffmpeg转换失败: {str(e)}")
                            self.logger.error(f"ffmpeg转换异常: {e}")
                else:
                    self.log_message.emit(f"✗ 错误: 视频文件未创建！")
                    self.logger.error(f"视频文件不存在: {video_out_path}")
        else:
            self.log_message.emit("✗ 错误: annotated_frames 为空，跳过视频生成")
            self.logger.error("annotated_frames为空")
        
        # 生成HTML报告
        self.log_message.emit("正在生成 HTML 报告...")
        self.logger.info("开始生成HTML报告")
        from core.report_generator import ReportGenerator
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
        
        self.logger.info(f"分析完成！报告文件夹: {report_dir}")
        return True, f"分析完成！\n报告文件夹: {report_dir}", str(report_dir)

