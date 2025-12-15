"""
OCR引擎封装
使用PaddleOCR进行文本识别
"""
import re
from paddleocr import PaddleOCR


class OCREngine:
    """OCR识别引擎"""
    
    def __init__(self, use_gpu: bool = False, lang: str = "en"):
        """
        初始化OCR引擎
        
        Args:
            use_gpu: 是否使用GPU加速
            lang: 识别语言
        """
        self.ocr = PaddleOCR(
            use_angle_cls=False,
            lang=lang,
            use_gpu=use_gpu
        )
    
    def extract_text(self, image) -> str:
        """
        从图像中提取文本
        
        Args:
            image: OpenCV图像 (BGR格式)
            
        Returns:
            提取的文本字符串，多行用空格连接
        """
        try:
            result = self.ocr.ocr(image, cls=False)
            
            if not result or len(result) == 0:
                return ""
            
            # PaddleOCR返回格式: [[[box], (text, score)], ...]
            result_list = result[0] if result else []
            
            if not result_list:
                return ""
            
            # 提取所有文本
            texts = []
            for item in result_list:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    text_info = item[1]
                    if isinstance(text_info, (list, tuple)) and len(text_info) >= 1:
                        texts.append(str(text_info[0]))
            
            return " ".join(texts)
        
        except Exception as e:
            print(f"OCR识别失败: {e}")
            return ""
    
    @staticmethod
    def parse_time(text: str) -> str:
        """
        从文本中解析时间格式
        
        Args:
            text: OCR识别的文本
            
        Returns:
            格式化的时间字符串 "HH:MM:SS.mmm"，失败返回None
        """
        if not text:
            return None
        
        # 清理文本（移除空格）
        text = text.replace(" ", "")
        
        # 匹配多种时间格式
        patterns = [
            r'(\d{2}):(\d{2}):(\d{2})\.(\d{3})',  # HH:MM:SS.mmm
            r'(\d{2}):(\d{2}):(\d{2})',           # HH:MM:SS
            r'(\d{2})-(\d{2})-(\d{2})\.(\d{3})',  # HH-MM-SS.mmm
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                groups = match.groups()
                if len(groups) == 4:
                    # 有毫秒
                    return f"{groups[0]}:{groups[1]}:{groups[2]}.{groups[3]}"
                elif len(groups) == 3:
                    # 没有毫秒，补上000
                    return f"{groups[0]}:{groups[1]}:{groups[2]}.000"
        
        return None
    
    @staticmethod
    def time_to_ms(time_str: str) -> int:
        """
        将时间字符串转换为毫秒
        
        Args:
            time_str: 格式 "HH:MM:SS.mmm"
            
        Returns:
            毫秒数，失败返回None
        """
        if not time_str:
            return None
        
        try:
            # 解析 HH:MM:SS.mmm
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
        
        except Exception as e:
            print(f"时间转换失败: {time_str}, 错误: {e}")
            return None


