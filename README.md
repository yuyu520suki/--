# RC Frame Optimization System (Phase 4C)
基于遗传算法的钢筋混凝土框架结构优化系统

## 项目简介
本项目是一个针对钢筋混凝土（RC）框架结构的自动化优化设计系统。它利用遗传算法（Genetic Algorithm）在满足中国国家规范（GB 50010, GB 50009）的前提下，寻找造价最低的截面配置方案。

**当前版本**: Phase 4C (GUI增强版)

## 核心功能

### 1. 智能优化核心
- **遗传算法引擎**: 基于 `PyGAD` 库，采用改进的遗传策略。
- **6基因分组编码**: 
    - 针对框架结构特点，将构件分为6组独立控制：
    1. **标准层梁** (Standard Beams)
    2. **屋面梁** (Roof Beams)
    3. **底层柱** (Bottom Columns) - 控制最大轴力
    4. **标准层角柱** (Standard Corner Columns)
    5. **标准层内柱** (Standard Interior Columns)
    6. **顶层柱** (Top Columns)
- **防早熟策略**: 
    - 高变异率 (35%)
    - 轮盘赌选择 (Roulette Wheel Selection)
    - 均匀交叉 (Uniform Crossover)
    - 动态自适应惩罚系数

### 2. 精确结构分析
- **有限元分析**: 集成 `anaStruct` 进行2D框架分析。
- **荷载模拟**: 
    - 恒载 (Dead Load)
    - 活载 (Live Load)
    - 风荷载 (Wind Load)
    - 雪荷载 (Snow Load)
    - 自动生成 SLS/ULS 荷载组合 (1.2D+1.4L等)

### 3. 工程合规性验算
- **规范标准**: 严格遵循 GB 50010-2010 (混凝土结构设计规范)。
- **验算项目**:
    - 正截面承载力 (P-M 曲线交互作用)
    - 斜截面受剪承载力
    - 构造配筋率检查
    - 轴压比限值检查
    - 强柱弱梁检查
    - 裂缝宽度验算 (SLS)
    - 挠度验算 (SLS)

### 4. 可视化交互界面 (GUI)
- **参数配置**: 交互式输入轴网尺寸、荷载参数。
- **实时预览**: 动态显示2D框架几何模型。
- **结果展示**: 
    - 实时显示最优造价与截面配置。
    - 一键生成设计计算书。
    - 查看内力图、P-M曲线、收敛曲线。

### 5. 自动化报告
- **Word 计算书**: 生成包含设计依据、计算过程、结果汇总的完整设计文档。
- **Excel 报表**: 详细的构件内力与验算结果数据。
- **专业图表**: 自动绘制框架内力包络图、柱P-M相关曲线、造价收敛曲线。

## 快速开始

### 环境依赖
```bash
pip install pygad anastruct matplotlib pandas python-docx openpyxl numpy
```

### 运行程序
启动图形化界面：
```bash
python -m phase4.gui_main
```

### 使用流程
1. 在左侧面板设置**轴网参数**（跨数、层数、层高）和**荷载参数**。
2. 点击 **"更新预览"** 确认模型几何。
3. 点击 **"▶ 运行优化"** 开始计算（建议观察进度条）。
4. 优化完成后，结果面板显示最优造价。
5. 点击 **"📄 打开计算书"** 查看详细设计报告。

## 文件结构
- `phase4/`
  - `gui_main.py`: GUI主程序入口
  - `optimizer.py`: 遗传算法优化器核心
  - `structure_model.py`: 结构建模与分析类
  - `section_verifier.py`: 截面验算与规范检查
  - `report_generator.py`: 报告生成器
  - `data_models.py`: 数据结构定义
  - `load_combinations.py`: 荷载组合生成
- `phase1/section_database.py`: 截面数据库

## 更新日志
- **2025-12-30**: 
    - 实现完整GUI界面。
    - 升级为6基因分组编码，大幅提升搜索空间与解的质量。
    - 修复早熟收敛问题。
    - 优化弯矩图绘制逻辑（数值显示修复）。
