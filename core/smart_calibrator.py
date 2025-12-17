"""
智能校准管理器 - 自动学习最佳识别参数
"""
import cv2
import numpy as np
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from collections import defaultdict


@dataclass
class CalibrationResult:
    """校准结果"""
    app_strategy: str  # T_app 最佳策略
    real_strategy: str  # T_real 最佳策略
    app_confidence: float  # T_app 平均置信度
    real_confidence: float  # T_real 平均置信度
    success_rate: float  # 总体成功率
    calibration_frames: int  # 校准使用的帧数


class SmartCalibrator:
    """智能校准器 - 自动寻找最佳识别参数"""
    
    def __init__(self, ocr_engine, logger=None):
        """
        初始化智能校准器
        
        Args:
            ocr_engine: 自适应OCR引擎实例
            logger: 日志记录器
        """
        self.ocr_engine = ocr_engine
        self.logger = logger
        
        # 校准状态
        self.is_calibrated = False
        self.calibration_result = None
        
        # 运行时统计
        self.app_success_count = 0
        self.real_success_count = 0
        self.total_frames = 0
        
    def _log(self, level: str, msg: str):
        """内部日志"""
        if self.logger:
            if level == 'debug':
                self.logger.debug(msg)
            elif level == 'info':
                self.logger.info(msg)
            elif level == 'warning':
                self.logger.warning(msg)
    
    def calibrate(self, video_path: str, app_roi: Tuple, max_frames: int = 10) -> CalibrationResult:
        """
        自动校准 - 使用前N帧找到最佳识别参数
        
        Args:
            video_path: 视频路径
            app_roi: T_app 区域 (x1, y1, x2, y2)
            max_frames: 最多使用多少帧进行校准（默认10帧）
            
        Returns:
            校准结果
        """
        self._log('info', f"=" * 60)
        self._log('info', f"🔧 开始智能校准 - 使用前 {max_frames} 帧自动寻找最佳参数")
        self._log('info', f"=" * 60)
        
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise Exception("无法打开视频文件")
        
        total_frames_in_video = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        
        self._log('info', f"视频信息: {total_frames_in_video} 帧, {fps:.2f} fps")
        
        # 智能选择校准帧（均匀分布）
        calibration_frames = self._select_calibration_frames(total_frames_in_video, max_frames)
        self._log('info', f"校准帧索引: {calibration_frames}")
        
        # 收集识别结果
        app_results = defaultdict(lambda: {'success': 0, 'confidence': []})
        real_results = defaultdict(lambda: {'success': 0, 'confidence': []})
        
        for frame_idx in calibration_frames:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                continue
            
            self._log('info', f"校准帧 {frame_idx}...")
            
            # 测试 T_app 识别（固定区域）
            if app_roi:
                x1, y1, x2, y2 = app_roi
                app_img = frame[y1:y2, x1:x2].copy()
                
                # 尝试所有策略
                for strategy in ['original', 'contrast', 'sharpen', 'grayscale', 
                               'binary', 'binary_inv', 'denoise']:
                    result = self._test_strategy(app_img, strategy, 'T_app')
                    if result:
                        app_results[strategy]['success'] += 1
                        app_results[strategy]['confidence'].append(result['confidence'])
            
            # 测试 T_real 识别（自动检测区域）
            real_roi = self._quick_detect_real_roi(frame)
            if real_roi:
                x1, y1, x2, y2 = real_roi
                real_img = frame[y1:y2, x1:x2].copy()
                
                for strategy in ['original', 'contrast', 'sharpen', 'grayscale',
                               'binary', 'binary_inv', 'denoise']:
                    result = self._test_strategy(real_img, strategy, 'T_real')
                    if result:
                        real_results[strategy]['success'] += 1
                        real_results[strategy]['confidence'].append(result['confidence'])
        
        cap.release()
        
        # 分析结果，选择最佳策略
        best_app_strategy = self._select_best_strategy(app_results, 'T_app')
        best_real_strategy = self._select_best_strategy(real_results, 'T_real')
        
        # 计算成功率
        app_success_rate = app_results[best_app_strategy]['success'] / len(calibration_frames) if best_app_strategy else 0
        real_success_rate = real_results[best_real_strategy]['success'] / len(calibration_frames) if best_real_strategy else 0
        
        # 计算平均置信度
        app_conf = np.mean(app_results[best_app_strategy]['confidence']) if best_app_strategy and app_results[best_app_strategy]['confidence'] else 0
        real_conf = np.mean(real_results[best_real_strategy]['confidence']) if best_real_strategy and real_results[best_real_strategy]['confidence'] else 0
        
        overall_success = (app_success_rate + real_success_rate) / 2
        
        # 创建校准结果
        self.calibration_result = CalibrationResult(
            app_strategy=best_app_strategy or 'contrast',
            real_strategy=best_real_strategy or 'contrast',
            app_confidence=app_conf,
            real_confidence=real_conf,
            success_rate=overall_success,
            calibration_frames=len(calibration_frames)
        )
        
        self.is_calibrated = True
        
        # 输出校准报告
        self._log('info', f"=" * 60)
        self._log('info', f"✅ 校准完成！")
        self._log('info', f"=" * 60)
        self._log('info', f"📊 T_app 最佳策略: {self.calibration_result.app_strategy} "
                         f"(成功率: {app_success_rate:.1%}, 置信度: {app_conf:.2f})")
        self._log('info', f"📊 T_real 最佳策略: {self.calibration_result.real_strategy} "
                         f"(成功率: {real_success_rate:.1%}, 置信度: {real_conf:.2f})")
        self._log('info', f"📊 总体成功率: {overall_success:.1%}")
        self._log('info', f"=" * 60)
        
        # 将最佳策略设置到OCR引擎
        self.ocr_engine.best_strategy = self.calibration_result.app_strategy
        
        return self.calibration_result
    
    def _select_calibration_frames(self, total_frames: int, max_frames: int) -> List[int]:
        """智能选择校准帧（均匀分布）"""
        if total_frames <= max_frames:
            return list(range(min(10, total_frames)))
        
        # 均匀选择
        step = total_frames // max_frames
        frames = [i * step for i in range(max_frames)]
        
        # 确保包含第一帧
        if 0 not in frames:
            frames[0] = 0
        
        return sorted(frames)
    
    def _test_strategy(self, img: np.ndarray, strategy: str, roi_type: str) -> Optional[Dict]:
        """测试单个预处理策略"""
        try:
            # 预处理
            processed = self.ocr_engine.preprocess_image(img, strategy)
            
            # 转换为RGB
            if len(processed.shape) == 2:
                processed = cv2.cvtColor(processed, cv2.COLOR_GRAY2RGB)
            elif processed.shape[2] == 3:
                processed = cv2.cvtColor(processed, cv2.COLOR_BGR2RGB)
            
            # OCR识别（不传cls参数，兼容不同版本）
            result = self.ocr_engine.ocr.ocr(processed)
            if not result or not result[0]:
                return None
            
            # 提取文本和置信度
            texts = []
            confidences = []
            for item in result[0]:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    text_info = item[1]
                    if isinstance(text_info, (list, tuple)) and len(text_info) >= 1:
                        texts.append(str(text_info[0]))
                        if len(text_info) >= 2:
                            confidences.append(float(text_info[1]))
            
            # 尝试解析时间
            time_str = self.ocr_engine._parse_time_from_texts(texts)
            
            if time_str:
                avg_conf = np.mean(confidences) if confidences else 0
                return {
                    'time': time_str,
                    'confidence': avg_conf
                }
        
        except Exception as e:
            self._log('debug', f"策略 {strategy} 测试异常: {e}")
        
        return None
    
    def _select_best_strategy(self, results: Dict, roi_type: str) -> Optional[str]:
        """选择最佳策略（综合成功率和置信度）"""
        if not results:
            return None
        
        # 计算每个策略的综合得分
        scores = {}
        for strategy, data in results.items():
            success_rate = data['success'] / 10  # 最多10帧
            avg_conf = np.mean(data['confidence']) if data['confidence'] else 0
            
            # 综合得分：成功率 70% + 置信度 30%
            score = success_rate * 0.7 + avg_conf * 0.3
            scores[strategy] = score
            
            self._log('debug', f"[{roi_type}] 策略 '{strategy}': "
                             f"成功={data['success']}, 置信度={avg_conf:.2f}, 得分={score:.2f}")
        
        # 选择得分最高的
        best = max(scores.items(), key=lambda x: x[1])
        return best[0] if best[1] > 0 else None
    
    def _quick_detect_real_roi(self, frame: np.ndarray) -> Optional[Tuple]:
        """快速检测 T_real 区域（简化版）"""
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # 使用单一阈值快速检测
        _, th = cv2.threshold(gray, 50, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for cnt in contours:
            x, y, w_box, h_box = cv2.boundingRect(cnt)
            area = w_box * h_box
            
            # 面积筛选
            if 0.05 * w * h < area < 0.5 * w * h:
                # 宽高比筛选
                ratio = w_box / h_box if h_box > 0 else 0
                if 1.2 < ratio < 5:
                    return (x, y, x + w_box, y + h_box)
        
        return None
    
    def record_frame_result(self, app_success: bool, real_success: bool):
        """记录每帧的识别结果（用于运行时监控）"""
        self.total_frames += 1
        if app_success:
            self.app_success_count += 1
        if real_success:
            self.real_success_count += 1
    
    def get_runtime_stats(self) -> Dict:
        """获取运行时统计"""
        if self.total_frames == 0:
            return {
                'app_success_rate': 0,
                'real_success_rate': 0,
                'overall_success_rate': 0
            }
        
        return {
            'app_success_rate': self.app_success_count / self.total_frames,
            'real_success_rate': self.real_success_count / self.total_frames,
            'overall_success_rate': (self.app_success_count + self.real_success_count) / (self.total_frames * 2)
        }
    
    def should_recalibrate(self) -> bool:
        """判断是否需要重新校准（成功率下降）"""
        if self.total_frames < 20:
            return False
        
        stats = self.get_runtime_stats()
        
        # 如果成功率低于50%，建议重新校准
        if stats['overall_success_rate'] < 0.5:
            self._log('warning', f"⚠️ 识别成功率下降至 {stats['overall_success_rate']:.1%}，建议检查视频质量")
            return True
        
        return False



