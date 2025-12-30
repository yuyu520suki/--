# 钢筋混凝土框架结构自动优化设计系统 (RC Frame Optimization System)

本项目是一个基于 Python 的自动化结构设计与优化工具，专为钢筋混凝土（RC）框架开发。它利用遗传算法（Genetic Algorithm）在满足**GB 50010-2010 混凝土结构设计规范**的前提下，自动寻找梁柱截面的最优经济组合。

## 项目特点

*   **全自动流程**：实现“建模 -> 分析 -> 验算 -> 优化 -> 报告”的全链路自动化。
*   **智能优化**：基于 `pygad` 的遗传算法，支持自适应惩罚和变异策略，有效解决有约束优化问题。
*   **规范集成**：内置符合 GB 50010-2010 的承载力计算引擎，支持柱的双向压弯（P-M曲线）验算。
*   **高效计算**：采用截面分组策略和 P-M 曲线缓存技术，大幅提升计算效率。
*   **丰富输出**：自动生成 Word 计算书、Excel 详细报表以及内力图、收敛曲线等可视化图表。

## 目录结构

```
.
├── phase1/                  # 基础层：截面库与规范算法
├── phase2/                  # 原型层：参数化建模测试
├── phase3/                  # 逻辑层：优化算法原型
├── phase4/                  # **生产层：核心主程序**
├── output/                  # 输出目录：生成的报告和图表
└── code_summary_for_deepresearch.md # 项目详细技术报告
```

## 快速开始

### 环境依赖

本项目主要依赖以下 Python 库：
- `numpy`
- `matplotlib`
- `shapely` (几何计算)
- `anastruct` (结构分析)
- `pygad` (遗传算法)
- `pandas`, `openpyxl` (Excel 处理)
- `python-docx`, `docxtpl` (Word 报告)

### 运行程序

项目的核心入口位于 `phase4` 目录。

```bash
cd phase4
python main.py
```

运行后，程序将：
1. 初始化结构模型和截面数据库。
2. 启动遗传算法进行迭代优化。
3. 实时打印优化代数和适应度。
4. 优化完成后，在 `../output/` 目录下生成最终的设计报告和图表。

## 技术文档

关于项目的详细技术实现、模块分析及算法原理，请参阅 [code_summary_for_deepresearch.md](./code_summary_for_deepresearch.md)。
