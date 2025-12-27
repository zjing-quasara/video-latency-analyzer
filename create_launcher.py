"""创建单文件启动器"""
import os
import sys
import shutil
import zipfile
from pathlib import Path

# 检查文件夹版本是否存在
source_dir = Path("dist/VideoDelayAnalyzer_v1.0")
if not source_dir.exists():
    print("错误: dist/VideoDelayAnalyzer_v1.0 不存在")
    print("请先运行 onedir 打包命令")
    sys.exit(1)

print("="*60)
print("步骤1: 压缩完整应用到zip")
print("="*60)

zip_file = Path("app_bundle.zip")
print(f"正在压缩到 {zip_file}...")

with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
    for file in source_dir.rglob('*'):
        if file.is_file():
            arcname = file.relative_to(source_dir.parent)
            zf.write(file, arcname)

zip_size = zip_file.stat().st_size / (1024*1024)
print(f"压缩完成: {zip_size:.1f} MB\n")

# 创建启动器脚本
launcher_code = '''"""视频延时分析工具 - 单文件启动器"""
import sys
import os
import zipfile
import subprocess
import tempfile
import shutil
from pathlib import Path

def extract_and_run():
    """解压并运行主程序"""
    # 获取内置zip路径
    if getattr(sys, 'frozen', False):
        bundle_dir = Path(sys._MEIPASS)
    else:
        bundle_dir = Path(__file__).parent
    
    zip_path = bundle_dir / "app_bundle.zip"
    
    # 解压目录
    extract_dir = Path(tempfile.gettempdir()) / "VideoDelayAnalyzer_v1.0_runtime"
    
    # 检查是否需要解压
    main_exe = extract_dir / "VideoDelayAnalyzer_v1.0" / "VideoDelayAnalyzer_v1.0.exe"
    
    if not main_exe.exists():
        print("首次运行，正在初始化（约30秒）...")
        
        # 清理旧文件
        if extract_dir.exists():
            try:
                shutil.rmtree(extract_dir)
            except:
                pass
        
        extract_dir.mkdir(parents=True, exist_ok=True)
        
        # 解压
        print("正在解压文件，请稍候...")
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                total = len(zf.namelist())
                for i, item in enumerate(zf.namelist(), 1):
                    zf.extract(item, extract_dir)
                    if i % 500 == 0:
                        print(f"解压进度: {i}/{total}")
            print("解压完成！")
        except Exception as e:
            print(f"解压失败: {e}")
            input("按回车退出...")
            sys.exit(1)
    
    # 启动主程序
    if not main_exe.exists():
        print(f"错误: 找不到主程序")
        input("按回车退出...")
        sys.exit(1)
    
    # 以新进程启动，不等待
    subprocess.Popen([str(main_exe)], cwd=str(main_exe.parent))

if __name__ == "__main__":
    try:
        extract_and_run()
    except Exception as e:
        print(f"启动失败: {e}")
        input("按回车退出...")
'''

launcher_file = Path("launcher.py")
launcher_file.write_text(launcher_code, encoding='utf-8')
print("="*60)
print("步骤2: 创建启动器脚本")
print("="*60)
print(f"已创建: {launcher_file}\n")

print("="*60)
print("步骤3: 打包启动器为单exe")
print("="*60)
print("执行以下命令:")
print()
cmd = f'pyinstaller --onefile --console --name=VideoDelayAnalyzer --add-data="app_bundle.zip;." launcher.py'
print(cmd)
print()
print("执行中...")
os.system(cmd)

# 清理临时文件
print("\n清理临时文件...")
launcher_file.unlink()
zip_file.unlink()
shutil.rmtree("build", ignore_errors=True)
if Path("launcher.spec").exists():
    Path("launcher.spec").unlink()

print("\n" + "="*60)
print("完成！")
print("="*60)
final_exe = Path("dist/VideoDelayAnalyzer.exe")
if final_exe.exists():
    size = final_exe.stat().st_size / (1024*1024)
    print(f"单文件exe: {final_exe}")
    print(f"大小: {size:.1f} MB")
    print()
    print("使用说明:")
    print("- 首次运行会解压文件（约30秒）")
    print("- 解压到临时目录，不占用安装空间")
    print("- 后续运行直接启动，无需再解压")
else:
    print("错误: 打包失败")

