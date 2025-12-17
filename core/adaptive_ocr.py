"""
自适应 OCR 识别引擎
支持多种图像预处理策略和时间格式自动识别
"""
import cv2
import re
import numpy as np
from typing import Optional, Tuple, List, Dict
from paddleocr import PaddleOCR


class AdaptiveOCREngine:
    """自适应 OCR 识别引擎 - 自动尝试多种策略直到成功"""
    
    # 支持的时间格式（按常见程度排序）
    TIME_PATTERNS = [
        # 标准格式
        (r'(\d{2}):(\d{2}):(\d{2})\.(\d{3})', 'HH:MM:SS.mmm'),
        (r'(\d{2}):(\d{2}):(\d{2})[,，](\d{3})', 'HH:MM:SS,mmm'),
        (r'(\d{2}):(\d{2}):(\d{2})', 'HH:MM:SS'),
        (r'(\d{2})-(\d{2})-(\d{2})\.(\d{3})', 'HH-MM-SS.mmm'),
        
        # 纯数字格式
        (r'(\d{2})(\d{2})(\d{2})(\d{3})', 'HHMMSSmmm'),
        (r'(\d{2})(\d{2})(\d{2})', 'HHMMSS'),
        
        # 带毫秒的其他格式
        (r'(\d{1,2}):(\d{2}):(\d{2})\.(\d{1,3})', 'H:MM:SS.m'),
    ]
    
    def __init__(self, use_gpu: bool = False, lang: str = "en", logger=None):
        """初始化自适应 OCR 引擎"""
        self.logger = logger
        # PaddleOCR参数兼容性处理（不同版本支持的参数不同）
        # 尝试最小参数集初始化
        try:
            # 只使用最基本的参数
            self.ocr = PaddleOCR(
                use_angle_cls=False,
                lang=lang
            )
        except Exception as e:
            self._log('warning', f'PaddleOCR初始化失败，尝试默认参数: {e}')
            # 如果还失败，使用完全默认的初始化
            self.ocr = PaddleOCR()
        
        # 策略统计（记住哪个策略最有效）
        self.strategy_stats = {}
        self.best_strategy = None
    
    def _log(self, level: str, msg: str):
        """内部日志"""
        if self.logger:
            if level == 'debug':
                self.logger.debug(msg)
            elif level == 'info':
                self.logger.info(msg)
            elif level == 'warning':
                self.logger.warning(msg)
    
    def preprocess_image(self, img: np.ndarray, strategy: str) -> np.ndarray:
        """
        图像预处理策略
        
        Args:
            img: 输入图像
            strategy: 预处理策略名称
            
        Returns:
            处理后的图像
        """
        if strategy == 'original':
            # 原图
            return img
        
        elif strategy == 'grayscale':
            # 灰度化
            if len(img.shape) == 3:
                return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            return img
        
        elif strategy == 'binary':
            # 自适应二值化
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
            return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                        cv2.THRESH_BINARY, 11, 2)
        
        elif strategy == 'binary_inv':
            # 反向二值化（白底黑字）
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
            return cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                        cv2.THRESH_BINARY_INV, 11, 2)
        
        elif strategy == 'denoise':
            # 降噪
            if len(img.shape) == 3:
                return cv2.fastNlMeansDenoisingColored(img, None, 10, 10, 7, 21)
            else:
                return cv2.fastNlMeansDenoising(img, None, 10, 7, 21)
        
        elif strategy == 'sharpen':
            # 锐化
            kernel = np.array([[-1,-1,-1],
                              [-1, 9,-1],
                              [-1,-1,-1]])
            return cv2.filter2D(img, -1, kernel)
        
        elif strategy == 'contrast':
            # 增强对比度
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            return clahe.apply(gray)
        
        elif strategy == 'morph':
            # 形态学处理（去除噪点）
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
            kernel = np.ones((2,2), np.uint8)
            return cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)
        
        else:
            return img
    
    def extract_time_adaptive(self, img: np.ndarray, roi_type: str = "unknown") -> Optional[str]:
        """
        自适应时间提取 - 自动尝试多种策略
        
        Args:
            img: 输入图像
            roi_type: ROI类型（用于日志）
            
        Returns:
            识别的时间字符串，失败返回 None
        """
        # 预处理策略列表（按优先级排序）
        strategies = ['original', 'contrast', 'sharpen', 'grayscale', 
                     'binary', 'binary_inv', 'denoise', 'morph']
        
        # 如果有最佳策略，优先尝试
        if self.best_strategy and self.best_strategy in strategies:
            strategies.remove(self.best_strategy)
            strategies.insert(0, self.best_strategy)
        
        self._log('debug', f"[{roi_type}] 开始自适应识别，将尝试 {len(strategies)} 种策略")
        
        # 尝试每种策略
        for strategy in strategies:
            try:
                # 预处理
                processed_img = self.preprocess_image(img, strategy)
                
                # 确保是 RGB 格式（PaddleOCR 需要）
                if len(processed_img.shape) == 2:
                    processed_img = cv2.cvtColor(processed_img, cv2.COLOR_GRAY2RGB)
                elif processed_img.shape[2] == 4:
                    processed_img = cv2.cvtColor(processed_img, cv2.COLOR_BGRA2RGB)
                elif processed_img.shape[2] == 3:
                    processed_img = cv2.cvtColor(processed_img, cv2.COLOR_BGR2RGB)
                
                # OCR 识别（不传cls参数，兼容不同版本）
                result = self.ocr.ocr(processed_img)
                
                if not result or len(result) == 0 or not result[0]:
                    continue
                
                # 提取文本
                texts = []
                confidences = []
                for item in result[0]:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        text_info = item[1]
                        if isinstance(text_info, (list, tuple)) and len(text_info) >= 1:
                            texts.append(str(text_info[0]))
                            if len(text_info) >= 2:
                                confidences.append(float(text_info[1]))
                
                if not texts:
                    continue
                
                self._log('debug', f"[{roi_type}] 策略 '{strategy}' 识别文本: {texts[:3]}...")
                
                # 尝试解析时间
                time_str = self._parse_time_from_texts(texts)
                
                if time_str:
                    # 成功！记录策略
                    self._record_success(strategy)
                    avg_conf = sum(confidences) / len(confidences) if confidences else 0
                    self._log('info', f"[{roi_type}] ✓ 策略 '{strategy}' 成功识别: {time_str} (置信度: {avg_conf:.2f})")
                    return time_str
            
            except Exception as e:
                self._log('debug', f"[{roi_type}] 策略 '{strategy}' 异常: {e}")
                continue
        
        self._log('warning', f"[{roi_type}] ✗ 所有 {len(strategies)} 种策略均失败")
        return None
    
    def _parse_time_from_texts(self, texts: List[str]) -> Optional[str]:
        """从 OCR 文本列表中解析时间"""
        # 合并所有文本
        all_text = " ".join(texts)
        
        # 尝试每种时间格式
        for pattern, format_name in self.TIME_PATTERNS:
            match = re.search(pattern, all_text.replace(" ", ""))
            if match:
                groups = match.groups()
                
                # 格式化为标准格式 HH:MM:SS.mmm
                if len(groups) == 4:
                    # 有毫秒
                    h, m, s, ms = groups
                    # 确保毫秒是3位
                    ms = ms.ljust(3, '0')[:3]
                    return f"{h.zfill(2)}:{m.zfill(2)}:{s.zfill(2)}.{ms}"
                
                elif len(groups) == 3:
                    # 没有毫秒
                    h, m, s = groups
                    return f"{h.zfill(2)}:{m.zfill(2)}:{s.zfill(2)}.000"
        
        # 尝试宽松匹配：任何包含6-9位连续数字的
        digits = re.findall(r'\d+', all_text.replace(" ", ""))
        for d in digits:
            if len(d) >= 6:
                # 可能是 HHMMSS 或 HHMMSSmmm
                if len(d) == 6:
                    return f"{d[0:2]}:{d[2:4]}:{d[4:6]}.000"
                elif len(d) >= 9:
                    return f"{d[0:2]}:{d[2:4]}:{d[4:6]}.{d[6:9]}"
        
        return None
    
    def _record_success(self, strategy: str):
        """记录成功的策略"""
        if strategy not in self.strategy_stats:
            self.strategy_stats[strategy] = 0
        self.strategy_stats[strategy] += 1
        
        # 更新最佳策略
        if self.strategy_stats[strategy] > 2:  # 至少成功3次才认为是最佳
            self.best_strategy = strategy
            self._log('info', f"更新最佳策略: {strategy} (成功 {self.strategy_stats[strategy]} 次)")
    
    def validate_time(self, time_str: str) -> Tuple[bool, Optional[str]]:
        """
        验证时间格式是否合法
        
        Returns:
            (is_valid, error_reason)
        """
        if not time_str:
            return False, "无效时间"
        
        try:
            # 标准格式：HH:MM:SS.mmm
            parts = time_str.split(':')
            if len(parts) != 3:
                return False, "无效时间"
            
            hours = int(parts[0])
            minutes = int(parts[1])
            
            # 分离秒和毫秒
            sec_parts = parts[2].split('.')
            seconds = int(sec_parts[0])
            
            # 验证时间范围
            if not (0 <= hours < 24):
                return False, "无效时间"
            if not (0 <= minutes < 60):
                return False, "无效时间"
            if not (0 <= seconds < 60):
                return False, "无效时间"
            
            return True, None
        
        except Exception:
            return False, "无效时间"
    
    def parse_time_to_ms(self, time_str: str) -> Optional[int]:
        """时间字符串转毫秒（只处理有效时间）"""
        if not time_str:
            return None
        
        # 先验证
        is_valid, _ = self.validate_time(time_str)
        if not is_valid:
            return None
        
        try:
            # 标准格式：HH:MM:SS.mmm
            parts = time_str.split(':')
            if len(parts) != 3:
                return None
            
            hours = int(parts[0])
            minutes = int(parts[1])
            
            # 分离秒和毫秒
            sec_parts = parts[2].split('.')
            seconds = int(sec_parts[0])
            milliseconds = int(sec_parts[1]) if len(sec_parts) > 1 else 0
            
            # 转换为总毫秒数
            total_ms = hours * 3600000 + minutes * 60000 + seconds * 1000 + milliseconds
            return total_ms
        
        except Exception:
            return None
    
    def get_statistics(self) -> Dict:
        """获取识别统计"""
        return {
            'strategy_stats': self.strategy_stats.copy(),
            'best_strategy': self.best_strategy
        }



