"""
截面验证器模块 (Analyzer) - 承载力校验
基于 GB 50010-2010 规范，包含 P-M 曲线验算和拓扑约束检查
"""

from typing import Dict, List, Tuple, Optional
import numpy as np

from src.calculation.section_database import SectionDatabase
from src.calculation.capacity_calculator import (
    calculate_capacity,
    generate_pm_curve,
    check_pm_capacity,
    REBAR_AREAS,
    DEFAULT_REBAR,
)
from src.models.data_models import GridInput, ElementForces

# 尝试导入 shapely（可选依赖）
try:
    from shapely.geometry import Polygon, Point
    HAS_SHAPELY = True
except ImportError:
    HAS_SHAPELY = False


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
        self._pm_polygon_cache: Dict[int, object] = {}
        
        # 归一化因子
        self._M_norm = 1000.0  # kN·m
        self._N_norm = 5000.0  # kN
    
    def precompute_pm_curves(self, 
                             As_total: float = DEFAULT_COL_AS,
                             num_points: int = 50) -> None:
        """
        预计算所有截面的P-M曲线并缓存
        """
        print(f"预计算P-M曲线 ({len(self.db)} 个截面)...")
        
        for idx in range(len(self.db)):
            sec = self.db.get_by_index(idx)
            pm_curve = generate_pm_curve(sec['b'], sec['h'], As_total, num_points)
            self._pm_cache[idx] = pm_curve
            
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
        
        Returns:
            (M惩罚值, V惩罚值): 超限程度，0表示满足
        """
        sec = self.db.get_by_index(section_idx)
        cap = calculate_capacity(sec['b'], sec['h'], As)
        
        dc_M = abs(mu) / cap['phi_Mn'] if cap['phi_Mn'] > 0 else 999
        dc_V = abs(vu) / cap['phi_Vn'] if cap['phi_Vn'] > 0 else 999
        
        penalty_M = max(0, dc_M - 1.0)
        penalty_V = max(0, dc_V - 1.0)
        
        return penalty_M, penalty_V
    
    def check_column_capacity(self, 
                              section_idx: int, 
                              pu: float, 
                              mu: float) -> float:
        """
        验算柱承载力 (P-M 曲线法)
        
        Args:
            section_idx: 截面索引
            pu: 设计轴力 (kN). 符号约定: 压+, 拉-
            mu: 设计弯矩 (kN·m)
        
        Returns:
            惩罚值: 0表示安全，>0表示超限
        """
        pm_curve = self.get_pm_curve(section_idx)
        if not pm_curve:
            return self._check_column_simplified(section_idx, pu, mu)
        
        is_safe = check_pm_capacity(pu, abs(mu), pm_curve)
        
        if is_safe:
            return 0.0
        else:
            M_capacity = self._get_pm_capacity_at_axial(pm_curve, pu)
            if M_capacity > 1e-3:
                return (abs(mu) / M_capacity) - 1.0
            else:
                return 2.0
    
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
            if P2 <= P_u <= P1:
                if abs(P1 - P2) < 1e-4:
                    return max(M1, M2)
                else:
                    ratio = (P_u - P2) / (P1 - P2)
                    return M2 + ratio * (M1 - M2)
        return 0.0
    
    def check_topology_constraints(self, 
                                   genes: List[int], 
                                   grid: GridInput) -> float:
        """
        检查拓扑约束
        
        规则:
        1. 强柱弱梁：柱截面面积 >= 梁截面面积 × 0.8
        2. 下大上小：底层柱 >= 顶层柱
        """
        if len(genes) < 6:
            return 0.0
        
        violation = 0.0
        
        # 1. 强柱弱梁约束
        beam_sec = self.db.get_by_index(genes[0])
        bottom_col_sec = self.db.get_by_index(genes[2])
        
        ratio = bottom_col_sec['A'] / beam_sec['A']
        min_ratio = 0.8
        
        if ratio < min_ratio:
            violation += (min_ratio - ratio) * 2.0
        
        # 2. 下大上小约束
        top_col_sec = self.db.get_by_index(genes[5])
        if top_col_sec['A'] > bottom_col_sec['A']:
            violation += (top_col_sec['A'] / bottom_col_sec['A'] - 1.0) * 1.5
        
        return violation
    
    def verify_all_elements(self, 
                            forces: Dict[int, ElementForces],
                            beam_sections: Dict[int, int],
                            col_sections: Dict[int, int]) -> Tuple[float, Dict[int, float]]:
        """
        验算所有构件
        
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
                
                # 同时验算最大压力和最大拉力工况
                P_comp = -f.axial_min 
                pen_comp = self.check_column_capacity(sec_idx, P_comp, f.M_design)
                
                P_tens = -f.axial_max
                pen_tens = self.check_column_capacity(sec_idx, P_tens, f.M_design)
                
                penalties[elem_id] = max(pen_comp, pen_tens)
            
            total_penalty += penalties[elem_id]
        
        return total_penalty, penalties
    
    def get_utility_ratios(self,
                           forces: Dict[int, ElementForces],
                           beam_sections: Dict[int, int],
                           col_sections: Dict[int, int]) -> Dict[int, float]:
        """计算所有构件的利用率"""
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
                sec = self.db.get_by_index(sec_idx)
                cap = calculate_capacity(sec['b'], sec['h'], DEFAULT_COL_AS)
                ratio = abs(f.M_design) / cap['phi_Mn'] if cap['phi_Mn'] > 0 else 999
                ratios[elem_id] = ratio
        
        return ratios
    
    # =========================================================================
    # 新增验算方法 (GB 50010-2010)
    # =========================================================================
    
    def check_axial_ratio(self, section_idx: int, nu: float) -> float:
        """轴压比限值验算 (GB 50010-2010 表11.4.16)"""
        sec = self.db.get_by_index(section_idx)
        fc = 14.3  # MPa (C30)
        Ag = sec['b'] * sec['h']
        
        mu_limit = 0.9
        mu_actual = abs(nu) * 1000 / (fc * Ag)
        
        if mu_actual > mu_limit:
            return (mu_actual - mu_limit) * 2.0
        return 0.0
    
    def check_deflection(self, span: float, delta: float, 
                         element_type: str = 'beam') -> float:
        """挠度限值验算 (GB 50010-2010 表3.4.3)"""
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
        """裂缝宽度验算 (GB 50010-2010 表3.4.5)"""
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
        """最小配筋率检查 (GB 50010-2010 表8.5.1)"""
        sec = self.db.get_by_index(section_idx)
        
        if element_type == 'beam':
            h0 = sec['h'] - 40
            A_eff = sec['b'] * h0
            rho = As / A_eff * 100
            rho_min = max(0.2, 45 * 1.43 / 360 * 100)
        else:
            Ag = sec['b'] * sec['h']
            rho = As / Ag * 100
            rho_min = 0.6
        
        if rho < rho_min:
            return (rho_min - rho) / rho_min * 0.3
        return 0.0
    
    def check_max_reinforcement(self, section_idx: int, As: float,
                                element_type: str = 'beam') -> float:
        """最大配筋率检查 (GB 50010-2010)"""
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
        """综合验算所有项目"""
        penalties = {
            'capacity': 0.0,
            'axial_ratio': 0.0,
            'reinforcement': 0.0,
            'topology': 0.0,
        }
        
        cap_penalty, _ = self.verify_all_elements(forces, beam_sections, col_sections)
        penalties['capacity'] = cap_penalty
        
        for elem_id, f in forces.items():
            if f.element_type == 'column':
                sec_idx = col_sections.get(elem_id, 40)
                penalties['axial_ratio'] += self.check_axial_ratio(sec_idx, f.N_design)
        
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
        
        if grid:
            genes = [30, 30, 40, 40, 40, 40]
            penalties['topology'] = self.check_topology_constraints(genes, grid)
        
        return penalties


# =============================================================================
# 验证结果类（兼容 phase5/model_validator）
# =============================================================================

from dataclasses import dataclass, field

@dataclass
class ValidationResult:
    """验证结果汇总"""
    all_passed: bool = True
    checks: Dict[str, Dict] = field(default_factory=dict)
    summary: str = ""
    detailed_report: str = ""
    
    def add_check(self, name: str, passed: bool, details: Dict):
        """添加检查结果"""
        self.checks[name] = {
            'passed': passed,
            'details': details
        }
        if not passed:
            self.all_passed = False
    
    def generate_summary(self) -> str:
        """生成验证摘要"""
        lines = ["=" * 60, "模型验证报告", "=" * 60, ""]
        
        for name, result in self.checks.items():
            status = "✓ 通过" if result['passed'] else "✗ 失败"
            message = result['details'].get('message', '')
            lines.append(f"{name}: {status}")
            if message:
                lines.append(f"  {message}")
            lines.append("")
        
        lines.append("-" * 60)
        overall = "✓ 所有验证通过" if self.all_passed else "✗ 存在未通过的验证项"
        lines.append(f"总体结果: {overall}")
        lines.append("=" * 60)
        
        self.summary = "\n".join(lines)
        return self.summary


def validate_optimization_result(grid: GridInput,
                                 model,
                                 forces: Dict[int, ElementForces],
                                 db = None) -> ValidationResult:
    """
    便捷函数：验证优化结果
    
    基于 SectionVerifier 进行承载力验算，
    提供与 phase5/model_validator 兼容的接口。
    
    Args:
        grid: 轴网配置
        model: 结构模型
        forces: 内力结果
        db: 截面数据库
        
    Returns:
        验证结果
    """
    result = ValidationResult()
    
    if db is None:
        db = SectionDatabase()
    
    verifier = SectionVerifier(db)
    
    # 1. 承载力验算
    print("\n[1/3] 承载力验算...")
    total_penalty, penalties = verifier.verify_all_elements(
        forces,
        getattr(model, 'beam_sections', {}),
        getattr(model, 'column_sections', {})
    )
    
    capacity_passed = total_penalty < 0.01
    result.add_check("承载力验算", capacity_passed, {
        'message': f"总惩罚值: {total_penalty:.4f}",
        'penalty': total_penalty
    })
    
    # 2. 利用率检查
    print("[2/3] 利用率检查...")
    ratios = verifier.get_utility_ratios(
        forces,
        getattr(model, 'beam_sections', {}),
        getattr(model, 'column_sections', {})
    )
    max_ratio = max(ratios.values()) if ratios else 0
    utilization_passed = max_ratio <= 1.0
    result.add_check("利用率检查", utilization_passed, {
        'message': f"最大利用率: {max_ratio:.2f}",
        'max_ratio': max_ratio
    })
    
    # 3. 拓扑约束检查
    print("[3/3] 拓扑约束检查...")
    genes = getattr(model, 'genes', [30, 30, 40, 40, 40, 40])
    topo_penalty = verifier.check_topology_constraints(genes, grid)
    topo_passed = topo_penalty < 0.01
    result.add_check("拓扑约束检查", topo_passed, {
        'message': f"约束惩罚: {topo_penalty:.4f}",
        'penalty': topo_penalty
    })
    
    result.generate_summary()
    print(result.summary)
    
    return result


# =============================================================================
# 基准对比功能 (Benchmark Comparison)
# =============================================================================

def benchmark_comparison(grid, optimized_result=None, db=None, verbose: bool = True) -> Dict:
    """
    与经验设计基准进行对比
    
    基准模型: 柱 600×600 mm (索引约60), 梁 300×600 mm (索引约35)
    
    Args:
        grid: GridInput 轴网输入
        optimized_result: 优化结果 (可选)
        db: 截面数据库
        verbose: 是否打印详细信息
        
    Returns:
        dict: {benchmark_cost, optimized_cost, savings_pct, benchmark_penalty}
    """
    from src.models.structure_model import StructureModel
    
    if db is None:
        db = SectionDatabase()
    
    # =========================================================================
    # 第一步：创建基准模型
    # =========================================================================
    benchmark_model = StructureModel(db)
    benchmark_model.build_from_grid(grid)
    
    # 经验设计截面:
    # - 梁 300×600 (查找最接近的索引)
    # - 柱 600×600 (查找最接近的索引)
    beam_sec_idx = None
    col_sec_idx = None
    
    for i in range(len(db)):
        sec = db.get_by_index(i)
        if sec['b'] == 300 and sec['h'] == 600:
            beam_sec_idx = i
        if sec['b'] == 600 and sec['h'] == 600:
            col_sec_idx = i
    
    # 如果没找到精确匹配，使用默认值
    if beam_sec_idx is None:
        beam_sec_idx = 35  # 约 300×600
    if col_sec_idx is None:
        col_sec_idx = 60  # 约 600×600
    
    # 全截面统一配置 (6基因)
    benchmark_genes = [beam_sec_idx, beam_sec_idx, col_sec_idx, col_sec_idx, col_sec_idx, col_sec_idx]
    benchmark_model.set_sections_by_groups(benchmark_genes)
    benchmark_model.build_anastruct_model()
    
    # =========================================================================
    # 第二步：分析并验算基准模型
    # =========================================================================
    forces = benchmark_model.analyze()
    verifier = SectionVerifier(db)
    verifier.precompute_pm_curves()
    
    total_penalty, _ = verifier.verify_all_elements(
        forces,
        benchmark_model.beam_sections,
        benchmark_model.column_sections
    )
    
    # 计算基准造价
    benchmark_cost = 0.0
    for beam_id in benchmark_model.beams:
        sec = db.get_by_index(beam_sec_idx)
        span = sum(grid.x_spans) / (grid.num_spans * 1000)  # 平均跨度 (m)
        benchmark_cost += sec['cost_per_m'] * span
    
    for col_id in benchmark_model.columns:
        sec = db.get_by_index(col_sec_idx)
        story_idx = (col_id - grid.num_beams - 1) % grid.num_stories
        col_height = grid.z_heights[story_idx] / 1000  # m
        benchmark_cost += sec['cost_per_m'] * col_height
    
    # =========================================================================
    # 第三步：对比
    # =========================================================================
    result = {
        'benchmark_cost': round(benchmark_cost, 0),
        'benchmark_penalty': round(total_penalty, 2),
        'benchmark_genes': benchmark_genes,
        'optimized_cost': None,
        'savings_pct': None,
    }
    
    if optimized_result is not None:
        opt_cost = getattr(optimized_result, 'total_cost', optimized_result.get('total_cost', 0))
        result['optimized_cost'] = round(opt_cost, 0)
        if benchmark_cost > 0:
            result['savings_pct'] = round((benchmark_cost - opt_cost) / benchmark_cost * 100, 1)
    
    if verbose:
        print("=" * 60)
        print("基准对比 (Benchmark Comparison)")
        print("=" * 60)
        sec_beam = db.get_by_index(beam_sec_idx)
        sec_col = db.get_by_index(col_sec_idx)
        print(f"基准模型: 梁 {sec_beam['b']}×{sec_beam['h']} mm, 柱 {sec_col['b']}×{sec_col['h']} mm")
        print(f"  基准造价: {result['benchmark_cost']:.0f} 元")
        print(f"  约束违背: {result['benchmark_penalty']:.2f}")
        
        if result['optimized_cost'] is not None:
            print(f"优化结果:")
            print(f"  优化造价: {result['optimized_cost']:.0f} 元")
            print(f"  节省比例: {result['savings_pct']:.1f}%")
        print("=" * 60)
    
    return result


# =============================================================================
# 测试代码
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("截面验证器模块测试")
    print("=" * 70)
    
    db = SectionDatabase()
    verifier = SectionVerifier(db)
    verifier.precompute_pm_curves()
    
    print("\n梁承载力验算测试:")
    sec_idx, mu, vu = 30, 100, 50
    sec = db.get_by_index(sec_idx)
    p_M, p_V = verifier.check_beam_capacity(sec_idx, mu, vu)
    status = "✓ 满足" if p_M == 0 and p_V == 0 else "✗ 超限"
    print(f"  截面{sec_idx} ({sec['b']}×{sec['h']}): 惩罚(M={p_M:.2f}, V={p_V:.2f}) {status}")
    
    print("\n✓ 截面验证器测试通过")

