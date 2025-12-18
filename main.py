"""
视频延时分析工具 - 启动入口
"""
# 必须在最开始设置，禁用PaddleX的模型检查（避免卡顿）
import os
os.environ['DISABLE_MODEL_SOURCE_CHECK'] = 'True'

import sys
import traceback
from PyQt5.QtWidgets import QApplication, QMessageBox
from src.gui import MainWindow
from src.utils.logger import init_logger, get_logger, get_log_file, log_exception


def main():
    """主函数"""
    # 初始化日志系统
    init_logger()
    logger = get_logger('Main')
    
    try:
        logger.info("正在启动应用...")
        
        # 检查关键依赖
        logger.info("检查依赖...")
        try:
            import cv2
            logger.info(f"[OK] OpenCV {cv2.__version__}")
        except ImportError as e:
            logger.error(f"[ERROR] OpenCV 未安装: {e}")
            raise
        
        # TODO: 时间识别引擎依赖检查
        # try:
        #     from paddleocr import PaddleOCR
        #     logger.info(f"[OK] PaddleOCR 已安装")
        # except ImportError as e:
        #     logger.error(f"[ERROR] PaddleOCR 未安装: {e}")
        #     raise
        
        try:
            from PyQt5 import QtCore
            logger.info(f"[OK] PyQt5 {QtCore.QT_VERSION_STR}")
        except ImportError as e:
            logger.error(f"[ERROR] PyQt5 未安装: {e}")
            raise
        
        logger.info("所有依赖检查通过")
        
        # 修复Qt平台插件问题
        logger.info("配置Qt环境...")
        try:
            # 获取PyQt5的安装路径
            import PyQt5
            pyqt5_path = os.path.dirname(PyQt5.__file__)
            qt_plugin_path = os.path.join(pyqt5_path, 'Qt5', 'plugins')
            
            # 设置Qt插件路径
            if os.path.exists(qt_plugin_path):
                os.environ['QT_PLUGIN_PATH'] = qt_plugin_path
                logger.info(f"[OK] Qt插件路径已设置: {qt_plugin_path}")
            else:
                # 尝试备用路径
                qt_plugin_path = os.path.join(pyqt5_path, 'Qt', 'plugins')
                if os.path.exists(qt_plugin_path):
                    os.environ['QT_PLUGIN_PATH'] = qt_plugin_path
                    logger.info(f"[OK] Qt插件路径已设置: {qt_plugin_path}")
                else:
                    logger.warning(f"⚠ 未找到Qt插件路径，将使用系统默认路径")
            
            # 设置Qt平台插件环境变量（备用方案）
            os.environ['QT_QPA_PLATFORM_PLUGIN_PATH'] = qt_plugin_path if os.path.exists(qt_plugin_path) else ''
            
        except Exception as e:
            logger.warning(f"配置Qt环境时出现警告: {e}")
        
        # 创建应用
        app = QApplication(sys.argv)
        logger.info("QApplication 已创建")
        
        # 创建主窗口
        window = MainWindow()
        logger.info("主窗口已创建")
        
        window.show()
        logger.info("应用启动成功")
        
        # 运行应用
        sys.exit(app.exec_())
        
    except Exception as e:
        logger.error("应用启动失败！")
        log_exception("详细错误信息:")
        
        # 显示错误对话框
        error_msg = f"""应用启动失败！

错误信息：
{str(e)}

请将以下日志文件发送给开发者：
{get_log_file()}

详细错误：
{traceback.format_exc()}
"""
        try:
            app = QApplication.instance()
            if app is None:
                app = QApplication(sys.argv)
            QMessageBox.critical(None, "启动失败", error_msg)
        except:
            print(error_msg)
        
        sys.exit(1)


if __name__ == "__main__":
    main()


