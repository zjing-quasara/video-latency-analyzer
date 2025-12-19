# -*- coding: utf-8 -*-
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
