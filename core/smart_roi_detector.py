"""
智能 ROI 检测器 - 自适应检测时间戳区域
"""
import cv2
import numpy as np
from typing import Optional, Tuple, List


class SmartROIDetector:
    """智能 ROI 检测器 - 自动适应不同视频"""
    
    def __init__(self, logger=None):
        """初始化"""
        self.logger = logger
        self.last_successful_roi = None  # 记住上次成功的ROI
        self.roi_history = []  # ROI历史（用于平滑）
        self.max_history = 5
    
    def _log(self, level: str, msg: str):
        """内部日志"""
        if self.logger:
            if level == 'debug':
                self.logger.debug(msg)
            elif level == 'info':
                self.logger.info(msg)
            elif level == 'warning':
                self.logger.warning(msg)
    
    def detect(self, frame: np.ndarray, exclude_roi: Optional[Tuple] = None) -> Optional[Tuple]:
        """
        智能检测 T_real 区域
        
        Args:
            frame: 视频帧
            exclude_roi: 要排除的区域（T_app）
            
        Returns:
            (x1, y1, x2, y2) 或 None
        """
        h, w = frame.shape[:2]
        
        # 策略1：如果有历史ROI，先在附近搜索（时间序列稳定性）
        if self.last_successful_roi:
            roi = self._search_near_previous(frame, self.last_successful_roi, exclude_roi)
            if roi:
                return roi
        
        # 策略2：全局搜索（多种阈值）
        candidates = []
        
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # 尝试多个阈值
        for thresh_val in [30, 50, 70, 90]:
            _, binary = cv2.threshold(gray, thresh_val, 255, cv2.THRESH_BINARY_INV)
            
            # 形态学操作（去除噪点）
            kernel = np.ones((3, 3), np.uint8)
            binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
            
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            for cnt in contours:
                roi = self._evaluate_contour(cnt, frame.shape, exclude_roi)
                if roi:
                    candidates.append(roi)
        
        # 策略3：边缘检测
        edges = cv2.Canny(gray, 50, 150)
        kernel = np.ones((5, 5), np.uint8)
        edges = cv2.dilate(edges, kernel, iterations=1)
        
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            roi = self._evaluate_contour(cnt, frame.shape, exclude_roi)
            if roi:
                candidates.append(roi)
        
        # 选择最佳候选
        if candidates:
            best_roi = self._select_best_candidate(candidates, frame.shape)
            if best_roi:
                self._update_history(best_roi)
                return best_roi
        
        return None
    
    def _search_near_previous(self, frame: np.ndarray, prev_roi: Tuple, 
                            exclude_roi: Optional[Tuple]) -> Optional[Tuple]:
        """在上次成功ROI附近搜索"""
        x1, y1, x2, y2 = prev_roi
        h, w = frame.shape[:2]
        
        # 扩展搜索范围（允许10%的移动）
        margin = int(min(x2 - x1, y2 - y1) * 0.1)
        search_x1 = max(0, x1 - margin)
        search_y1 = max(0, y1 - margin)
        search_x2 = min(w, x2 + margin)
        search_y2 = min(h, y2 + margin)
        
        # 在搜索区域内查找
        search_region = frame[search_y1:search_y2, search_x1:search_x2]
        gray = cv2.cvtColor(search_region, cv2.COLOR_BGR2GRAY)
        
        _, binary = cv2.threshold(gray, 50, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        candidates = []
        for cnt in contours:
            x, y, w_box, h_box = cv2.boundingRect(cnt)
            # 转换回原图坐标
            abs_x1 = search_x1 + x
            abs_y1 = search_y1 + y
            abs_x2 = abs_x1 + w_box
            abs_y2 = abs_y1 + h_box
            
            roi = (abs_x1, abs_y1, abs_x2, abs_y2)
            if self._is_valid_roi(roi, frame.shape, exclude_roi):
                candidates.append(roi)
        
        if candidates:
            # 选择与历史ROI最接近的
            best = min(candidates, key=lambda r: self._roi_distance(r, prev_roi))
            return best
        
        return None
    
    def _evaluate_contour(self, contour, frame_shape: Tuple, 
                         exclude_roi: Optional[Tuple]) -> Optional[Tuple]:
        """评估轮廓是否是有效的时间戳区域"""
        x, y, w, h = cv2.boundingRect(contour)
        roi = (x, y, x + w, y + h)
        
        if self._is_valid_roi(roi, frame_shape, exclude_roi):
            return roi
        
        return None
    
    def _is_valid_roi(self, roi: Tuple, frame_shape: Tuple, 
                     exclude_roi: Optional[Tuple]) -> bool:
        """检查ROI是否有效"""
        x1, y1, x2, y2 = roi
        frame_h, frame_w = frame_shape[:2]
        
        w = x2 - x1
        h = y2 - y1
        area = w * h
        frame_area = frame_w * frame_h
        
        # 1. 面积筛选（5% - 50%）
        if area < 0.05 * frame_area or area > 0.5 * frame_area:
            return False
        
        # 2. 宽高比筛选（时间戳通常是横向的，1.2 - 5）
        ratio = w / h if h > 0 else 0
        if ratio < 1.2 or ratio > 5:
            return False
        
        # 3. 最小尺寸（至少50x20像素）
        if w < 50 or h < 20:
            return False
        
        # 4. 不能与exclude_roi重叠太多
        if exclude_roi:
            overlap = self._calculate_overlap(roi, exclude_roi)
            if overlap > 0.5:  # 重叠超过50%，认为无效
                return False
        
        return True
    
    def _calculate_overlap(self, roi1: Tuple, roi2: Tuple) -> float:
        """计算两个ROI的重叠率"""
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
        
        return intersection / union if union > 0 else 0
    
    def _select_best_candidate(self, candidates: List[Tuple], 
                              frame_shape: Tuple) -> Optional[Tuple]:
        """从候选ROI中选择最佳的"""
        if not candidates:
            return None
        
        # 去重（合并相近的ROI）
        merged = self._merge_similar_rois(candidates)
        
        if not merged:
            return None
        
        # 评分：考虑面积、宽高比、位置等
        scores = []
        frame_h, frame_w = frame_shape[:2]
        
        for roi in merged:
            x1, y1, x2, y2 = roi
            w = x2 - x1
            h = y2 - y1
            area = w * h
            ratio = w / h if h > 0 else 0
            
            # 面积得分（偏好中等大小）
            area_ratio = area / (frame_w * frame_h)
            area_score = 1 - abs(area_ratio - 0.15)  # 理想15%
            
            # 宽高比得分（偏好2-3）
            ratio_score = 1 - abs(ratio - 2.5) / 2.5
            
            # 位置得分（时间戳通常在屏幕中央或上方）
            center_y = (y1 + y2) / 2
            position_score = 1 - abs(center_y / frame_h - 0.4)  # 偏好40%高度
            
            # 历史一致性得分
            history_score = 0
            if self.last_successful_roi:
                history_score = 1 - self._roi_distance_normalized(roi, self.last_successful_roi, frame_shape)
            
            # 综合得分
            total_score = (
                area_score * 0.3 +
                ratio_score * 0.3 +
                position_score * 0.2 +
                history_score * 0.2
            )
            
            scores.append((roi, total_score))
        
        # 返回得分最高的
        best = max(scores, key=lambda x: x[1])
        return best[0] if best[1] > 0.3 else None  # 最低得分阈值
    
    def _merge_similar_rois(self, rois: List[Tuple], threshold: float = 0.5) -> List[Tuple]:
        """合并相似的ROI"""
        if not rois:
            return []
        
        merged = []
        used = set()
        
        for i, roi1 in enumerate(rois):
            if i in used:
                continue
            
            # 找到所有与roi1重叠的ROI
            group = [roi1]
            for j, roi2 in enumerate(rois):
                if j != i and j not in used:
                    overlap = self._calculate_overlap(roi1, roi2)
                    if overlap > threshold:
                        group.append(roi2)
                        used.add(j)
            
            # 合并group中的所有ROI（取外包矩形）
            x1 = min(r[0] for r in group)
            y1 = min(r[1] for r in group)
            x2 = max(r[2] for r in group)
            y2 = max(r[3] for r in group)
            
            merged.append((x1, y1, x2, y2))
            used.add(i)
        
        return merged
    
    def _roi_distance(self, roi1: Tuple, roi2: Tuple) -> float:
        """计算两个ROI的距离"""
        # 使用中心点距离
        cx1 = (roi1[0] + roi1[2]) / 2
        cy1 = (roi1[1] + roi1[3]) / 2
        cx2 = (roi2[0] + roi2[2]) / 2
        cy2 = (roi2[1] + roi2[3]) / 2
        
        return np.sqrt((cx1 - cx2)**2 + (cy1 - cy2)**2)
    
    def _roi_distance_normalized(self, roi1: Tuple, roi2: Tuple, frame_shape: Tuple) -> float:
        """归一化的ROI距离（0-1）"""
        distance = self._roi_distance(roi1, roi2)
        frame_h, frame_w = frame_shape[:2]
        max_distance = np.sqrt(frame_w**2 + frame_h**2)
        return distance / max_distance
    
    def _update_history(self, roi: Tuple):
        """更新ROI历史"""
        self.last_successful_roi = roi
        self.roi_history.append(roi)
        
        # 保持历史长度
        if len(self.roi_history) > self.max_history:
            self.roi_history.pop(0)
    
    def get_smoothed_roi(self) -> Optional[Tuple]:
        """获取平滑后的ROI（基于历史）"""
        if not self.roi_history:
            return None
        
        # 取平均值
        x1_avg = int(np.mean([r[0] for r in self.roi_history]))
        y1_avg = int(np.mean([r[1] for r in self.roi_history]))
        x2_avg = int(np.mean([r[2] for r in self.roi_history]))
        y2_avg = int(np.mean([r[3] for r in self.roi_history]))
        
        return (x1_avg, y1_avg, x2_avg, y2_avg)



