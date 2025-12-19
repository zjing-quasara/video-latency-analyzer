# -*- coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files

# 收集所有paddleocr模块
datas, binaries, hiddenimports = collect_all('paddleocr')

# 收集额外的数据文件
datas += collect_data_files('paddleocr')

# 额外的隐藏导入
hiddenimports += collect_submodules('paddleocr')
