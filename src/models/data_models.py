"""
数据模型模块 - 标准化数据契约
使用 dataclass 定义结构分析的输入输出格式

更新日志:
    2026-01: 活载默认值调整为 2.5 kN/m² (GB 55001-2021)
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import numpy as np


# =============================================================================
# 建筑功能分类数据库 (GB 50009-2012 表5.1.1 / GB 55001-2021)
# =============================================================================

BUILDING_TYPES: Dict[str, Dict] = {
    # 格式: {q_dead: 楼面恒荷载(kN/m²), q_live: 楼面活荷载(kN/m²), gamma_0: 结构重要性系数, psi_c: 组合值系数}
    # q_dead 参考 GB 50009-2012 附录A，含楼板自重+装修层+吊顶
    # q_live 参考 GB 55001-2021 表 4.2.2
    # 典型组成: 120mm楼板(3.0) + 装修面层(1.0) + 吊顶(0.5) = 4.5 kN/m²
    "住宅": {"q_dead": 4.0, "q_live": 2.0, "gamma_0": 1.0, "psi_c": 0.7, "psi_q": 0.4, "desc": "住宅、宿舍"},
    "办公": {"q_dead": 4.5, "q_live": 2.5, "gamma_0": 1.0, "psi_c": 0.7, "psi_q": 0.5, "desc": "办公楼、教室"},
    "教学楼": {"q_dead": 4.5, "q_live": 2.5, "gamma_0": 1.1, "psi_c": 0.7, "psi_q": 0.5, "desc": "学校教学楼(重点设防类)"},
    "医院": {"q_dead": 5.0, "q_live": 2.0, "gamma_0": 1.1, "psi_c": 0.7, "psi_q": 0.4, "desc": "医院病房(表4.2.2项1(1))"},
    "商场": {"q_dead": 5.0, "q_live": 4.0, "gamma_0": 1.0, "psi_c": 0.7, "psi_q": 0.5, "desc": "商店、展览厅(表4.2.2项4)"},
    "档案馆": {"q_dead": 5.5, "q_live": 5.0, "gamma_0": 1.1, "psi_c": 0.9, "psi_q": 0.8, "desc": "档案馆、图书馆书库"},
    "工业厂房": {"q_dead": 4.0, "q_live": 7.0, "gamma_0": 1.0, "psi_c": 0.8, "psi_q": 0.5, "desc": "轻型机械加工(表4.2.7)"},
    "仓库": {"q_dead": 4.0, "q_live": 5.0, "gamma_0": 1.0, "psi_c": 0.9, "psi_q": 0.8, "desc": "一般仓库"},
}


# =============================================================================
# 中国典型地区参数数据库 (GB 50011-2010 / GB 50009-2012)
# =============================================================================

REGION_PARAMS: Dict[str, Dict] = {
    # 格式: {alpha_max: 地震影响系数最大值, w0: 基本风压(kN/m²), s0: 基本雪压(kN/m²), intensity: 设防烈度}
    "北京": {"alpha_max": 0.08, "w0": 0.45, "s0": 0.40, "intensity": 8, "desc": "华北地区"},
    "上海": {"alpha_max": 0.08, "w0": 0.55, "s0": 0.20, "intensity": 7, "desc": "长三角沿海"},
    "广州": {"alpha_max": 0.08, "w0": 0.50, "s0": 0.00, "intensity": 7, "desc": "华南地区"},
    "深圳": {"alpha_max": 0.08, "w0": 0.75, "s0": 0.00, "intensity": 7, "desc": "华南沿海"},
    "成都": {"alpha_max": 0.10, "w0": 0.30, "s0": 0.10, "intensity": 7, "desc": "西南地区"},
    "重庆": {"alpha_max": 0.05, "w0": 0.40, "s0": 0.10, "intensity": 6, "desc": "西南地区"},
    "西安": {"alpha_max": 0.12, "w0": 0.35, "s0": 0.25, "intensity": 8, "desc": "西北地区"},
    "武汉": {"alpha_max": 0.05, "w0": 0.40, "s0": 0.30, "intensity": 6, "desc": "华中地区"},
    "南京": {"alpha_max": 0.08, "w0": 0.45, "s0": 0.40, "intensity": 7, "desc": "长三角"},
    "杭州": {"alpha_max": 0.05, "w0": 0.45, "s0": 0.35, "intensity": 6, "desc": "长三角"},
    "天津": {"alpha_max": 0.12, "w0": 0.50, "s0": 0.35, "intensity": 8, "desc": "华北沿海"},
    "沈阳": {"alpha_max": 0.08, "w0": 0.55, "s0": 0.50, "intensity": 7, "desc": "东北地区"},
    "哈尔滨": {"alpha_max": 0.05, "w0": 0.50, "s0": 0.70, "intensity": 6, "desc": "东北寒冷区"},
    "昆明": {"alpha_max": 0.16, "w0": 0.30, "s0": 0.15, "intensity": 8, "desc": "西南高原"},
    "兰州": {"alpha_max": 0.12, "w0": 0.35, "s0": 0.20, "intensity": 8, "desc": "西北地区"},
    "六安": {"alpha_max": 0.08, "w0": 0.35, "s0": 0.55, "intensity": 7, "desc": "安徽中部"},
    "自定义": {"alpha_max": 0.0, "w0": 0.0, "s0": 0.0, "intensity": 0, "desc": "用户自定义参数"},
}


def get_building_params(building_type: str) -> Dict:
    """
    获取建筑类型对应的参数
    
    Args:
        building_type: 建筑类型名称
        
    Returns:
        dict: {q_live, gamma_0, psi_c}
    """
    return BUILDING_TYPES.get(building_type, BUILDING_TYPES["住宅"])


def get_region_params(region: str) -> Dict:
    """
    获取地区对应的参数
    
    Args:
        region: 地区名称
        
    Returns:
        dict: {alpha_max, w0, s0, intensity}
    """
    return REGION_PARAMS.get(region, REGION_PARAMS["自定义"])


@dataclass
class GridInput:
    """
    轴网输入数据
    
    Attributes:
        x_spans: 开间列表 [mm], 如 [6000, 6000, 6000] 表示3跨
        z_heights: 层高列表 [mm], 如 [4000, 3500, 3500] 表示3层
        q_dead: 恒载 (kN/m²), 默认 4.5 (含楼板+装修+吊顶)
        q_live: 活载 (kN/m²), 默认 2.5
    
    Example:
        >>> grid = GridInput(
        ...     x_spans=[6000, 6000, 6000],  # 3跨，每跨6m
        ...     z_heights=[4000, 3500, 3500, 3500, 3500]  # 5层
        ... )
    """
    x_spans: List[float]      # 开间 [mm]
    z_heights: List[float]    # 层高 [mm]
    q_dead: float = 4.5       # 恒载 (kN/m²)，参考GB 50009-2012
    q_live: float = 2.5       # 活载 (kN/m²)
    q_roof: float = 0.5       # 屋顶活载 (kN/m²), GB 50009-2012: 不上人0.5, 上人2.0
    # 注：恒载4.5 kN/m² 典型组成 = 120mm楼板(3.0) + 装修面层(1.0) + 吊顶(0.5)
    
    # 风荷载和雪荷载参数 (可选)
    w0: float = 0.0           # 基本风压 (kN/m²), 0表示不考虑
    s0: float = 0.0           # 基本雪压 (kN/m²), 0表示不考虑
    terrain: str = 'B'        # 地面粗糙度类别 (A/B/C/D)
    
    # 地震荷载参数 (可选, GB 50011-2010)
    alpha_max: float = 0.0    # 水平地震影响系数最大值, 0表示不考虑地震
    seismic_group: str = '2'  # 设计地震分组 (1/2/3)
    
    # 建筑功能与地区参数 (可选)
    building_type: str = '办公'  # 建筑功能类型 (住宅/办公/教学楼/医院/商场/档案馆/工业厂房/仓库)
    region: str = '自定义'       # 项目所在地区 (北京/上海/广州/...)
    gamma_0: float = 1.0         # 结构重要性系数 (GB 50068)
    
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
    
    @property
    def has_wind(self) -> bool:
        """是否考虑风荷载"""
        return self.w0 > 0
    
    @property
    def has_snow(self) -> bool:
        """是否考虑雪荷载 (仅施加于屋面梁)"""
        return self.s0 > 0
    
    @property
    def has_seismic(self) -> bool:
        """是否考虑地震作用"""
        return self.alpha_max > 0
    
    @classmethod
    def from_presets(cls, 
                     x_spans: List[float],
                     z_heights: List[float],
                     building_type: str = "办公",
                     region: str = "自定义",
                     q_dead: float = None,
                     **overrides) -> 'GridInput':
        """
        从预设数据库创建 GridInput，自动填充建筑和地区参数
        
        Args:
            x_spans: 开间列表 [mm]
            z_heights: 层高列表 [mm]
            building_type: 建筑功能类型
            region: 项目所在地区
            q_dead: 恒载 (kN/m²)，若为None则从建筑类型数据库获取
            **overrides: 覆盖默认参数
            
        Returns:
            GridInput: 配置好的轴网输入对象
        """
        # 从数据库获取建筑参数
        bldg_params = get_building_params(building_type)
        region_params = get_region_params(region)
        
        # 合并参数 (用户指定的 overrides 优先)
        params = {
            'x_spans': x_spans,
            'z_heights': z_heights,
            'q_dead': q_dead if q_dead is not None else bldg_params['q_dead'],
            'q_live': bldg_params['q_live'],
            'gamma_0': bldg_params['gamma_0'],
            'building_type': building_type,
            'region': region,
            'w0': region_params['w0'],
            's0': region_params['s0'],
            'alpha_max': region_params['alpha_max'],
        }
        params.update(overrides)
        
        return cls(**params)
    
    def apply_building_preset(self, building_type: str) -> None:
        """根据建筑类型自动设置 q_dead, q_live 和 gamma_0 (就地修改)"""
        params = get_building_params(building_type)
        self.building_type = building_type
        self.q_dead = params['q_dead']
        self.q_live = params['q_live']
        self.gamma_0 = params['gamma_0']
    
    def apply_region_preset(self, region: str) -> None:
        """根据地区自动设置 w0, s0, alpha_max (就地修改)"""
        params = get_region_params(region)
        self.region = region
        self.w0 = params['w0']
        self.s0 = params['s0']
        self.alpha_max = params['alpha_max']


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
class ElementForcesEnvelope:
    """
    单元内力包络结果 (多工况分析)
    
    Attributes:
        element_id: 单元编号
        element_type: 单元类型 ('beam' 或 'column')
        length: 单元长度 (mm)
        M_uls_max: ULS最大弯矩 (kN·m)
        M_uls_min: ULS最小弯矩 (kN·m)
        V_uls_max: ULS最大剪力 (kN)
        N_uls_max: ULS最大轴力 (kN)
        N_uls_min: ULS最小轴力 (kN)
        M_sls: SLS弯矩 (准永久组合, kN·m)
        controlling_combo: 控制工况名称
    """
    element_id: int
    element_type: str
    length: float
    # ULS 控制内力
    M_uls_max: float = 0.0
    M_uls_min: float = 0.0
    V_uls_max: float = 0.0
    N_uls_max: float = 0.0
    N_uls_min: float = 0.0
    # SLS 控制内力 (准永久组合)
    M_sls: float = 0.0
    # 控制工况
    controlling_combo: str = ''
    
    @property
    def M_design(self) -> float:
        """设计弯矩: ULS最大绝对值"""
        return max(abs(self.M_uls_max), abs(self.M_uls_min))
    
    @property
    def V_design(self) -> float:
        """设计剪力"""
        return abs(self.V_uls_max)
    
    @property
    def N_design(self) -> float:
        """设计轴力: ULS最大绝对值"""
        return max(abs(self.N_uls_max), abs(self.N_uls_min))


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
    fitness_history: List[float] = field(default_factory=list)
    
    # 兼容性字段 (新版本报告需要)
    cost_history: List[float] = field(default_factory=list)
    feasible_ratio_history: List[float] = field(default_factory=list)


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
    print(f"  活载默认值: {grid.q_live} kN/m² (GB 55001-2021)")
    
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
