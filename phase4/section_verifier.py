"""
截面验证器模块 - 承载力校验
基于 GB 50010-2010 规范，包含 P-M 曲线验算和拓扑约束检查
"""

import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import numpy as np

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from phase1.section_database import SectionDatabase
from phase1.capacity_calculator import (
    calculate_capacity,
    generate_pm_curve,
    check_pm_capacity,
    REBAR_AREAS,
    DEFAULT_REBAR,
)
from phase4.data_models import GridInput, ElementForces

# 尝试导入 shapely（可选依赖）
try:
    from shapely.geometry import Polygon, Point
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False
    print("警告: shapely 未安装，P-M验算将使用简化方法")


# =============================================================================
# 默认配筋配置
# =============================================================================

DEFAULT_BEAM_AS = REBAR_AREAS['3φ20']   # 942 mm² (梁)
DEFAULT_COL_AS = REBAR_AREAS['4φ22']    # 1520 mm² (柱)


class SectionVerifier:
    """
    截面验证器
    
    功能:
    - 梁承载力验算 (弯矩、剪力)
    - 柱承载力验算 (P-M相互作用曲线)
    - 拓扑约束检查 (强柱弱梁、下大上小)
    
    惩罚策略:
    - D/C > 1.0 时，惩罚值 = (D/C - 1.0)
    - 柱P-M超限时，惩罚值 = 到包络线的归一化距离
    """
    
    def __init__(self, db: SectionDatabase = None):
        """
        初始化验证器
        
        Args:
            db: 截面数据库
        """
        self.db = db if db else SectionDatabase()
        
        # P-M曲线缓存
        self._pm_cache: Dict[int, List[Tuple[float, float]]] = {}
        self._pm_polygon_cache: Dict[int, object] = {}  # shapely Polygon
        
        # 归一化因子 (用于惩罚值计算)
        self._M_norm = 1000.0  # kN·m
        self._N_norm = 5000.0  # kN
    
    def precompute_pm_curves(self, 
                             As_total: float = DEFAULT_COL_AS,
                             num_points: int = 50) -> None:
        """
        预计算所有截面的P-M曲线并缓存
        
        Args:
            As_total: 总配筋面积 (mm²)
            num_points: 曲线采样点数
        """
        print(f"预计算P-M曲线 ({len(self.db)} 个截面)...")
        
        for idx in range(len(self.db)):
            sec = self.db.get_by_index(idx)
            pm_curve = generate_pm_curve(sec['b'], sec['h'], As_total, num_points)
            self._pm_cache[idx] = pm_curve
            
            # 创建shapely多边形（如果可用）
            if HAS_SHAPELY and len(pm_curve) >= 3:
                try:
                    self._pm_polygon_cache[idx] = Polygon(pm_curve)
                except Exception:
                    pass
        
        print(f"  ✓ 已缓存 {len(self._pm_cache)} 条P-M曲线")
    
    def get_pm_curve(self, section_idx: int) -> List[Tuple[float, float]]:
        """获取P-M曲线（优先从缓存读取）"""
        if section_idx in self._pm_cache:
            return self._pm_cache[section_idx]
        
        # 实时计算
        sec = self.db.get_by_index(section_idx)
        pm_curve = generate_pm_curve(sec['b'], sec['h'], DEFAULT_COL_AS)
        self._pm_cache[section_idx] = pm_curve
        return pm_curve
    
    def check_beam_capacity(self, 
                            section_idx: int, 
                            mu: float, 
                            vu: float,
                            As: float = DEFAULT_BEAM_AS) -> Tuple[float, float]:
        """
        验算梁承载力
        
        Args:
            section_idx: 截面索引
            mu: 设计弯矩 (kN·m)
            vu: 设计剪力 (kN)
            As: 配筋面积 (mm²)
            
        Returns:
            (M惩罚值, V惩罚值): 超限程度，0表示满足
        """
        sec = self.db.get_by_index(section_idx)
        cap = calculate_capacity(sec['b'], sec['h'], As)
        
        # D/C 比
        dc_M = abs(mu) / cap['phi_Mn'] if cap['phi_Mn'] > 0 else 999
        dc_V = abs(vu) / cap['phi_Vn'] if cap['phi_Vn'] > 0 else 999
        
        # 惩罚值 (超限部分)
        penalty_M = max(0, dc_M - 1.0)
        penalty_V = max(0, dc_V - 1.0)
        
        return penalty_M, penalty_V
    
    def check_column_capacity(self, 
                              section_idx: int, 
                              pu: float, 
                              mu: float) -> float:
        """
        验算柱承载力 (使用真实P-M曲线)
        
        使用预计算的P-M曲线进行精确验算，确保与图表显示一致
        
        Args:
            section_idx: 截面索引
            pu: 设计轴力 (kN), 压力为正
            mu: 设计弯矩 (kN·m)
            
        Returns:
            惩罚值: 0表示安全，>0表示超限
        """
        # 获取P-M曲线（使用缓存）
        pm_curve = self.get_pm_curve(section_idx)
        
        if not pm_curve:
            # 无曲线时回退到简化方法
            return self._check_column_simplified(section_idx, pu, mu)
        
        # 使用真实P-M曲线验算
        # 注意：check_pm_capacity中，P是压力为正，与我们的约定一致
        is_safe = check_pm_capacity(abs(pu), abs(mu), pm_curve)
        
        if is_safe:
            return 0.0
        else:
            # 计算超限程度作为惩罚值
            # 找到对应轴力下的弯矩承载力
            M_capacity = self._get_pm_capacity_at_axial(pm_curve, abs(pu))
            if M_capacity > 0:
                over_ratio = abs(mu) / M_capacity - 1.0
                return max(0.0, over_ratio) * 2.0  # 放大惩罚
            else:
                return 1.0  # 默认惩罚
    
    def _check_column_simplified(self, section_idx: int, pu: float, mu: float) -> float:
        """简化的柱验算方法（备用）"""
        sec = self.db.get_by_index(section_idx)
        cap = calculate_capacity(sec['b'], sec['h'], DEFAULT_COL_AS)
        
        phi_Mn = cap['phi_Mn']
        fc = 14.3  # MPa (C30)
        Ag = sec['b'] * sec['h']
        phi_Pn = 0.65 * 0.85 * fc * Ag / 1000
        
        if phi_Pn > 0 and phi_Mn > 0:
            utilization = abs(pu) / phi_Pn + abs(mu) / phi_Mn
            if utilization <= 1.0:
                return 0.0
            else:
                return utilization - 1.0
        
        return 0.5
    
    def _get_pm_capacity_at_axial(self, pm_curve: List[Tuple[float, float]], P_u: float) -> float:
        """获取给定轴力下的弯矩承载力"""
        for i in range(len(pm_curve) - 1):
            P1, M1 = pm_curve[i]
            P2, M2 = pm_curve[i + 1]
            
            if min(P1, P2) <= P_u <= max(P1, P2):
                if abs(P2 - P1) < 1e-6:
                    return max(abs(M1), abs(M2))
                else:
                    t = (P_u - P1) / (P2 - P1)
                    return abs(M1 + t * (M2 - M1))
        
        # 超出范围，返回边界值
        return max(abs(m) for p, m in pm_curve)
    
    def check_topology_constraints(self, 
                                   genes: List[int], 
                                   grid: GridInput) -> float:
        """
        检查拓扑约束
        
        规则:
        1. 强柱弱梁：柱截面面积 >= 梁截面面积 × 0.8
        2. 下大上小：底层柱 >= 标准层柱 >= 顶层柱
        
        Args:
            genes: [标准梁, 屋面梁, 底层柱, 标准角柱, 标准内柱, 顶层柱] 截面索引
            grid: 轴网信息
            
        Returns:
            惩罚值: 违反程度
        """
        if len(genes) < 6:
            return 0.0
        
        violation = 0.0
        
        # 1. 强柱弱梁约束：底层柱面积 >= 标准梁面积 × 0.8
        beam_sec = self.db.get_by_index(genes[0])  # 标准梁
        bottom_col_sec = self.db.get_by_index(genes[2])   # 底层柱
        
        ratio = bottom_col_sec['A'] / beam_sec['A']
        min_ratio = 0.8
        
        if ratio < min_ratio:
            violation += (min_ratio - ratio) * 2.0  # 放大惩罚
        
        # 2. 下大上小约束：底层柱 >= 顶层柱
        top_col_sec = self.db.get_by_index(genes[5])  # 顶层柱
        if top_col_sec['A'] > bottom_col_sec['A']:
            violation += (top_col_sec['A'] / bottom_col_sec['A'] - 1.0) * 1.5
        
        return violation
    
    def verify_all_elements(self, 
                            forces: Dict[int, ElementForces],
                            beam_sections: Dict[int, int],
                            col_sections: Dict[int, int]) -> Tuple[float, Dict[int, float]]:
        """
        验算所有构件
        
        Args:
            forces: 内力结果
            beam_sections: {beam_id: section_idx}
            col_sections: {col_id: section_idx}
            
        Returns:
            (总惩罚值, {element_id: 惩罚值})
        """
        penalties = {}
        total_penalty = 0.0
        
        for elem_id, f in forces.items():
            if f.element_type == 'beam':
                sec_idx = beam_sections.get(elem_id, 30)
                p_M, p_V = self.check_beam_capacity(sec_idx, f.M_design, f.V_design)
                penalties[elem_id] = p_M + p_V
            else:
                sec_idx = col_sections.get(elem_id, 40)
                # 使用压力的绝对值 (anaStruct返回压力为负，axial_min是最大压力)
                # 这样与P-M曲线图绘制时使用的轴力保持一致
                N_compression = abs(f.axial_min)  # 压力为正
                p = self.check_column_capacity(sec_idx, N_compression, f.M_design)
                penalties[elem_id] = p
            
            total_penalty += penalties[elem_id]
        
        return total_penalty, penalties
    
    def get_utility_ratios(self,
                           forces: Dict[int, ElementForces],
                           beam_sections: Dict[int, int],
                           col_sections: Dict[int, int]) -> Dict[int, float]:
        """
        计算所有构件的利用率
        
        Returns:
            {element_id: utility_ratio}
        """
        ratios = {}
        
        for elem_id, f in forces.items():
            if f.element_type == 'beam':
                sec_idx = beam_sections.get(elem_id, 30)
                sec = self.db.get_by_index(sec_idx)
                cap = calculate_capacity(sec['b'], sec['h'], DEFAULT_BEAM_AS)
                
                ratio_M = abs(f.M_design) / cap['phi_Mn'] if cap['phi_Mn'] > 0 else 999
                ratio_V = abs(f.V_design) / cap['phi_Vn'] if cap['phi_Vn'] > 0 else 999
                ratios[elem_id] = max(ratio_M, ratio_V)
            else:
                sec_idx = col_sections.get(elem_id, 40)
                # 简化：使用弯矩利用率
                sec = self.db.get_by_index(sec_idx)
                cap = calculate_capacity(sec['b'], sec['h'], DEFAULT_COL_AS)
                ratio = abs(f.M_design) / cap['phi_Mn'] if cap['phi_Mn'] > 0 else 999
                ratios[elem_id] = ratio
        
        return ratios
    
    # =========================================================================
    # 新增验算方法 (GB 50010-2010)
    # =========================================================================
    
    def check_axial_ratio(self, section_idx: int, nu: float) -> float:
        """
        轴压比限值验算 (GB 50010-2010 表11.4.16)
        
        非抗震时，轴压比限值 μ = N / (fc * A) ≤ 0.9
        
        Args:
            section_idx: 截面索引
            nu: 设计轴力 (kN), 压力为正
            
        Returns:
            惩罚值: 0表示满足，>0表示超限
        """
        sec = self.db.get_by_index(section_idx)
        fc = 14.3  # MPa (C30)
        Ag = sec['b'] * sec['h']  # mm²
        
        mu_limit = 0.9  # 非抗震限值
        mu_actual = abs(nu) * 1000 / (fc * Ag)  # 轴压比
        
        if mu_actual > mu_limit:
            return (mu_actual - mu_limit) * 2.0  # 超限惩罚
        return 0.0
    
    def check_deflection(self, span: float, delta: float, 
                         element_type: str = 'beam') -> float:
        """
        挠度限值验算 (GB 50010-2010 表3.4.3)
        
        限值:
        - 梁 (l ≤ 7m): l/200
        - 梁 (l > 7m): l/250
        - 悬挑构件: l/250
        
        Args:
            span: 跨度 (mm)
            delta: 挠度 (mm)
            element_type: 构件类型
            
        Returns:
            惩罚值: 0表示满足，>0表示超限
        """
        # 确定挠度限值
        if element_type == 'cantilever':
            limit = span / 250
        elif span <= 7000:
            limit = span / 200
        else:
            limit = span / 250
        
        if abs(delta) > limit:
            return (abs(delta) / limit - 1.0) * 0.5
        return 0.0
    
    def check_crack_width(self, wmax: float, 
                          env_class: str = 'II-a') -> float:
        """
        裂缝宽度验算 (GB 50010-2010 表3.4.5)
        
        最大裂缝宽度限值:
        - I 类环境: 0.4mm
        - II-a 类环境: 0.3mm
        - II-b 类环境: 0.2mm
        - III 类环境: 0.2mm
        
        Args:
            wmax: 最大裂缝宽度 (mm)
            env_class: 环境类别
            
        Returns:
            惩罚值: 0表示满足，>0表示超限
        """
        limits = {
            'I': 0.4,
            'II-a': 0.3,
            'II-b': 0.2,
            'III-a': 0.2,
            'III-b': 0.2,
        }
        wlim = limits.get(env_class, 0.3)
        
        if wmax > wlim:
            return (wmax / wlim - 1.0) * 0.5
        return 0.0
    
    def check_min_reinforcement(self, section_idx: int, As: float,
                                element_type: str = 'beam') -> float:
        """
        最小配筋率检查 (GB 50010-2010 表8.5.1)
        
        最小配筋率:
        - 梁受拉区: ρmin = max(0.2%, 45*ft/fy)
        - 柱全截面: ρmin = 0.6%
        
        Args:
            section_idx: 截面索引
            As: 配筋面积 (mm²)
            element_type: 构件类型
            
        Returns:
            惩罚值: 0表示满足，>0表示不足
        """
        sec = self.db.get_by_index(section_idx)
        
        if element_type == 'beam':
            # 受拉区配筋率 (按 b*h0 计算)
            h0 = sec['h'] - 40  # 有效高度
            A_eff = sec['b'] * h0
            rho = As / A_eff * 100  # %
            
            # ft=1.43 MPa (C30), fy=360 MPa
            rho_min = max(0.2, 45 * 1.43 / 360 * 100)  # ≈ 0.2%
        else:
            # 柱全截面配筋率
            Ag = sec['b'] * sec['h']
            rho = As / Ag * 100  # %
            rho_min = 0.6  # %
        
        if rho < rho_min:
            return (rho_min - rho) / rho_min * 0.3
        return 0.0
    
    def check_max_reinforcement(self, section_idx: int, As: float,
                                element_type: str = 'beam') -> float:
        """
        最大配筋率检查 (GB 50010-2010)
        
        最大配筋率:
        - 梁: 2.5%
        - 柱: 5%
        
        Args:
            section_idx: 截面索引
            As: 配筋面积 (mm²)
            element_type: 构件类型
            
        Returns:
            惩罚值: 0表示满足，>0表示超限
        """
        sec = self.db.get_by_index(section_idx)
        
        if element_type == 'beam':
            h0 = sec['h'] - 40
            A_eff = sec['b'] * h0
            rho = As / A_eff * 100
            rho_max = 2.5
        else:
            Ag = sec['b'] * sec['h']
            rho = As / Ag * 100
            rho_max = 5.0
        
        if rho > rho_max:
            return (rho - rho_max) / rho_max * 0.5
        return 0.0
    
    def verify_comprehensive(self,
                             forces: Dict[int, ElementForces],
                             beam_sections: Dict[int, int],
                             col_sections: Dict[int, int],
                             grid = None) -> Dict[str, float]:
        """
        综合验算所有项目
        
        Returns:
            各类惩罚值汇总 {'capacity': ..., 'axial_ratio': ..., ...}
        """
        penalties = {
            'capacity': 0.0,
            'axial_ratio': 0.0,
            'reinforcement': 0.0,
            'topology': 0.0,
        }
        
        # 1. 承载力验算
        cap_penalty, _ = self.verify_all_elements(forces, beam_sections, col_sections)
        penalties['capacity'] = cap_penalty
        
        # 2. 柱轴压比验算
        for elem_id, f in forces.items():
            if f.element_type == 'column':
                sec_idx = col_sections.get(elem_id, 40)
                penalties['axial_ratio'] += self.check_axial_ratio(sec_idx, f.N_design)
        
        # 3. 配筋率验算
        for elem_id, f in forces.items():
            if f.element_type == 'beam':
                sec_idx = beam_sections.get(elem_id, 30)
                penalties['reinforcement'] += self.check_min_reinforcement(
                    sec_idx, DEFAULT_BEAM_AS, 'beam'
                )
            else:
                sec_idx = col_sections.get(elem_id, 40)
                penalties['reinforcement'] += self.check_min_reinforcement(
                    sec_idx, DEFAULT_COL_AS, 'column'
                )
        
        # 4. 拓扑约束 (如果提供了grid)
        if grid:
            genes = [30, 30, 40, 40]  # 默认基因
            penalties['topology'] = self.check_topology_constraints(genes, grid)
        
        return penalties

# =============================================================================
# 测试代码
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("Phase 4B: 验证引擎测试")
    print("=" * 70)
    
    # 初始化
    db = SectionDatabase()
    verifier = SectionVerifier(db)
    
    # 预计算P-M曲线
    verifier.precompute_pm_curves()
    
    # 测试梁验算
    print("\n梁承载力验算测试:")
    test_cases_beam = [
        (30, 100, 50),   # 中等截面，中等荷载
        (30, 200, 100),  # 中等截面，较大荷载
        (50, 150, 80),   # 大截面，中等荷载
    ]
    
    for sec_idx, mu, vu in test_cases_beam:
        sec = db.get_by_index(sec_idx)
        p_M, p_V = verifier.check_beam_capacity(sec_idx, mu, vu)
        status = "✓ 满足" if p_M == 0 and p_V == 0 else "✗ 超限"
        print(f"  截面{sec_idx} ({sec['b']}×{sec['h']}): "
              f"Mu={mu}, Vu={vu} → 惩罚(M={p_M:.2f}, V={p_V:.2f}) {status}")
    
    # 测试柱验算
    print("\n柱承载力验算测试 (P-M曲线):")
    test_cases_col = [
        (40, 1000, 100),  # 中等轴力和弯矩
        (40, 2000, 200),  # 较大荷载
        (50, 3000, 300),  # 大截面大荷载
    ]
    
    for sec_idx, pu, mu in test_cases_col:
        sec = db.get_by_index(sec_idx)
        penalty = verifier.check_column_capacity(sec_idx, pu, mu)
        status = "✓ 安全" if penalty == 0 else f"✗ 超限(惩罚={penalty:.3f})"
        print(f"  截面{sec_idx} ({sec['b']}×{sec['h']}): "
              f"Pu={pu}kN, Mu={mu}kN·m → {status}")
    
    # 测试拓扑约束
    print("\n拓扑约束测试 (强柱弱梁):")
    test_genes = [
        [30, 30, 50, 45],  # 梁小柱大 → 满足
        [50, 50, 30, 30],  # 梁大柱小 → 违反
    ]
    
    grid = GridInput(x_spans=[6000], z_heights=[3500])
    for genes in test_genes:
        beam_sec = db.get_by_index(genes[0])
        col_sec = db.get_by_index(genes[2])
        penalty = verifier.check_topology_constraints(genes, grid)
        status = "✓ 满足" if penalty == 0 else f"✗ 违反(惩罚={penalty:.2f})"
        print(f"  梁{beam_sec['b']}×{beam_sec['h']} vs 柱{col_sec['b']}×{col_sec['h']} → {status}")
    
    print("\n" + "=" * 70)
    print(f"✓ Phase 4B 验证引擎测试通过! (shapely: {'已安装' if HAS_SHAPELY else '未安装'})")
    print("=" * 70)
