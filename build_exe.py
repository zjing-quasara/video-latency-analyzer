"""
视频延时分析工具 - 打包脚本
解决PaddleOCR打包问题
"""
import os
import sys
import shutil
import subprocess
from pathlib import Path

def clean_build():
    """清理构建目录"""
    print("清理旧的构建文件...")
    dirs_to_clean = ['build', 'dist']
    for dir_name in dirs_to_clean:
        if Path(dir_name).exists():
            shutil.rmtree(dir_name)
            print(f"  已删除: {dir_name}")
    
    # 清理spec文件
    for spec_file in Path('.').glob('*.spec'):
        spec_file.unlink()
        print(f"  已删除: {spec_file}")

def find_paddle_libs():
    """查找paddle库文件"""
    print("\n检查Paddle库文件...")
    try:
        import paddle
        paddle_path = Path(paddle.__file__).parent
        print(f"  Paddle路径: {paddle_path}")
        
        # 查找libs目录
        libs_dir = paddle_path / "libs"
        if libs_dir.exists():
            print(f"  找到libs目录: {libs_dir}")
            return str(libs_dir)
        else:
            print(f"  警告: libs目录不存在")
            return None
    except Exception as e:
        print(f"  错误: 无法导入paddle - {e}")
        return None

def find_paddleocr_files():
    """查找paddleocr相关文件"""
    print("\n检查PaddleOCR文件...")
    try:
        import paddleocr
        paddleocr_path = Path(paddleocr.__file__).parent
        print(f"  PaddleOCR路径: {paddleocr_path}")
        return str(paddleocr_path)
    except Exception as e:
        print(f"  错误: 无法导入paddleocr - {e}")
        return None

def create_hook_file():
    """创建PyInstaller hook文件"""
    print("\n创建PyInstaller hook文件...")
    
    # 创建hooks目录
    hooks_dir = Path("pyinstaller_hooks")
    hooks_dir.mkdir(exist_ok=True)
    
    # hook-paddle.py
    paddle_hook = hooks_dir / "hook-paddle.py"
    paddle_hook.write_text("""# -*- coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files

# 收集所有paddle模块
datas, binaries, hiddenimports = collect_all('paddle')

# 额外的隐藏导入
hiddenimports += [
    'paddle.fluid',
    'paddle.fluid.core',
    'paddle.fluid.core_avx',
    'paddle.fluid.framework',
    'paddle.inference',
]
""", encoding='utf-8')
    print(f"  创建: {paddle_hook}")
    
    # hook-paddleocr.py
    paddleocr_hook = hooks_dir / "hook-paddleocr.py"
    paddleocr_hook.write_text("""# -*- coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files

# 收集所有paddleocr模块
datas, binaries, hiddenimports = collect_all('paddleocr')

# 收集额外的数据文件
datas += collect_data_files('paddleocr')

# 额外的隐藏导入
hiddenimports += collect_submodules('paddleocr')
""", encoding='utf-8')
    print(f"  创建: {paddleocr_hook}")
    
    return str(hooks_dir)

def build_exe():
    """打包exe"""
    print("\n开始打包...")
    
    # 清理旧文件
    clean_build()
    
    # 创建hook文件
    hooks_dir = create_hook_file()
    
    # 查找paddle库
    paddle_libs = find_paddle_libs()
    find_paddleocr_files()
    
    # 构建PyInstaller命令
    cmd = [
        'pyinstaller',
        '--onefile',
        '--windowed',
        '--name=VideoDelayAnalyzer_v1.0',
        '--add-data=models;models',
        f'--additional-hooks-dir={hooks_dir}',
        
        # 隐藏导入
        '--hidden-import=paddleocr',
        '--hidden-import=paddle',
        '--hidden-import=paddle.fluid',
        '--hidden-import=paddle.fluid.core',
        '--hidden-import=paddle.inference',
        '--hidden-import=PyQt5',
        '--hidden-import=PyQt5.QtCore',
        '--hidden-import=PyQt5.QtGui',
        '--hidden-import=PyQt5.QtWidgets',
        '--hidden-import=cv2',
        '--hidden-import=numpy',
        '--hidden-import=PIL',
        '--hidden-import=PIL.Image',
        
        # 收集所有paddle和paddleocr
        '--collect-all=paddleocr',
        '--collect-all=paddle',
        '--collect-binaries=paddle',
        '--collect-data=paddle',
        
        # 排除不需要的模块（减小体积）
        '--exclude-module=matplotlib',
        '--exclude-module=scipy',
        '--exclude-module=pandas',
        '--exclude-module=notebook',
        '--exclude-module=IPython',
        
        'main.py'
    ]
    
    # 如果找到paddle libs，添加二进制文件
    if paddle_libs:
        cmd.insert(-1, f'--add-binary={paddle_libs};paddle/libs')
    
    print("\n执行命令:")
    print(" ".join(cmd))
    print("\n" + "="*80)
    
    # 执行打包
    try:
        result = subprocess.run(cmd, check=True)
        
        if result.returncode == 0:
            print("\n" + "="*80)
            print("打包成功！")
            print(f"输出目录: {Path('dist').absolute()}")
            
            # 检查文件大小
            exe_path = Path('dist') / 'VideoDelayAnalyzer_v1.0.exe'
            if exe_path.exists():
                size_mb = exe_path.stat().st_size / (1024 * 1024)
                print(f"可执行文件: {exe_path.name} ({size_mb:.1f} MB)")
            
            # 创建分发包
            create_distribution()
            
    except subprocess.CalledProcessError as e:
        print(f"\n打包失败: {e}")
        sys.exit(1)

def create_distribution():
    """创建分发包"""
    print("\n创建分发包...")
    
    dist_folder = Path("dist") / "VideoDelayAnalyzer_v1.0_Release"
    dist_folder.mkdir(exist_ok=True)
    
    # 复制exe
    exe_file = Path("dist") / "VideoDelayAnalyzer_v1.0.exe"
    if exe_file.exists():
        shutil.copy2(exe_file, dist_folder / exe_file.name)
        print(f"  复制: {exe_file.name}")
    
    # 创建README
    readme = dist_folder / "使用说明.txt"
    readme.write_text("""视频延时分析工具 v1.0
====================================

使用说明：
1. 双击运行 VideoDelayAnalyzer_v1.0.exe
2. 选择视频文件
3. 设置ROI区域（应用内时间显示区域）
4. 点击"开始分析"
5. 分析完成后会自动打开报告文件夹

系统要求：
- Windows 10/11
- 无需安装Python或其他依赖

首次运行：
- 首次运行时可能需要下载OCR模型（约15MB）
- 请确保网络连接正常

技术支持：
如遇到问题，请将logs目录下的日志文件发送给开发者

版本信息：
- 版本：v1.0
- 构建日期：{build_date}
""".format(build_date=__import__('datetime').datetime.now().strftime("%Y-%m-%d")), 
    encoding='utf-8')
    print(f"  创建: {readme.name}")
    
    print(f"\n分发包已创建: {dist_folder.absolute()}")
    print("可以将此文件夹打包为zip分发给用户")

if __name__ == "__main__":
    print("="*80)
    print("视频延时分析工具 - 打包脚本")
    print("="*80)
    
    build_exe()

