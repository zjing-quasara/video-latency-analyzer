"""
主窗口和ROI标定对话框
"""
import sys
import subprocess
import cv2
import numpy as np
from pathlib import Path
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QTextEdit, QFileDialog, QMessageBox, QDialog, QSlider,
    QGroupBox, QCheckBox, QComboBox, QSpinBox, QRadioButton, QLineEdit
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap
from .worker import AnalysisWorker
from config import REPORT_CONFIG
from utils.logger import get_logger, get_log_file
import json


class ROIAdjustDialog(QDialog):
    """ROI手动调整对话框"""
    
    def __init__(self, frame, initial_roi, parent=None):
        super().__init__(parent)
        self.setWindowTitle("标定 T_app 区域")
        self.setModal(True)
        self.resize(1000, 700)
        
        self.frame = frame
        self.h, self.w = frame.shape[:2]
        self.confirmed = False
        
        # 初始化ROI
        self.x1, self.y1, self.x2, self.y2 = initial_roi
        
        self.init_ui()
        self.update_preview()
    
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 图像预览
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.image_label)
        
        # 滑块控制
        sliders_layout = QVBoxLayout()
        
        self.x1_slider = self._create_slider("X1 (左)", 0, self.w, self.x1, sliders_layout)
        self.y1_slider = self._create_slider("Y1 (上)", 0, self.h, self.y1, sliders_layout)
        self.x2_slider = self._create_slider("X2 (右)", 0, self.w, self.x2, sliders_layout)
        self.y2_slider = self._create_slider("Y2 (下)", 0, self.h, self.y2, sliders_layout)
        
        layout.addLayout(sliders_layout)
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_confirm = QPushButton("确认")
        btn_cancel = QPushButton("取消")
        btn_confirm.clicked.connect(self.on_confirm)
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_confirm)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)
    
    def _create_slider(self, label, min_val, max_val, init_val, parent_layout):
        """创建滑块"""
        h_layout = QHBoxLayout()
        lbl = QLabel(f"{label}:")
        lbl.setFixedWidth(80)
        slider = QSlider(Qt.Horizontal)
        slider.setMinimum(min_val)
        slider.setMaximum(max_val)
        slider.setValue(init_val)
        slider.valueChanged.connect(self.on_slider_changed)
        value_label = QLabel(str(init_val))
        value_label.setFixedWidth(50)
        slider.value_label = value_label
        h_layout.addWidget(lbl)
        h_layout.addWidget(slider)
        h_layout.addWidget(value_label)
        parent_layout.addLayout(h_layout)
        return slider
    
    def on_slider_changed(self):
        """滑块变化"""
        self.x1 = self.x1_slider.value()
        self.y1 = self.y1_slider.value()
        self.x2 = self.x2_slider.value()
        self.y2 = self.y2_slider.value()
        
        # 更新标签
        self.x1_slider.value_label.setText(str(self.x1))
        self.y1_slider.value_label.setText(str(self.y1))
        self.x2_slider.value_label.setText(str(self.x2))
        self.y2_slider.value_label.setText(str(self.y2))
        
        self.update_preview()
    
    def update_preview(self):
        """更新预览"""
        preview = self.frame.copy()
        
        # 画蓝色ROI框
        cv2.rectangle(preview, (self.x1, self.y1), (self.x2, self.y2), (255, 0, 0), 2)
        
        # 转换为QPixmap显示
        h, w, ch = preview.shape
        bytes_per_line = ch * w
        q_img = QImage(preview.data, w, h, bytes_per_line, QImage.Format_BGR888)
        pixmap = QPixmap.fromImage(q_img)
        
        # 缩放以适应窗口
        scaled_pixmap = pixmap.scaled(900, 600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_label.setPixmap(scaled_pixmap)
    
    def on_confirm(self):
        """确认"""
        if self.x2 <= self.x1 or self.y2 <= self.y1:
            QMessageBox.warning(self, "警告", "ROI区域无效")
            return
        self.confirmed = True
        self.accept()
    
    def get_roi(self):
        """获取ROI"""
        return (self.x1, self.y1, self.x2, self.y2)


class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self):
        super().__init__()
        self.logger = get_logger('MainWindow')
        self.video_path = None
        self.video_total_frames = 0  # 视频总帧数
        self.video_fps = 0  # 视频FPS
        self.roi_config_path = Path("data/config/roi_config.json")
        self.worker = None
        self.use_gpu = True  # 默认使用GPU
        self.resize_ratio = 0.5
        self.report_folder = None  # 保存最后生成的报告文件夹路径
        self.phone_log_path = None  # 手机网络日志路径
        self.pc_log_path = None  # 电脑网络日志路径
        
        # 默认输出路径（桌面）
        from config import DEFAULT_OUTPUT_DIR
        self.output_dir = DEFAULT_OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger.info("主窗口初始化")
        self.init_ui()
    
    def get_app_roi(self):
        """获取保存的APP ROI配置"""
        try:
            if self.roi_config_path.exists():
                with open(self.roi_config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    return config.get('app_roi')
        except Exception as e:
            self.logger.warning(f"读取ROI配置失败: {e}")
        return None
    
    def set_app_roi(self, roi):
        """保存APP ROI配置"""
        try:
            config = {}
            if self.roi_config_path.exists():
                with open(self.roi_config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            config['app_roi'] = roi
            self.roi_config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.roi_config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"保存ROI配置失败: {e}")
    
    def save_video_dir(self, video_dir):
        """保存最后使用的视频目录"""
        try:
            config = {}
            if self.roi_config_path.exists():
                with open(self.roi_config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            config['last_video_dir'] = video_dir
            with open(self.roi_config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"保存视频目录失败: {e}")
    
    def get_last_video_dir(self):
        """获取最后使用的视频目录"""
        try:
            if self.roi_config_path.exists():
                with open(self.roi_config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    return config.get('last_video_dir')
        except Exception as e:
            self.logger.warning(f"读取视频目录失败: {e}")
        return None
    
    @staticmethod
    def get_default_app_roi(w, h):
        """获取默认APP ROI位置（左上角区域）"""
        roi_w = int(w * 0.3)
        roi_h = int(h * 0.15)
        return (10, 10, roi_w, roi_h)
    
    def init_ui(self):
        self.setWindowTitle("视频延时分析工具")
        self.setGeometry(100, 100, 900, 700)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # 视频选择
        file_layout = QHBoxLayout()
        self.video_label = QLabel("未选择视频")
        btn_select = QPushButton("选择视频")
        btn_select.clicked.connect(self.select_video)
        file_layout.addWidget(QLabel("视频文件:"))
        file_layout.addWidget(self.video_label, 1)
        file_layout.addWidget(btn_select)
        layout.addLayout(file_layout)
        
        # 输出路径选择
        output_layout = QHBoxLayout()
        self.output_label = QLabel(str(self.output_dir))
        btn_select_output = QPushButton("选择输出路径")
        btn_select_output.clicked.connect(self.select_output_dir)
        output_layout.addWidget(QLabel("输出路径:"))
        output_layout.addWidget(self.output_label, 1)
        output_layout.addWidget(btn_select_output)
        layout.addLayout(output_layout)
        
        # ROI状态
        roi_layout = QHBoxLayout()
        app_roi = self.get_app_roi()
        roi_text = f"T_app ROI: {app_roi}" if app_roi else "T_app ROI: 未配置"
        self.roi_status_label = QLabel(roi_text)
        btn_calibrate = QPushButton("标定 T_app")
        btn_calibrate.clicked.connect(self.calibrate_roi)
        roi_layout.addWidget(self.roi_status_label, 1)
        roi_layout.addWidget(btn_calibrate)
        layout.addLayout(roi_layout)
        
        # 性能设置
        perf_group = QGroupBox("性能设置")
        perf_layout = QHBoxLayout()
        
        self.gpu_checkbox = QCheckBox("使用 GPU 加速")
        self.gpu_checkbox.setChecked(True)  # 默认勾选GPU
        self.gpu_checkbox.stateChanged.connect(self.on_gpu_changed)
        perf_layout.addWidget(self.gpu_checkbox)
        
        perf_layout.addWidget(QLabel("OCR 分辨率:"))
        self.resize_combo = QComboBox()
        self.resize_combo.addItem("50% (最快)", 0.5)
        self.resize_combo.addItem("75% (平衡)", 0.75)
        self.resize_combo.addItem("100% (最清晰)", 1.0)
        self.resize_combo.setCurrentIndex(0)
        self.resize_combo.currentIndexChanged.connect(self.on_resize_changed)
        perf_layout.addWidget(self.resize_combo)
        
        perf_group.setLayout(perf_layout)
        layout.addWidget(perf_group)
        
        # 分析参数设置
        param_group = QGroupBox("分析参数")
        param_layout = QVBoxLayout()
        
        # T_real格式选择
        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("T_real格式:"))
        self.treal_format_combo = QComboBox()
        self.treal_format_combo.addItem("标准格式 (HH:MM:SS.mmm)", "standard")
        self.treal_format_combo.addItem("纯数字格式 (HHMMSSMMM)", "digits")
        self.treal_format_combo.setCurrentIndex(0)  # 默认标准格式
        format_layout.addWidget(self.treal_format_combo)
        format_layout.addWidget(QLabel("（选择手机屏幕显示的时间格式）"))
        format_layout.addStretch()
        param_layout.addLayout(format_layout)
        
        # 抽帧间隔
        frame_step_layout = QHBoxLayout()
        frame_step_layout.addWidget(QLabel("抽帧间隔:"))
        self.frame_step_spin = QComboBox()
        self.frame_step_spin.addItem("每1帧", 1)
        self.frame_step_spin.addItem("每3帧", 3)
        self.frame_step_spin.addItem("每5帧（推荐）", 5)
        self.frame_step_spin.addItem("每10帧", 10)
        self.frame_step_spin.addItem("每15帧", 15)
        self.frame_step_spin.setCurrentIndex(2)  # 默认每5帧
        frame_step_layout.addWidget(self.frame_step_spin)
        frame_step_layout.addWidget(QLabel("（间隔越大，速度越快，但数据点越少）"))
        frame_step_layout.addStretch()
        param_layout.addLayout(frame_step_layout)
        
        # 分析帧数
        frame_limit_layout = QHBoxLayout()
        frame_limit_layout.addWidget(QLabel("分析帧数:"))
        
        self.frame_limit_spin = QSpinBox()
        self.frame_limit_spin.setMinimum(10)
        self.frame_limit_spin.setMaximum(999999)
        self.frame_limit_spin.setValue(100)
        self.frame_limit_spin.setSuffix(" 帧")
        self.frame_limit_spin.setEnabled(False)  # 初始禁用，选择视频后启用
        frame_limit_layout.addWidget(self.frame_limit_spin)
        
        self.full_analysis_check = QCheckBox("全量分析（整个视频）")
        self.full_analysis_check.stateChanged.connect(self.on_full_analysis_changed)
        frame_limit_layout.addWidget(self.full_analysis_check)
        
        self.video_info_label = QLabel("（请先选择视频）")
        self.video_info_label.setStyleSheet("color: #666;")
        frame_limit_layout.addWidget(self.video_info_label)
        frame_limit_layout.addStretch()
        param_layout.addLayout(frame_limit_layout)
        
        param_group.setLayout(param_layout)
        layout.addWidget(param_group)
        
        # 网络监控日志导入
        network_group = QGroupBox("网络监控日志")
        network_layout = QVBoxLayout()
        
        # 单选按钮（是/否）
        radio_layout = QHBoxLayout()
        radio_layout.addWidget(QLabel("  "))  # 缩进
        self.radio_network_yes = QRadioButton("是")
        self.radio_network_no = QRadioButton("否")
        self.radio_network_no.setChecked(True)  # 默认选"否"
        radio_layout.addWidget(self.radio_network_yes)
        radio_layout.addWidget(self.radio_network_no)
        radio_layout.addStretch()
        network_layout.addLayout(radio_layout)
        
        # 文件选择区域（默认隐藏）
        self.network_file_widget = QWidget()
        file_widget_layout = QVBoxLayout()
        
        # 手机日志
        phone_layout = QHBoxLayout()
        phone_layout.addWidget(QLabel("  手机日志:"))
        self.phone_log_input = QLineEdit()
        self.phone_log_input.setReadOnly(True)
        self.phone_log_input.setPlaceholderText("未选择")
        self.btn_phone_log = QPushButton("浏览...")
        self.btn_phone_log.clicked.connect(self.select_phone_log)
        phone_layout.addWidget(self.phone_log_input, 1)
        phone_layout.addWidget(self.btn_phone_log)
        file_widget_layout.addLayout(phone_layout)
        
        # 电脑日志
        pc_layout = QHBoxLayout()
        pc_layout.addWidget(QLabel("  电脑日志:"))
        self.pc_log_input = QLineEdit()
        self.pc_log_input.setReadOnly(True)
        self.pc_log_input.setPlaceholderText("未选择（可选）")
        self.btn_pc_log = QPushButton("浏览...")
        self.btn_pc_log.clicked.connect(self.select_pc_log)
        self.label_optional = QLabel("(可选)")
        pc_layout.addWidget(self.pc_log_input, 1)
        pc_layout.addWidget(self.btn_pc_log)
        pc_layout.addWidget(self.label_optional)
        file_widget_layout.addLayout(pc_layout)
        
        self.network_file_widget.setLayout(file_widget_layout)
        self.network_file_widget.hide()  # 默认隐藏
        
        network_layout.addWidget(self.network_file_widget)
        network_group.setLayout(network_layout)
        layout.addWidget(network_group)
        
        # 信号连接：选"是"时显示，选"否"时隐藏
        self.radio_network_yes.toggled.connect(
            lambda checked: self.network_file_widget.setVisible(checked)
        )
        
        # 开始分析
        self.btn_start = QPushButton("开始分析")
        self.btn_start.clicked.connect(self.start_analysis)
        self.btn_start.setEnabled(False)
        layout.addWidget(self.btn_start)
        
        # 进度条
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        
        # 日志
        layout.addWidget(QLabel("处理日志:"))
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)
        
        # 结果按钮
        result_layout = QHBoxLayout()
        self.btn_open_html = QPushButton("打开 HTML 报告")
        self.btn_open_html.clicked.connect(self.open_html_report)
        self.btn_open_html.setEnabled(False)
        
        self.btn_open_csv = QPushButton("打开报告文件夹")
        self.btn_open_csv.clicked.connect(self.open_csv_report)
        self.btn_open_csv.setEnabled(False)
        
        self.btn_open_log = QPushButton("打开日志文件")
        self.btn_open_log.clicked.connect(self.open_log_file)
        
        result_layout.addWidget(self.btn_open_html)
        result_layout.addWidget(self.btn_open_csv)
        result_layout.addWidget(self.btn_open_log)
        layout.addLayout(result_layout)
    
    def select_video(self):
        """选择视频"""
        # 获取上次视频目录
        last_dir = self.get_last_video_dir()
        if not last_dir or not Path(last_dir).exists():
            last_dir = str(Path.home())
        
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择视频文件", last_dir, "视频文件 (*.mp4 *.avi *.mov)"
        )
        if file_path:
            self.video_path = file_path
            self.video_label.setText(Path(file_path).name)
            
            # 获取视频信息
            cap = cv2.VideoCapture(file_path)
            if cap.isOpened():
                self.video_total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                self.video_fps = cap.get(cv2.CAP_PROP_FPS)
                cap.release()
                
                # 更新UI
                self.frame_limit_spin.setMaximum(self.video_total_frames)
                self.frame_limit_spin.setEnabled(True)
                
                # 计算推荐值（前100帧或10%，取较小者）
                recommended = min(100, int(self.video_total_frames * 0.1))
                self.frame_limit_spin.setValue(recommended)
                
                # 更新提示信息
                duration_sec = self.video_total_frames / self.video_fps if self.video_fps > 0 else 0
                self.video_info_label.setText(
                    f"总帧数: {self.video_total_frames} ({duration_sec:.1f}秒)"
                )
                self.video_info_label.setStyleSheet("color: #27ae60;")
                
                self.append_log(f"已选择视频: {file_path}")
                self.append_log(f"视频信息: {self.video_total_frames}帧, {self.video_fps:.2f}FPS, {duration_sec:.1f}秒")
            else:
                QMessageBox.warning(self, "警告", "无法读取视频信息")
            
            self.update_start_button()
            
            # 保存视频目录
            video_dir = str(Path(file_path).parent)
            self.save_video_dir(video_dir)
    
    def on_full_analysis_changed(self, state):
        """全量分析选项变化"""
        from PyQt5.QtCore import Qt
        is_full = (state == Qt.Checked)
        self.frame_limit_spin.setEnabled(not is_full)
        
        if is_full:
            self.video_info_label.setText(f"将分析全部 {self.video_total_frames} 帧")
            self.video_info_label.setStyleSheet("color: #e67e22;")
        else:
            duration_sec = self.video_total_frames / self.video_fps if self.video_fps > 0 else 0
            self.video_info_label.setText(f"总帧数: {self.video_total_frames} ({duration_sec:.1f}秒)")
            self.video_info_label.setStyleSheet("color: #27ae60;")
    
    def select_output_dir(self):
        """选择输出路径"""
        dir_path = QFileDialog.getExistingDirectory(
            self, "选择报告输出路径", str(self.output_dir)
        )
        if dir_path:
            self.output_dir = Path(dir_path)
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self.output_label.setText(str(self.output_dir))
            self.append_log(f"已设置输出路径: {self.output_dir}")
    
    def select_phone_log(self):
        """选择手机网络日志"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择手机网络日志", str(Path.home()), "CSV文件 (*.csv)"
        )
        if file_path:
            self.phone_log_path = file_path
            self.phone_log_input.setText(Path(file_path).name)
            self.append_log(f"已选择手机日志: {Path(file_path).name}")
    
    def select_pc_log(self):
        """选择电脑网络日志"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择电脑网络日志", str(Path.home()), "CSV文件 (*.csv)"
        )
        if file_path:
            self.pc_log_path = file_path
            self.pc_log_input.setText(Path(file_path).name)
            self.append_log(f"已选择电脑日志: {Path(file_path).name}")
    
    def calibrate_roi(self):
        """标定ROI"""
        if not self.video_path:
            QMessageBox.warning(self, "提示", "请先选择视频文件")
            return
        
        # 读取第1帧
        cap = cv2.VideoCapture(self.video_path)
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            QMessageBox.critical(self, "错误", "无法读取视频第1帧")
            return
        
        h, w = frame.shape[:2]
        
        # 获取初始ROI
        app_roi = self.get_app_roi()
        if app_roi:
            initial_roi = app_roi
            self.append_log("使用上次保存的 ROI 位置")
        else:
            initial_roi = self.get_default_app_roi(w, h)
            self.append_log("使用默认 ROI 位置")
        
        # 打开调整对话框
        dialog = ROIAdjustDialog(frame, initial_roi, self)
        if dialog.exec_() == QDialog.Accepted and dialog.confirmed:
            roi = dialog.get_roi()
            self.set_app_roi(roi)
            self.roi_status_label.setText(f"T_app ROI: {roi}")
            
            # 保存配置（包括上次视频目录）
            video_dir = str(Path(self.video_path).parent) if self.video_path else None
            self.save_video_dir(video_dir)
            
            self.update_start_button()
            self.append_log(f"T_app ROI 已更新: {roi}")
    
    def on_gpu_changed(self, state):
        """GPU选项变化"""
        self.use_gpu = (state == Qt.Checked)
        status = "已启用" if self.use_gpu else "已禁用"
        self.append_log(f"GPU 加速: {status}")
    
    def on_resize_changed(self, index):
        """分辨率选项变化"""
        self.resize_ratio = self.resize_combo.currentData()
        self.append_log(f"OCR 分辨率缩放: {int(self.resize_ratio*100)}%")
    
    def update_start_button(self):
        """更新开始按钮状态"""
        has_video = self.video_path is not None
        has_roi = self.get_app_roi() is not None
        self.btn_start.setEnabled(has_video and has_roi)
    
    def start_analysis(self):
        """开始分析"""
        if not self.video_path or not self.get_app_roi():
            return
        
        self.btn_start.setEnabled(False)
        self.btn_open_html.setEnabled(False)
        self.btn_open_csv.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_text.clear()
        
        # 获取分析参数
        app_roi = self.get_app_roi()
        frame_step = self.frame_step_spin.currentData()
        treal_format = self.treal_format_combo.currentData()
        
        # 获取分析帧数
        from PyQt5.QtCore import Qt
        if self.full_analysis_check.isChecked():
            frame_limit = float('inf')
            mode_desc = "全量分析（整个视频）"
        else:
            frame_limit = self.frame_limit_spin.value()
            mode_desc = f"分析前 {frame_limit} 帧"
        
        # 检查网络日志
        enable_network = self.radio_network_yes.isChecked()
        phone_log = self.phone_log_path if enable_network else None
        pc_log = self.pc_log_path if enable_network else None
        
        # 日志输出
        self.logger.info(f"开始分析: frame_limit={frame_limit}, frame_step={frame_step}, treal_format={treal_format}")
        self.append_log(f"分析模式: {mode_desc}")
        self.append_log(f"抽帧间隔: 每{frame_step}帧")
        format_name = "标准格式" if treal_format == "standard" else "纯数字格式"
        self.append_log(f"T_real格式: {format_name}")
        
        if enable_network:
            if phone_log:
                self.append_log(f"手机日志: {Path(phone_log).name}")
            if pc_log:
                self.append_log(f"电脑日志: {Path(pc_log).name}")
            self.append_log("将生成网络关联分析报告")
        
        self.worker = AnalysisWorker(
            self.video_path, 
            app_roi, 
            self.use_gpu, 
            self.resize_ratio,
            frame_limit,
            frame_step,
            treal_format,
            self.output_dir,  # 传递输出路径
            phone_log,  # 传递手机日志路径
            pc_log  # 传递电脑日志路径
        )
        self.worker.progress.connect(self.update_progress)
        self.worker.log_message.connect(self.append_log)
        self.worker.finished.connect(self.analysis_finished)
        self.worker.start()
    
    def update_progress(self, current, total):
        """更新进度"""
        progress = int((current / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(progress)
    
    def append_log(self, message):
        """添加日志"""
        self.log_text.append(message)
    
    def analysis_finished(self, success, message, report_folder):
        """分析完成"""
        self.btn_start.setEnabled(True)
        
        if success:
            self.report_folder = report_folder
            self.btn_open_html.setEnabled(True)
            self.btn_open_csv.setEnabled(True)
            QMessageBox.information(self, "完成", f"分析完成!\n\n{message}")
        else:
            QMessageBox.critical(self, "错误", f"分析失败\n\n{message}")
    
    def open_html_report(self):
        """打开HTML报告"""
        if self.report_folder:
            report_folder = Path(self.report_folder)
            folder_name = report_folder.name
            html_path = report_folder / f"{folder_name}.html"
            if html_path.exists():
                subprocess.run(["explorer", str(html_path.resolve())])
            else:
                QMessageBox.warning(self, "提示", "HTML报告文件不存在")
        else:
            QMessageBox.warning(self, "提示", "请先完成分析")
    
    def open_csv_report(self):
        """打开报告文件夹"""
        if self.report_folder:
            report_folder = Path(self.report_folder)
            if report_folder.exists():
                subprocess.run(["explorer", str(report_folder.resolve())])
            else:
                QMessageBox.warning(self, "提示", "报告文件夹不存在")
        else:
            QMessageBox.warning(self, "提示", "请先完成分析")
    
    def open_log_file(self):
        """打开日志文件"""
        log_file = get_log_file()
        if log_file.exists():
            subprocess.run(["explorer", "/select,", str(log_file.resolve())])
        else:
            QMessageBox.warning(self, "提示", f"日志文件不存在:\n{log_file}")

