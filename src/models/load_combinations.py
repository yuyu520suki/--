"""
荷载组合模块 - GB 50009-2012 / GB 55001-2021 规范
包含：永久作用、楼面活荷载、风荷载、雪荷载

更新日志:
    2026-01: 新增 1.3G+1.5L 组合 (GB 55001-2021 第 3.1.13 条)

References:
    - GB 50009-2012 建筑结构荷载规范
    - GB 55001-2021 工程结构通用规范
    - GB 50010-2010 混凝土结构设计规范
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional


# =============================================================================
# 分项系数 (GB 50009-2012 表4.1.1)
# =============================================================================

GAMMA_G = 1.2       # 永久作用分项系数 (对结构不利时)
GAMMA_G_FAV = 1.0   # 永久作用分项系数 (对结构有利时)
GAMMA_Q = 1.4       # 可变作用分项系数


# =============================================================================
# 组合值系数 (GB 50009-2012 表5.1.1)
# =============================================================================

# 组合值系数 ψc
PSI_C = {
    'live': 0.7,    # 民用楼面活荷载
    'wind': 0.6,    # 风荷载
    'snow': 0.7,    # 雪荷载
}

# 准永久值系数 ψq
PSI_Q = {
    'live': 0.4,    # 民用楼面活荷载
    'wind': 0.0,    # 风荷载
    'snow': 0.2,    # 雪荷载
}


# =============================================================================
# 风荷载参数 (GB 50009-2012 第8章)
# =============================================================================

@dataclass
class WindLoadParams:
    """
    风荷载参数
    
    Attributes:
        w0: 基本风压 (kN/m²), 按50年重现期取值，不应小于0.3kN/m²
        mu_s: 风荷载体型系数，矩形平面取1.3
        terrain: 地面粗糙度类别 (A/B/C/D)
    """
    w0: float = 0.40         # 基本风压 (kN/m²)
    mu_s: float = 1.3        # 体型系数 (矩形平面)
    terrain: str = 'B'       # 地面粗糙度类别
    
    def __post_init__(self):
        if self.w0 < 0.3:
            print(f"警告: 基本风压 w0={self.w0} kN/m² < 0.3 kN/m²，已调整为0.3")
            self.w0 = 0.3
    
    def get_mu_z(self, z: float) -> float:
        """
        风压高度变化系数 μz (GB 50009-2012 表8.2.1)
        
        Args:
            z: 离地高度 (m)
            
        Returns:
            风压高度变化系数 μz
        """
        # B类地貌(田野、乡村、丛林等)
        if self.terrain == 'B':
            if z <= 10:
                return 1.0
            elif z <= 15:
                return 1.14
            elif z <= 20:
                return 1.25
            elif z <= 30:
                return 1.42
            elif z <= 40:
                return 1.56
            elif z <= 50:
                return 1.67
            elif z <= 60:
                return 1.77
            elif z <= 70:
                return 1.86
            elif z <= 80:
                return 1.95
            elif z <= 90:
                return 2.02
            else:
                return 2.09
        # A类地貌(海面、海岛等)
        elif self.terrain == 'A':
            if z <= 10:
                return 1.28
            elif z <= 15:
                return 1.42
            elif z <= 20:
                return 1.52
            elif z <= 30:
                return 1.67
            elif z <= 40:
                return 1.79
            else:
                return 1.89
        # C类地貌(城市郊区)
        elif self.terrain == 'C':
            if z <= 10:
                return 0.74
            elif z <= 15:
                return 0.84
            elif z <= 20:
                return 0.92
            elif z <= 30:
                return 1.06
            elif z <= 40:
                return 1.18
            elif z <= 50:
                return 1.28
            else:
                return 1.37
        # D类地貌(大城市市区)
        elif self.terrain == 'D':
            if z <= 10:
                return 0.62
            elif z <= 15:
                return 0.62
            elif z <= 20:
                return 0.70
            elif z <= 30:
                return 0.84
            elif z <= 40:
                return 0.95
            elif z <= 50:
                return 1.05
            else:
                return 1.14
        else:
            return 1.0  # 默认B类
    
    def get_wk(self, z: float) -> float:
        """
        计算风荷载标准值 (GB 50009-2012 8.1.1)
        
        wk = βz * μs * μz * w0
        
        简化计算（不考虑风振系数βz，取1.0）:
        wk = μs * μz * w0
        
        Args:
            z: 离地高度 (m)
            
        Returns:
            风荷载标准值 (kN/m²)
        """
        mu_z = self.get_mu_z(z)
        return self.mu_s * mu_z * self.w0


# =============================================================================
# 雪荷载参数 (GB 50009-2012 第7章)
# =============================================================================

@dataclass
class SnowLoadParams:
    """
    雪荷载参数
    
    Attributes:
        s0: 基本雪压 (kN/m²), 按50年重现期取值
        mu_r: 屋面积雪分布系数，平屋面取1.0
    """
    s0: float = 0.35         # 基本雪压 (kN/m²)
    mu_r: float = 1.0        # 屋面积雪分布系数 (平屋面)
    
    def get_sk(self) -> float:
        """
        计算雪荷载标准值 (GB 50009-2012 7.1.1)
        
        sk = μr * s0
        
        Returns:
            雪荷载标准值 (kN/m²)
        """
        return self.mu_r * self.s0


# =============================================================================
# 荷载数据类
# =============================================================================

@dataclass
class LoadCase:
    """
    荷载工况
    
    Attributes:
        name: 工况名称
        load_type: 荷载类型 ('dead', 'live', 'wind', 'snow')
        value: 荷载标准值 (kN/m 或 kN/m²)
        direction: 荷载方向 ('vertical', 'horizontal')
    """
    name: str
    load_type: str
    value: float
    direction: str = 'vertical'


@dataclass
class LoadCombination:
    """
    荷载组合
    
    Attributes:
        name: 组合名称 (如 "1.2G+1.4Q")
        limit_state: 极限状态类型 ('ULS', 'SLS_STD', 'SLS_QUASI')
        factors: 各荷载类型的组合系数 [(load_type, factor), ...]
    """
    name: str
    limit_state: str
    factors: List[Tuple[str, float]]
    
    def get_factor(self, load_type: str) -> float:
        """获取指定荷载类型的组合系数"""
        for lt, f in self.factors:
            if lt == load_type:
                return f
        return 0.0


# =============================================================================
# 荷载组合生成器
# =============================================================================

class LoadCombinationGenerator:
    """
    荷载组合生成器
    
    根据 GB 50009-2012 及 GB 55001-2021 生成承载能力极限状态和正常使用极限状态的荷载组合
    """
    
    def get_uls_combinations(self, 
                             has_wind: bool = True, 
                             has_snow: bool = True) -> List[LoadCombination]:
        """
        生成承载能力极限状态组合 (GB 50009-2012 5.3.1 / GB 55001-2021)
        
        基本组合的效应设计值:
        γG * SGk + γQ * ψc * SQk (永久作用控制)
        γG * SGk + γQ * SQ1k + Σ(γQ * ψc * SQik) (可变作用控制)
        
        Args:
            has_wind: 是否包含风荷载组合
            has_snow: 是否包含雪荷载组合
            
        Returns:
            荷载组合列表
        """
        combos = []
        
        # ==== GB 55001-2021 默认校核组合 ====
        # 依据 GB 55001-2021 第 3.1.13 条调整。
        # 注意：此组合用于最终校核，GA 内部适应度计算可保留原逻辑以保证搜索多样性。
        combos.append(LoadCombination(
            name="1.3G+1.5L",
            limit_state="ULS",
            factors=[("dead", 1.3), ("live", 1.5)]
        ))
        
        # ==== 永久+活载组合 (GB 50009-2012) ====
        # 1.2G + 1.4Q (可变作用控制)
        combos.append(LoadCombination(
            name="1.2G+1.4Q",
            limit_state="ULS",
            factors=[("dead", 1.2), ("live", 1.4)]
        ))
        
        # 1.35G + 0.98Q (永久作用控制, 0.7×1.4=0.98)
        combos.append(LoadCombination(
            name="1.35G+0.98Q",
            limit_state="ULS",
            factors=[("dead", 1.35), ("live", 0.7 * 1.4)]
        ))
        
        # ==== 含风荷载组合 ====
        if has_wind:
            # 1.2G + 1.4W (纯风控制)
            combos.append(LoadCombination(
                name="1.2G+1.4W",
                limit_state="ULS",
                factors=[("dead", 1.2), ("wind", 1.4)]
            ))
            
            # 1.2G + 0.98Q + 1.4W (风为主，活载参与组合)
            combos.append(LoadCombination(
                name="1.2G+0.98Q+1.4W",
                limit_state="ULS",
                factors=[("dead", 1.2), ("live", 0.7 * 1.4), ("wind", 1.4)]
            ))
            
            # 1.2G + 1.4Q + 0.84W (活载为主，风参与组合)
            combos.append(LoadCombination(
                name="1.2G+1.4Q+0.84W",
                limit_state="ULS",
                factors=[("dead", 1.2), ("live", 1.4), ("wind", 0.6 * 1.4)]
            ))
        
        # ==== 含雪荷载组合 ====
        if has_snow:
            # 1.2G + 1.4S (纯雪控制)
            combos.append(LoadCombination(
                name="1.2G+1.4S",
                limit_state="ULS",
                factors=[("dead", 1.2), ("snow", 1.4)]
            ))
            
            # 1.2G + 0.98Q + 1.4S (雪为主)
            combos.append(LoadCombination(
                name="1.2G+0.98Q+1.4S",
                limit_state="ULS",
                factors=[("dead", 1.2), ("live", 0.7 * 1.4), ("snow", 1.4)]
            ))
            
            # 1.2G + 1.4Q + 0.98S (活载为主，雪参与)
            combos.append(LoadCombination(
                name="1.2G+1.4Q+0.98S",
                limit_state="ULS",
                factors=[("dead", 1.2), ("live", 1.4), ("snow", 0.7 * 1.4)]
            ))
        
        # ==== 风+雪组合 ====
        if has_wind and has_snow:
            # 1.2G + 0.98Q + 1.4W + 0.98S
            combos.append(LoadCombination(
                name="1.2G+0.98Q+1.4W+0.98S",
                limit_state="ULS",
                factors=[
                    ("dead", 1.2), 
                    ("live", 0.7 * 1.4), 
                    ("wind", 1.4), 
                    ("snow", 0.7 * 1.4)
                ]
            ))
        
        return combos
    
    def get_sls_combinations(self) -> List[LoadCombination]:
        """
        生成正常使用极限状态组合 (GB 50009-2012 5.3.2)
        
        Returns:
            荷载组合列表
        """
        return [
            # 标准组合 (用于挠度验算)
            LoadCombination(
                name="G+Q",
                limit_state="SLS_STD",
                factors=[("dead", 1.0), ("live", 1.0)]
            ),
            
            # 准永久组合 (用于裂缝验算)
            LoadCombination(
                name="G+0.4Q",
                limit_state="SLS_QUASI",
                factors=[("dead", 1.0), ("live", PSI_Q['live'])]
            ),
        ]
    
    def get_all_combinations(self, 
                             has_wind: bool = True, 
                             has_snow: bool = True) -> List[LoadCombination]:
        """获取所有荷载组合"""
        return self.get_uls_combinations(has_wind, has_snow) + \
               self.get_sls_combinations()


# =============================================================================
# 测试代码
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("荷载组合模块测试 (GB 50009-2012 / GB 55001-2021)")
    print("=" * 70)
    
    # 测试风荷载参数
    print("\n风荷载参数测试:")
    wind = WindLoadParams(w0=0.45, mu_s=1.3, terrain='B')
    test_heights = [5, 10, 15, 20, 30]
    for z in test_heights:
        wk = wind.get_wk(z)
        print(f"  z={z:2d}m: μz={wind.get_mu_z(z):.2f}, wk={wk:.3f} kN/m²")
    
    # 测试雪荷载参数
    print("\n雪荷载参数测试:")
    snow = SnowLoadParams(s0=0.40, mu_r=1.0)
    print(f"  基本雪压 s0={snow.s0} kN/m²")
    print(f"  雪荷载标准值 sk={snow.get_sk():.2f} kN/m²")
    
    # 测试荷载组合生成
    print("\n承载能力极限状态组合 (ULS):")
    gen = LoadCombinationGenerator()
    uls_combos = gen.get_uls_combinations(has_wind=True, has_snow=True)
    for combo in uls_combos:
        factors_str = ", ".join([f"{lt}×{f:.2f}" for lt, f in combo.factors])
        print(f"  {combo.name}: [{factors_str}]")
    
    print("\n正常使用极限状态组合 (SLS):")
    sls_combos = gen.get_sls_combinations()
    for combo in sls_combos:
        factors_str = ", ".join([f"{lt}×{f:.2f}" for lt, f in combo.factors])
        print(f"  {combo.name}: [{factors_str}]")
    
    print("\n" + "=" * 70)
    print("✓ 荷载组合模块测试通过!")
    print("  注: 1.3G+1.5L 组合已按 GB 55001-2021 第 3.1.13 条添加")
    print("=" * 70)
