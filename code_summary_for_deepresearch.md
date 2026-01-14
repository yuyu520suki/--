# RC 框架优化系统 - 代码库分析报告 (v2.0)

## 1. 项目概况
本项目是一个针对钢筋混凝土（RC）框架的自动结构设计与优化系统。它利用遗传算法（GA）在确保符合中国国家标准（GB 50010-2010, GB 55001-2021）的前提下，寻找梁和柱最具成本效益的截面配置。

v2.0 版本采用标准 Python 包结构，所有功能模块整合在 `src/` 目录下。

## 2. 代码库结构

```
c:/Users/tw/Desktop/毕设/
├── src/                    # 核心源代码包
│   ├── models/             # 数据模型
│   │   ├── data_models.py         # GridInput, OptimizationResult
│   │   ├── structure_model.py     # anaStruct 封装
│   │   └── load_combinations.py   # 荷载组合生成
│   ├── calculation/        # 力学计算
│   │   ├── capacity_calculator.py # P-M曲线、承载力
│   │   └── section_database.py    # 77种RC截面
│   ├── optimization/       # 优化算法
│   │   └── optimizer.py           # PyGAD 遗传算法
│   ├── analysis/           # 验证系统
│   │   ├── analyzer.py            # 截面验证器
│   │   ├── model_validator.py     # 综合验证
│   │   ├── equilibrium_check.py   # 全局平衡
│   │   ├── symmetry_check.py      # 对称性
│   │   ├── deformation_check.py   # 变形协调
│   │   └── monte_carlo_test.py    # 蒙特卡洛
│   ├── utils/              # 工具
│   │   └── report_generator.py    # 报告生成
│   └── gui/                # 界面
│       └── gui_main.py            # Tkinter GUI
├── output/                 # 优化结果
├── main.py                 # 命令行入口
└── run_gui.py              # GUI 入口
```

## 3. 模块分析

### 3.1 截面数据库 (`src/calculation/section_database.py`)
- 搜索空间：200x300mm 到 500x800mm，步长 50mm
- 成本估算：混凝土 $500/m³ + 钢筋 $5.5/kg + 模板 $50/m²
- 刚度处理：梁 0.35 Ig，柱 0.70 Ig

### 3.2 承载力计算器 (`src/calculation/capacity_calculator.py`)
- 抗弯 (M)：矩形截面精确解
- 抗剪 (V)：Vc + Vs 公式
- P-M 曲线：控制点算法，精确生成柱承载力包络

### 3.3 结构建模 (`src/models/structure_model.py`)
- 封装 anaStruct 2D 矩阵位移法求解器
- 6组分组策略：减少搜索空间至 6 个基因

### 3.4 优化器 (`src/optimization/optimizer.py`)
- 适应度：F = 1 / (Cost × (1 + Penalty)^α)
- 自适应惩罚和变异率

### 3.5 验证系统 (`src/analysis/`)
- 4项独立检查 + 综合验证主程序
- 蒙特卡洛基准测试确保统计稳定性

## 4. 技术亮点

1. **工程严谨性**：P-M 相互作用曲线精确验算
2. **计算效率**：分组编码 + P-M 缓存
3. **鲁棒优化**：自适应惩罚/变异
4. **端到端自动化**：输入网格 → 输出报告

## 5. 版本历史

- **v2.0 (2026-01-14)**: 项目结构重构，GB 55001-2021 合规
- **v1.x (Phase 4C)**: 功能开发完成

## 6. 结论
该系统正确实现了结构优化的完整循环（建模 → 分析 → 验算 → 优化）。模块化架构允许轻松升级组件。
