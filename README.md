# RC Frame Optimization System
基于遗传算法的钢筋混凝土框架结构优化系统

## 项目简介
本项目是一个针对钢筋混凝土（RC）框架结构的自动化优化设计系统。它利用遗传算法（Genetic Algorithm）在满足中国国家规范（GB 50010-2010, GB 55001-2021）的前提下，寻找造价最低的截面配置方案。

**当前版本**: v2.1 (荷载修正版) - 2026年1月15日更新

**状态**: ✅ 核心功能完成，全部验证通过

## 核心功能

### 1. 智能优化核心
- **遗传算法引擎**: 基于 `PyGAD` 库，采用改进的遗传策略
- **6基因分组编码**: 标准梁、屋面梁、底层柱、标准角柱、标准内柱、顶层柱
- **防早熟策略**: 高变异率、轮盘赌选择、均匀交叉、动态自适应惩罚
- **并行计算准备**: 已规划基于 CPU 多核的并行计算架构（待实装）

### 2. 精确结构分析
- **有限元分析**: 集成 `anaStruct` 进行2D框架分析
- **荷载模拟**: 恒载、活载、风荷载、雪荷载
- **荷载组合**: 自动生成 SLS/ULS 组合 (1.3G+1.5L 等，符合 GB 55001-2021)

### 3. 工程合规性验算
- **规范标准**: GB 50010-2010, GB 55001-2021
- **验算项目**: P-M曲线、斜截面受剪、轴压比、配筋率、强柱弱梁

### 4. 验证模块
- 全局平衡检查、对称性检查、变形协调性检查、蒙特卡洛基准测试

### 5. GUI 界面
- 参数配置、实时预览、结果展示、一键生成报告
- **智能填充**: 根据建筑类型（住宅/办公/商场等）自动填充荷载规范值

### 6. 自动化报告
- Word 计算书、Excel 报表、框架内力图、P-M曲线图、收敛曲线

## 快速开始

### 环境依赖
```bash
pip install pygad anastruct matplotlib pandas python-docx openpyxl numpy
```

### 运行程序
```bash
# 命令行优化
python main.py

# GUI 界面
python run_gui.py
# 或
python src/gui/gui_main.py
```

## 项目结构
```
Project_Root/
├── src/
│   ├── models/          # 数据模型
│   │   ├── data_models.py         # GridInput, OptimizationResult（含建筑类型数据库）
│   │   ├── structure_model.py     # 结构建模与分析
│   │   └── load_combinations.py   # 荷载组合生成
│   ├── calculation/     # 力学计算
│   │   ├── capacity_calculator.py # P-M曲线、承载力计算
│   │   └── section_database.py    # 截面数据库
│   ├── optimization/    # 遗传算法
│   │   └── optimizer.py           # GA 优化器核心
│   ├── analysis/        # 验证系统
│   │   ├── analyzer.py            # 截面验证器
│   │   ├── model_validator.py     # 综合验证主程序
│   │   ├── equilibrium_check.py   # 全局平衡检查
│   │   ├── symmetry_check.py      # 对称性检查
│   │   ├── deformation_check.py   # 变形协调性检查
│   │   └── monte_carlo_test.py    # 蒙特卡洛测试
│   ├── utils/           # 报表工具
│   │   └── report_generator.py    # Excel/Word/图表自动生成
│   └── gui/             # GUI 界面
│       └── gui_main.py            # Tkinter 主界面
├── output/              # 优化结果输出目录
├── main.py              # 命令行入口
└── run_gui.py           # GUI 启动脚本
```

## 更新日志

### 2026-01-15 (v2.1 荷载修正版)
- **严重 Bug 修复**: 修正恒载单位错误
  - `q_dead` 默认值从 25 kN/m (错误引用容重) 修正为 **4.5 kN/m²** (符合 GB 50009-2012)
  - 所有文档和 GUI 标签单位统一修正为 kN/m²
- **数据库升级**: 
  - `BUILDING_TYPES` 新增各建筑类型（办公、住宅、商场等）的规范恒载值
- **GUI 增强**: 
  - 下拉选择建筑类型时，自动联动的填充 **恒载 + 活载 + 重要性系数**
  - 分离恒载和活载单位显示

### 2026-01-14 (v2.0 重构版)
- **项目结构重构**: 整合 src 目录，统一 import 路径
- **GB 55001-2021 合规**: 默认活载 2.5 kN/m²，1.3G+1.5L 组合
- **Phase 5 验证系统完整迁移**

### 2026-01-09 (P-M曲线修复)
- P-M曲线采用Grok控制点算法，弯矩基准修正

## 许可证
MIT License
