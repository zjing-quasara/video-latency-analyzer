"""
时间识别模块
识别视频中的时间戳（T_app和T_real）
"""
import re
from typing import Optional, Tuple
from src.core.roi_tracker import ROITracker


def parse_time_format_colon(text: str) -> Optional[str]:
    """
    解析冒号格式时间: HH:MM:SS.mmm (严格格式，不自动补0)
    
    Args:
        text: OCR识别的文本
        
    Returns:
        标准化时间字符串 "HH:MM:SS.mmm" 或 None
        
    Examples:
        "12:34:56.789" -> "12:34:56.789"
        "12:34:56"     -> "12:34:56.000" (无毫秒)
        "1:23:45.678"  -> None (小时位不足2位，拒绝识别)
        "12:34:56.78"  -> None (毫秒位不足3位，拒绝识别)
    """
    # 严格匹配 HH:MM:SS 格式（小时、分钟、秒都必须是2位）
    # 毫秒部分：要么没有，要么必须是完整的3位
    # 使用负向前瞻确保秒后面如果有点或冒号，后面必须跟3位数字
    pattern = r'(\d{2}):(\d{2}):(\d{2})(?:[.:](\d{3}))?(?![.:\d])'
    match = re.search(pattern, text)
    
    if match:
        h, m, s, ms = match.groups()
        h, m, s = int(h), int(m), int(s)
        
        # 验证时间有效性
        if not (0 <= h <= 23 and 0 <= m <= 59 and 0 <= s <= 59):
            return None
        
        # 处理毫秒部分
        if ms:
            # 毫秒必须是3位（正则已保证）
            pass
        else:
            # 没有毫秒部分，设为000
            ms = '000'
        
        return f"{h:02d}:{m:02d}:{s:02d}.{ms}"
    
    return None


def parse_time_format_digits(text: str) -> Optional[str]:
    """
    解析纯数字格式时间: HHMMSSMMM (9-13位连续数字)
    
    Args:
        text: OCR识别的文本
        
    Returns:
        标准化时间字符串 "HH:MM:SS.mmm" 或 None
        
    Examples:
        "123456789"     -> "12:34:56.789"
        "012345678"     -> "01:23:45.678"
        "1234567890"    -> "12:34:56.789"
        "123456"        -> "12:34:56.000" (无毫秒)
        "12345678"      -> None (毫秒位不足3位，拒绝识别)
    """
    # 提取所有连续数字
    numbers = re.findall(r'\d+', text)
    
    for num in numbers:
        # 只接受6位（HHMMSS无毫秒）或9位及以上（HHMMSSMMM有完整毫秒）
        if len(num) == 6:
            # 6位：HHMMSS，无毫秒部分
            try:
                h = int(num[0:2])
                m = int(num[2:4])
                s = int(num[4:6])
                
                # 验证时间有效性
                if not (0 <= h <= 23 and 0 <= m <= 59 and 0 <= s <= 59):
                    continue
                
                return f"{h:02d}:{m:02d}:{s:02d}.000"
                
            except (ValueError, IndexError):
                continue
                
        elif len(num) >= 9:
            # 9位及以上：HHMMSSMMM...，有完整毫秒
            try:
                h = int(num[0:2])
                m = int(num[2:4])
                s = int(num[4:6])
                
                # 验证时间有效性
                if not (0 <= h <= 23 and 0 <= m <= 59 and 0 <= s <= 59):
                    continue
                
                # 取前3位毫秒（不补0，必须完整）
                ms = num[6:9]
                
                return f"{h:02d}:{m:02d}:{s:02d}.{ms}"
                
            except (ValueError, IndexError):
                continue
        # 7-8位的情况：毫秒位不完整，拒绝识别
    
    return None


def parse_time_auto(text: str) -> Optional[str]:
    """
    自动识别时间格式
    
    Args:
        text: OCR识别的文本
        
    Returns:
        标准化时间字符串 "HH:MM:SS.mmm" 或 None
    """
    # 优先尝试冒号格式（更常见）
    time_str = parse_time_format_colon(text)
    if time_str:
        return time_str
    
    # 再尝试纯数字格式
    return parse_time_format_digits(text)


def parse_time_to_ms(time_str: str) -> Optional[int]:
    """
    时间字符串转换为毫秒
    
    Args:
        time_str: "HH:MM:SS.mmm" 格式的时间字符串
        
    Returns:
        毫秒数 (int) 或 None
        
    Examples:
        "12:34:56.789" -> 45296789
        "00:00:01.000" -> 1000
    """
    if not time_str:
        return None
    
    try:
        # 分割时间部分
        parts = time_str.split(':')
        if len(parts) != 3:
            return None
        
        h = int(parts[0])
        m = int(parts[1])
        
        # 处理秒和毫秒
        s_ms = parts[2].split('.')
        s = int(s_ms[0])
        ms = int(s_ms[1]) if len(s_ms) > 1 else 0
        
        # 转换为总毫秒数
        total_ms = ((h * 3600 + m * 60 + s) * 1000) + ms
        return total_ms
        
    except (ValueError, IndexError):
        return None


def calculate_overlap(roi1: Tuple[int, int, int, int], 
                     roi2: Tuple[int, int, int, int]) -> float:
    """
    计算两个ROI的重叠率（IoU - Intersection over Union）
    
    Args:
        roi1: (x1, y1, x2, y2)
        roi2: (x1, y1, x2, y2)
        
    Returns:
        重叠率 0.0-1.0
    """
    x1_1, y1_1, x2_1, y2_1 = roi1
    x1_2, y1_2, x2_2, y2_2 = roi2
    
    # 计算交集
    x_overlap = max(0, min(x2_1, x2_2) - max(x1_1, x1_2))
    y_overlap = max(0, min(y2_1, y2_2) - max(y1_1, y1_2))
    intersection = x_overlap * y_overlap
    
    # 计算并集
    area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
    area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
    union = area1 + area2 - intersection
    
    return intersection / union if union > 0 else 0.0


def detect_time_in_region(
    region,
    ocr,
    time_format: str = 'auto',
    min_confidence: float = 0.6,
    debug: bool = False
) -> Tuple[Optional[str], float]:
    """
    在指定图像区域内识别时间
    
    Args:
        region: 图像区域 (numpy array)
        ocr: OCR引擎实例
        time_format: 时间格式 'auto' | 'colon' | 'digits'
        min_confidence: 最低置信度阈值
        debug: 是否输出调试信息
        
    Returns:
        (时间字符串, 置信度) 或 (None, 0.0)
        - 时间字符串: "HH:MM:SS.mmm" 格式
        - 置信度: 0.0-1.0
    """
    if region.size == 0:
        if debug:
            print("[DEBUG] 区域为空")
        return None, 0.0
    
    try:
        # 调用OCR（兼容不同版本）
        try:
            result = ocr.ocr(region)  # PaddleOCR 3.x
        except TypeError:
            result = ocr.ocr(region, cls=False)  # PaddleOCR 2.x
        
        if not result or not result[0]:
            if debug:
                print("[DEBUG] OCR无结果")
            return None, 0.0
        
        if debug:
            print(f"[DEBUG] OCR识别到 {len(result[0])} 个文本")
            # 调试：打印第一个结果的格式
            if len(result[0]) > 0:
                print(f"[DEBUG] OCR返回格式示例: {result[0][0]}")
        
        # 遍历所有识别结果
        for line in result[0]:
            try:
                # 兼容不同PaddleOCR版本的返回格式
                if len(line) == 2:
                    bbox_points, text_info = line
                    if isinstance(text_info, tuple) and len(text_info) == 2:
                        text, confidence = text_info
                    else:
                        text, confidence = text_info[0], text_info[1]
                else:
                    if debug:
                        print(f"[DEBUG] OCR出错: 未知格式 line={line}")
                    continue
            except Exception as e:
                if debug:
                    print(f"[DEBUG] OCR出错: {e}, line={line}")
                continue
            
            if debug:
                print(f"[DEBUG]   文本='{text}', 置信度={confidence:.3f}")
            
            # 置信度过滤
            if confidence < min_confidence:
                continue
            
            # 根据格式解析时间
            time_str = None
            if time_format == 'auto':
                time_str = parse_time_auto(text)
            elif time_format == 'colon':
                time_str = parse_time_format_colon(text)
            elif time_format == 'digits':
                time_str = parse_time_format_digits(text)
            
            if time_str:
                if debug:
                    print(f"[DEBUG]   [OK] 匹配到时间: {time_str}")
                return time_str, confidence
        
    except Exception as e:
        if debug:
            print(f"[DEBUG] OCR出错: {e}")
        return None, 0.0
    
    if debug:
        print("[DEBUG] 未找到有效时间")
    return None, 0.0


def detect_time_app(
    frame,
    app_roi: Tuple[int, int, int, int],
    ocr,
    time_format: str = 'auto',
    debug: bool = False
) -> Tuple[Optional[str], float]:
    """
    识别T_app（应用内时间）- 在用户标定的区域内识别
    
    Args:
        frame: 视频帧 (numpy array)
        app_roi: T_app区域 (x1, y1, x2, y2)
        ocr: OCR引擎实例
        time_format: 时间格式 'auto' | 'colon' | 'digits'
        debug: 是否输出调试信息
        
    Returns:
        (时间字符串, 置信度) 或 (None, 0.0)
    """
    if debug:
        print(f"[DEBUG] T_app: 在用户标定区域识别 {app_roi}")
    
    # 裁剪用户标定的区域
    x1, y1, x2, y2 = app_roi
    app_region = frame[y1:y2, x1:x2]
    
    # 在该区域内识别时间
    return detect_time_in_region(
        app_region, 
        ocr, 
        time_format=time_format,
        debug=debug
    )


def detect_time_real(
    frame,
    ocr,
    exclude_roi: Optional[Tuple[int, int, int, int]] = None,
    time_format: str = 'auto',
    debug: bool = False
) -> Tuple[Optional[Tuple[int, int, int, int]], Optional[str], float]:
    """
    识别T_real（真实世界时间）- 全画面智能搜索
    
    采用中央优先策略：50% > 70% > 90% 逐步扩大搜索范围
    
    Args:
        frame: 视频帧 (numpy array)
        ocr: OCR引擎实例
        exclude_roi: 排除的ROI区域（通常是T_app区域）
        time_format: 时间格式 'auto' | 'colon' | 'digits'
        debug: 是否输出调试信息
        
    Returns:
        (roi, 时间字符串, 置信度) 或 (None, None, 0.0)
        - roi: 时间戳在画面中的位置 (x1, y1, x2, y2)
        - 时间字符串: "HH:MM:SS.mmm" 格式
        - 置信度: 0.0-1.0
    """
    h, w = frame.shape[:2]
    
    # 中央优先搜索策略
    search_regions = [
        ('center_50', int(w*0.25), int(h*0.25), int(w*0.75), int(h*0.75)),
        ('center_70', int(w*0.15), int(h*0.15), int(w*0.85), int(h*0.85)),
        ('center_90', int(w*0.05), int(h*0.05), int(w*0.95), int(h*0.95)),
    ]
    
    if debug:
        print(f"[DEBUG] T_real: 全画面搜索，排除区域={exclude_roi}")
    
    for region_name, x1, y1, x2, y2 in search_regions:
        region = frame[y1:y2, x1:x2]
        
        if region.size == 0:
            continue
        
        if debug:
            print(f"[DEBUG] 搜索区域: {region_name} ({x1},{y1})-({x2},{y2})")
        
        try:
            # OCR识别
            try:
                result = ocr.ocr(region)
            except TypeError:
                result = ocr.ocr(region, cls=False)
            
            if not result or not result[0]:
                if debug:
                    print(f"[DEBUG]   OCR无结果")
                continue
            
            # 遍历识别结果
            for line in result[0]:
                try:
                    if len(line) == 2:
                        bbox_points, text_info = line
                        if isinstance(text_info, tuple) and len(text_info) == 2:
                            text, confidence = text_info
                        else:
                            text, confidence = text_info[0], text_info[1]
                    else:
                        continue
                except Exception as e:
                    if debug:
                        print(f"[DEBUG]   OCR解析出错: {e}")
                    continue
                
                if confidence < 0.6:
                    continue
                
                # 解析时间
                time_str = None
                if time_format == 'auto':
                    time_str = parse_time_auto(text)
                elif time_format == 'colon':
                    time_str = parse_time_format_colon(text)
                elif time_format == 'digits':
                    time_str = parse_time_format_digits(text)
                
                if not time_str:
                    continue
                
                # 计算在原图中的绝对坐标
                if isinstance(bbox_points, list) and len(bbox_points) > 0:
                    # 确保bbox_points格式正确
                    if isinstance(bbox_points[0], (list, tuple)):
                        bbox = [[int(p[0] + x1), int(p[1] + y1)] for p in bbox_points]
                    else:
                        # 扁平化坐标
                        bbox = [[int(bbox_points[i] + x1), int(bbox_points[i+1] + y1)] 
                               for i in range(0, len(bbox_points), 2)]
                    
                    # 转换为矩形ROI
                    xs = [p[0] for p in bbox]
                    ys = [p[1] for p in bbox]
                    roi = (min(xs), min(ys), max(xs), max(ys))
                    
                    # 检查是否与排除区域重叠
                    if exclude_roi:
                        overlap = calculate_overlap(roi, exclude_roi)
                        if overlap > 0.5:
                            if debug:
                                print(f"[DEBUG]   [NG] 与排除区域重叠 {overlap:.2f}")
                            continue
                    
                    if debug:
                        print(f"[DEBUG]   [OK] 找到T_real: {time_str}, ROI={roi}")
                    
                    return roi, time_str, confidence
        
        except Exception as e:
            if debug:
                print(f"[DEBUG] {region_name}: OCR出错 - {e}")
            continue
    
    if debug:
        print("[DEBUG] 所有区域搜索完成，未找到T_real")
    
    return None, None, 0.0


def check_time_format_complete(time_str: str, original_text: str = None) -> Tuple[bool, str]:
    """
    检查时间格式是否完整
    
    Args:
        time_str: 标准化后的时间字符串
        original_text: OCR识别的原始文本（用于判断小时位数）
        
    Returns:
        (是否完整, 缺失位置) 
        - 缺失位置: "complete" | "left" | "right" | "both"
    """
    if not time_str:
        return False, "both"
    
    # 格式1: 冒号格式 HH:MM:SS.mmm
    colon_match = re.match(r'^(\d{1,2}):(\d{2}):(\d{2})(?:[.:](\d{1,3}))?$', time_str)
    if colon_match:
        hour, minute, second, ms = colon_match.groups()
        
        # 关键修改：检查原始文本中的小时位数
        if original_text:
            # 从原始文本中提取小时部分
            original_match = re.search(r'^.*?(\d{1,2}):(\d{2}):(\d{2})', original_text)
            if original_match:
                original_hour = original_match.group(1)
                # 如果原始文本中小时是个位数，一律判定为可能不完整
                if len(original_hour) == 1:
                    return False, "left"
        
        # 检查毫秒：应该有3位
        if ms is None or len(ms) < 3:
            return False, "right"
        
        return True, "complete"
    
    # 格式2: 纯数字格式 HHMMSSMMM (9-13位)
    digit_match = re.match(r'^(\d{9,13})$', time_str)
    if digit_match:
        digits = time_str
        length = len(digits)
        
        # 9位是最少的：HHMMSSMMM
        # 10-13位：小时可能>9或毫秒有4位
        if length >= 9:
            return True, "complete"
        else:
            # 位数不够
            return False, "both"
    
    # 其他不完整格式
    # 检查是否有冒号但不完整
    if ':' in time_str:
        # 有冒号但格式不对
        parts = time_str.split(':')
        if len(parts) < 3:
            return False, "right"  # 缺少秒或毫秒
        elif len(parts[0]) == 0:
            return False, "left"  # 小时被截断
        else:
            return False, "right"  # 可能毫秒不完整
    
    # 纯数字但位数不够
    if time_str.isdigit():
        if len(time_str) < 9:
            return False, "both"
    
    return False, "both"


def is_roi_at_edge(roi: Tuple[int, int, int, int], frame_shape: Tuple[int, int], margin: int = 10) -> Tuple[bool, str]:
    """
    判断ROI是否在画面边缘
    
    Args:
        roi: ROI区域 (x1, y1, x2, y2)
        frame_shape: 画面尺寸 (height, width)
        margin: 边缘距离阈值（像素）
        
    Returns:
        (是否在边缘, 边缘位置) 
        - 边缘位置: "left" | "right" | "top" | "bottom" | "none"
    """
    h, w = frame_shape
    x1, y1, x2, y2 = roi
    
    # 检查各边
    if x1 < margin:
        return True, "left"
    if x2 > w - margin:
        return True, "right"
    if y1 < margin:
        return True, "top"
    if y2 > h - margin:
        return True, "bottom"
    
    return False, "none"


def expand_roi_by_direction(
    roi: Tuple[int, int, int, int], 
    direction: str, 
    frame_shape: Tuple[int, int],
    expand_pixels: int = 50
) -> Tuple[int, int, int, int]:
    """
    按指定方向扩展ROI
    
    Args:
        roi: 原始ROI (x1, y1, x2, y2)
        direction: 扩展方向 "left" | "right" | "both"
        frame_shape: 画面尺寸 (height, width)
        expand_pixels: 扩展像素数
        
    Returns:
        扩展后的ROI
    """
    h, w = frame_shape
    x1, y1, x2, y2 = roi
    
    if direction == "left":
        x1 = max(0, x1 - expand_pixels)
    elif direction == "right":
        x2 = min(w, x2 + expand_pixels)
    elif direction == "both":
        x1 = max(0, x1 - expand_pixels)
        x2 = min(w, x2 + expand_pixels)
    
    return (x1, y1, x2, y2)


def detect_time_real_optimized(
    frame,
    frame_idx: int,
    roi_tracker: ROITracker,
    ocr,
    exclude_roi: Optional[Tuple[int, int, int, int]] = None,
    time_format: str = 'auto',
    debug: bool = False
) -> Tuple[Optional[Tuple[int, int, int, int]], Optional[str], float]:
    """
    优化版T_real识别 - 集成ROI跟踪和格式完整性检查
    
    采用快速跟踪 + 全局搜索 + 格式验证的策略
    
    Args:
        frame: 视频帧
        frame_idx: 当前帧号
        roi_tracker: ROI跟踪器实例
        ocr: OCR引擎
        exclude_roi: 排除区域（T_app）
        time_format: 时间格式
        debug: 调试模式
        
    Returns:
        (ROI, 时间字符串, 置信度)
    """
    h, w = frame.shape[:2]
    frame_shape = (h, w)
    
    # ========== 阶段1: 快速跟踪（如果有历史ROI）==========
    if roi_tracker.has_valid_roi(frame_idx):
        if debug:
            print(f"[DEBUG] 帧{frame_idx}: 使用ROI快速跟踪")
        
        try:
            # 在历史ROI±10%范围搜索
            search_roi = roi_tracker.get_search_region(frame_shape, expand_ratio=0.1)
            x1, y1, x2, y2 = search_roi
            search_region = frame[y1:y2, x1:x2]
            
            # OCR识别
            result = _ocr_recognize_region(search_region, ocr)
            if result:
                time_str, conf, bbox_in_region, original_text = result
                
                # 计算在原图中的绝对坐标
                abs_bbox = (
                    bbox_in_region[0] + x1,
                    bbox_in_region[1] + y1,
                    bbox_in_region[2] + x1,
                    bbox_in_region[3] + y1
                )
                
                # 格式完整性检查和扩展
                final_bbox, final_time_str, final_conf = _verify_and_expand_roi(
                    frame, abs_bbox, time_str, conf, ocr, frame_shape, exclude_roi, time_format, original_text, debug
                )
                
                if final_time_str:
                    # 成功：更新ROI
                    roi_tracker.update_roi(final_bbox, frame_idx, success=True)
                    if debug:
                        print(f"[DEBUG]   [OK] 快速跟踪成功: {final_time_str}")
                    return final_bbox, final_time_str, final_conf
        
        except Exception as e:
            if debug:
                print(f"[DEBUG] 快速跟踪出错: {e}")
        
        # 快速跟踪失败，记录失败
        roi_tracker.update_roi(roi_tracker.roi, frame_idx, success=False)
        if debug:
            print(f"[DEBUG]   [NG] 快速跟踪失败，降级到全局搜索")
    
    # ========== 阶段2: 全局搜索 ==========
    if debug:
        print(f"[DEBUG] 帧{frame_idx}: 全局搜索")
    
    # 搜索区域：50% > 70% > 90%
    search_regions = [
        ('center_50', int(w*0.25), int(h*0.25), int(w*0.75), int(h*0.75)),
        ('center_70', int(w*0.15), int(h*0.15), int(w*0.85), int(h*0.85)),
        ('center_90', int(w*0.05), int(h*0.05), int(w*0.95), int(h*0.95)),
    ]
    
    for region_name, x1, y1, x2, y2 in search_regions:
        region = frame[y1:y2, x1:x2]
        
        if region.size == 0:
            continue
        
        if debug:
            print(f"[DEBUG]   搜索区域: {region_name}")
        
        try:
            result = _ocr_recognize_region(region, ocr)
            if result:
                time_str, conf, bbox_in_region, original_text = result
                
                # 计算绝对坐标
                abs_bbox = (
                    bbox_in_region[0] + x1,
                    bbox_in_region[1] + y1,
                    bbox_in_region[2] + x1,
                    bbox_in_region[3] + y1
                )
                
                # 格式检查和扩展
                final_bbox, final_time_str, final_conf = _verify_and_expand_roi(
                    frame, abs_bbox, time_str, conf, ocr, frame_shape, exclude_roi, time_format, original_text, debug
                )
                
                if final_time_str:
                    # 成功：建立新ROI
                    roi_tracker.establish_roi(final_bbox, frame_idx)
                    if debug:
                        print(f"[DEBUG]   [OK] 全局搜索成功: {final_time_str} (区域:{region_name})")
                    return final_bbox, final_time_str, final_conf
        
        except Exception as e:
            if debug:
                print(f"[DEBUG]   {region_name}: OCR出错 - {e}")
            continue
    
    # ========== 全部失败 ==========
    if debug:
        print("[DEBUG] 所有搜索完成，未找到T_real")
    
    return None, None, 0.0


def _ocr_recognize_region(region, ocr) -> Optional[Tuple[str, float, Tuple[int, int, int, int], str]]:
    """
    在指定区域进行OCR识别，找到第一个时间格式
    
    Returns:
        (时间字符串, 置信度, bbox, 原始文本) 或 None
    """
    try:
        result = ocr.ocr(region, cls=False)
    except TypeError:
        result = ocr.ocr(region)
    
    if not result or not result[0]:
        return None
    
    # 遍历所有识别结果
    for line in result[0]:
        try:
            if len(line) == 2:
                bbox_points, text_info = line
                if isinstance(text_info, tuple) and len(text_info) == 2:
                    text, confidence = text_info
                else:
                    text, confidence = text_info[0], text_info[1]
            else:
                continue
        except:
            continue
        
        if confidence < 0.6:
            continue
        
        # 尝试解析时间
        time_str = parse_time_auto(text)
        if time_str:
            # 计算bbox
            if isinstance(bbox_points, list) and len(bbox_points) > 0:
                if isinstance(bbox_points[0], (list, tuple)):
                    xs = [int(p[0]) for p in bbox_points]
                    ys = [int(p[1]) for p in bbox_points]
                else:
                    xs = [int(bbox_points[i]) for i in range(0, len(bbox_points), 2)]
                    ys = [int(bbox_points[i]) for i in range(1, len(bbox_points), 2)]
                
                bbox = (min(xs), min(ys), max(xs), max(ys))
                return time_str, confidence, bbox, text  # 返回原始文本
    
    return None


def _verify_and_expand_roi(
    frame, 
    bbox: Tuple[int, int, int, int],
    time_str: str,
    conf: float,
    ocr,
    frame_shape: Tuple[int, int],
    exclude_roi: Optional[Tuple[int, int, int, int]],
    time_format: str,
    original_text: str,
    debug: bool
) -> Tuple[Optional[Tuple[int, int, int, int]], Optional[str], float]:
    """
    验证时间格式完整性，必要时扩展ROI重新识别
    
    Args:
        original_text: OCR识别的原始文本（用于判断小时位数）
    
    Returns:
        (最终bbox, 最终时间字符串, 置信度)
    """
    # 检查与排除区域的重叠
    if exclude_roi:
        overlap = calculate_overlap(bbox, exclude_roi)
        
        # 计算包含率：bbox在exclude_roi内的比例
        x1, y1, x2, y2 = bbox
        ex1, ey1, ex2, ey2 = exclude_roi
        
        x_overlap = max(0, min(x2, ex2) - max(x1, ex1))
        y_overlap = max(0, min(y2, ey2) - max(y1, ey1))
        intersection = x_overlap * y_overlap
        
        area_bbox = (x2 - x1) * (y2 - y1)
        containment = intersection / area_bbox if area_bbox > 0 else 0
        
        # 拒绝条件：IoU > 0.5 或 包含率 > 0.5
        # 包含率检查解决了"小框完全在大框内但IoU不高"的问题
        if overlap > 0.5 or containment > 0.5:
            if debug:
                print(f"[DEBUG]   [NG] 与T_app重叠 IoU={overlap:.2f}, 包含率={containment:.2f}")
            return None, None, 0.0
    
    # 格式完整性检查（传入原始文本）
    is_complete, missing_direction = check_time_format_complete(time_str, original_text)
    
    if is_complete:
        # 格式完整，直接返回
        return bbox, time_str, conf
    
    if debug:
        print(f"[DEBUG]   格式不完整: {time_str}, 缺失位置: {missing_direction}")
    
    # 格式不完整：尝试扩展ROI
    # 先检查是否在边缘
    at_edge, edge_side = is_roi_at_edge(bbox, frame_shape, margin=10)
    
    # 第1次扩展
    expanded_bbox = expand_roi_by_direction(bbox, missing_direction, frame_shape, expand_pixels=50)
    
    # 如果扩展后还在同一边缘，说明画面截断了
    if at_edge:
        at_edge_after, edge_side_after = is_roi_at_edge(expanded_bbox, frame_shape, margin=5)
        if at_edge_after and edge_side == edge_side_after:
            if debug:
                print(f"[DEBUG]   [NG] 画面边缘截断 ({edge_side})")
            return None, None, 0.0
    
    # 重新OCR
    x1, y1, x2, y2 = expanded_bbox
    expanded_region = frame[y1:y2, x1:x2]
    
    try:
        result = ocr.ocr(expanded_region, cls=False)
        if result and result[0]:
            for line in result[0]:
                try:
                    if len(line) == 2:
                        _, text_info = line
                        if isinstance(text_info, tuple) and len(text_info) == 2:
                            text, new_conf = text_info
                        else:
                            text, new_conf = text_info[0], text_info[1]
                    else:
                        continue
                except:
                    continue
                new_time_str = parse_time_auto(text) if time_format == 'auto' else (
                    parse_time_format_colon(text) if time_format == 'colon' else parse_time_format_digits(text)
                )
                
                if new_time_str:
                    # 再次检查完整性（传入新的原始文本）
                    is_complete_new, _ = check_time_format_complete(new_time_str, text)
                    if is_complete_new:
                        if debug:
                            print(f"[DEBUG]   [OK] 扩展后完整: {new_time_str}")
                        return expanded_bbox, new_time_str, new_conf
    
    except Exception as e:
        if debug:
            print(f"[DEBUG]   扩展ROI识别出错: {e}")
    
    # 扩展后还是不完整，返回None
    if debug:
        print(f"[DEBUG]   [NG] 扩展后仍不完整")
    
    return None, None, 0.0


