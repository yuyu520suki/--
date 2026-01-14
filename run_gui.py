#!/usr/bin/env python
"""
RC框架优化系统 - GUI 启动脚本
"""

import sys
from pathlib import Path

# 确保项目根目录在路径中
sys.path.insert(0, str(Path(__file__).parent))

from src.gui.gui_main import main

if __name__ == "__main__":
    main()
