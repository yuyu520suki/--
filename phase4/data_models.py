"""
数据模型模块 - 标准化数据契约
使用 dataclass 定义结构分析的输入输出格式
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
import numpy as np


@dataclass
class GridInput:
    """
    轴网输入数据
    
    Attributes:
        x_spans: 开间列表 [mm], 如 [6000, 6000, 6000] 表示3跨
        z_heights: 层高列表 [mm], 如 [4000, 3500, 3500] 表示3层
        q_dead: 恒载 (kN/m), 默认 25.0
        q_live: 活载 (kN/m), 默认 10.0
    
    Example:
        >>> grid = GridInput(
        ...     x_spans=[6000, 6000, 6000],  # 3跨，每跨6m
        ...     z_heights=[4000, 3500, 3500, 3500, 3500]  # 5层
        ... )
    """
    x_spans: List[float]      # 开间 [mm]
    z_heights: List[float]    # 层高 [mm]
    q_dead: float = 25.0      # 恒载 (kN/m)
    q_live: float = 10.0      # 活载 (kN/m)
    
    @property
    def num_spans(self) -> int:
        """跨数"""
        return len(self.x_spans)
    
    @property
    def num_stories(self) -> int:
        """层数"""
        return len(self.z_heights)
    
    @property
    def total_width(self) -> float:
        """总宽度 (mm)"""
        return sum(self.x_spans)
    
    @property
    def total_height(self) -> float:
        """总高度 (mm)"""
        return sum(self.z_heights)
    
    @property
    def num_nodes(self) -> int:
        """节点总数: (跨数+1) × (层数+1)"""
        return (self.num_spans + 1) * (self.num_stories + 1)
    
    @property
    def num_beams(self) -> int:
        """梁总数: 跨数 × 层数"""
        return self.num_spans * self.num_stories
    
    @property
    def num_columns(self) -> int:
        """柱总数: (跨数+1) × 层数"""
        return (self.num_spans + 1) * self.num_stories


@dataclass
class ElementForces:
    """
    单元内力结果
    
    Attributes:
        element_id: 单元编号
        element_type: 单元类型 ('beam' 或 'column')
        length: 单元长度 (mm)
        axial_max: 最大轴力 (kN), 压力为正
        axial_min: 最小轴力 (kN)
        shear_max: 最大剪力 (kN)
        shear_min: 最小剪力 (kN)
        moment_max: 最大弯矩 (kN·m)
        moment_min: 最小弯矩 (kN·m)
    """
    element_id: int
    element_type: str           # 'beam' 或 'column'
    length: float               # 单元长度 (mm)
    axial_max: float = 0.0      # 最大轴力 N (kN)
    axial_min: float = 0.0      # 最小轴力 N (kN)
    shear_max: float = 0.0      # 最大剪力 V (kN)
    shear_min: float = 0.0      # 最小剪力 V (kN)
    moment_max: float = 0.0     # 最大弯矩 M (kN·m)
    moment_min: float = 0.0     # 最小弯矩 M (kN·m)
    
    @property
    def M_design(self) -> float:
        """设计弯矩: 取绝对值最大值"""
        return max(abs(self.moment_max), abs(self.moment_min))
    
    @property
    def V_design(self) -> float:
        """设计剪力: 取绝对值最大值"""
        return max(abs(self.shear_max), abs(self.shear_min))
    
    @property
    def N_design(self) -> float:
        """设计轴力: 取绝对值最大值"""
        return max(abs(self.axial_max), abs(self.axial_min))


@dataclass
class DesignResult:
    """
    设计结果
    
    Attributes:
        element_id: 单元编号
        element_type: 单元类型
        section_id: 截面索引
        b: 截面宽度 (mm)
        h: 截面高度 (mm)
        As: 配筋面积 (mm²)
        rho: 配筋率 (%)
        utility_ratio_M: 弯矩利用率 (Mu/φMn)
        utility_ratio_V: 剪力利用率 (Vu/φVn)
        is_safe: 是否满足承载力要求
    """
    element_id: int
    element_type: str           # 'beam' 或 'column'
    section_id: int             # 截面索引
    b: float                    # 宽度 (mm)
    h: float                    # 高度 (mm)
    As: float = 0.0             # 配筋面积 (mm²)
    rho: float = 0.0            # 配筋率 (%)
    utility_ratio_M: float = 0.0  # 弯矩利用率
    utility_ratio_V: float = 0.0  # 剪力利用率
    is_safe: bool = True        # 是否安全


@dataclass
class OptimizationResult:
    """
    优化结果汇总
    
    Attributes:
        genes: 最优基因序列
        cost: 总造价 (元)
        fitness: 适应度值
        penalty: 惩罚值
        forces: 内力结果字典
        designs: 设计结果列表
        convergence_history: 收敛历史
        fitness_history: 适应度历史
    """
    genes: List[int]                           # 最优基因
    cost: float                                # 总造价 (元)
    fitness: float                             # 适应度
    penalty: float = 0.0                       # 惩罚值
    forces: Dict[int, ElementForces] = field(default_factory=dict)
    designs: List[DesignResult] = field(default_factory=list)
    convergence_history: List[float] = field(default_factory=list)
    fitness_history: List[float] = field(default_factory=list) # 新增：适应度历史


# =============================================================================
# 测试代码
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("数据模型测试")
    print("=" * 60)
    
    # 测试 GridInput
    grid = GridInput(
        x_spans=[6000, 6000, 6000],  # 3跨
        z_heights=[4000, 3500, 3500, 3500, 3500]  # 5层
    )
    
    print(f"\n轴网信息:")
    print(f"  跨数: {grid.num_spans}")
    print(f"  层数: {grid.num_stories}")
    print(f"  总宽度: {grid.total_width} mm")
    print(f"  总高度: {grid.total_height} mm")
    print(f"  节点数: {grid.num_nodes}")
    print(f"  梁数量: {grid.num_beams}")
    print(f"  柱数量: {grid.num_columns}")
    
    # 测试 ElementForces
    forces = ElementForces(
        element_id=1,
        element_type='beam',
        length=6000,
        moment_max=150.0,
        moment_min=-200.0,
        shear_max=100.0,
        shear_min=-100.0
    )
    
    print(f"\n内力示例:")
    print(f"  单元 {forces.element_id} ({forces.element_type})")
    print(f"  设计弯矩: {forces.M_design:.1f} kN·m")
    print(f"  设计剪力: {forces.V_design:.1f} kN")
    
    print("\n✓ 数据模型测试通过")
