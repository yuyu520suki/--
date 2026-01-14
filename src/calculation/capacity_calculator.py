"""
承载力计算器模块 - 基于 GB 50010-2010 规范
重构版：基于 Grok 建议的控制点算法 + 严格的几何中心力矩平衡
"""

import math
from typing import Tuple, List

# =============================================================================
# 材料参数 (GB 50010-2010)
# =============================================================================

# 混凝土 C30
F_C = 14.3      # 混凝土轴心抗压强度设计值 (MPa)
F_T = 1.43      # 混凝土轴心抗拉强度设计值 (MPa)
E_C = 30000     # 混凝土弹性模量 (MPa)
ALPHA_1 = 1.0   # 受压区等效矩形应力图系数
BETA_1 = 0.8    # 受压区高度系数 (C50以下)

# 钢筋 HRB400
F_Y = 360       # 钢筋抗拉强度设计值 (MPa)
F_Y_PRIME = 360 # 钢筋抗压强度设计值 (MPa)
E_S = 200000    # 钢筋弹性模量 (MPa)

# 构造要求
C_COVER = 35    # 保护层厚度 (mm)
D_STIRRUP = 8   # 箍筋直径 (mm)

def get_h0(h: float) -> float:
    """计算有效高度 h0 = h - as"""
    a_s = C_COVER + D_STIRRUP + 10 
    return h - a_s


# =============================================================================
# 梁正截面受弯承载力 (GB 50010-2010 第6.2节)
# =============================================================================

def calculate_beam_Mn(b: float, h: float, As: float, As_prime: float = 0) -> float:
    """
    计算单筋/双筋矩形截面受弯承载力
    """
    h0 = get_h0(h)
    a_s_prime = C_COVER + D_STIRRUP + 10
    xi_b = BETA_1 / (1 + F_Y / (E_S * 0.0033))
    x = (F_Y * As - F_Y_PRIME * As_prime) / (ALPHA_1 * F_C * b)
    if x > xi_b * h0: x = xi_b * h0
    if x < 2 * a_s_prime and As_prime > 0: x = 2 * a_s_prime
    Mn = ALPHA_1 * F_C * b * x * (h0 - x / 2) + F_Y_PRIME * As_prime * (h0 - a_s_prime)
    return Mn / 1e6


def calculate_phi_Mn(b: float, h: float, As: float, As_prime: float = 0) -> float:
    """计算设计弯矩承载力 φMn (取 φ=0.9)"""
    return 0.9 * calculate_beam_Mn(b, h, As, As_prime)


# =============================================================================
# 梁斜截面受剪承载力 (GB 50010-2010 第6.3节)
# =============================================================================

def calculate_beam_Vn(b: float, h: float, s: float = 150, Asv: float = 100.5) -> float:
    """计算梁斜截面受剪承载力"""
    h0 = get_h0(h)
    Vc = 0.7 * F_T * b * h0
    Vs = F_Y * Asv * h0 / s
    return (Vc + Vs) / 1000


def calculate_phi_Vn(b: float, h: float, s: float = 150, Asv: float = 100.5) -> float:
    """计算设计剪力承载力 φVn (取 φ=0.75)"""
    return 0.75 * calculate_beam_Vn(b, h, s, Asv)


# =============================================================================
# 综合承载力计算
# =============================================================================

def calculate_capacity(b: float, h: float, As: float, 
                       As_prime: float = 0, s: float = 150, 
                       Asv: float = 100.5) -> dict:
    """计算截面综合承载力"""
    return {
        'phi_Mn': calculate_phi_Mn(b, h, As, As_prime),
        'phi_Vn': calculate_phi_Vn(b, h, s, Asv),
        'Mn': calculate_beam_Mn(b, h, As, As_prime),
        'Vn': calculate_beam_Vn(b, h, s, Asv),
    }


# =============================================================================
# P-M 相互作用曲线 (柱) - 重构修正版 (Grok 控制点算法)
# =============================================================================

def generate_pm_curve(b: float, h: float, As_total: float, 
                      num_points: int = 60) -> List[Tuple[float, float]]:
    """
    生成 P-M 曲线 (控制点法)
    
    符号约定: 
    - P: 压为正 (+), 拉为负 (-)
    - M: 绝对值 (kN·m)
    - 基准: 截面几何中心 (h/2)
    """
    h0 = get_h0(h)
    a_s = h - h0
    a_s_prime = a_s
    As = As_total / 2
    As_prime = As_total / 2
    
    # 界限破坏参数
    xi_b = BETA_1 / (1 + F_Y / (E_S * 0.0033))
    x_b = xi_b * h0

    # 内部计算函数：给定中和轴高度 x，计算 N 和 M
    def compute_nm(x):
        # 1. 纯拉状态 (x 极小或负)
        if x <= 1e-5:
            N = -F_Y * As_total
            M = 0.0
            return N / 1000, M
        
        # 2. 混凝土贡献
        h_eff = min(h, BETA_1 * x)
        C_c = ALPHA_1 * F_C * b * h_eff
        y_c_top = h_eff / 2
        y_arm_c = (h / 2) - y_c_top
        M_c = C_c * y_arm_c
        
        # 3. 钢筋应变与应力
        eps_prime = 0.0033 * (x - a_s_prime) / x
        sig_prime = max(-F_Y, min(F_Y_PRIME, E_S * eps_prime))
        F_prime = sig_prime * As_prime
        y_arm_prime = (h / 2) - a_s_prime
        M_prime = F_prime * y_arm_prime

        eps_s = 0.0033 * (x - h0) / x
        sig_s = max(-F_Y, min(F_Y_PRIME, E_S * eps_s))
        F_s = sig_s * As
        y_arm_s = (h / 2) - h0
        M_s = F_s * y_arm_s

        # 4. 合力与合力矩
        N_total = C_c + F_prime + F_s
        M_total = M_c + M_prime + M_s
        
        return N_total / 1000, abs(M_total) / 1e6

    points = []
    
    # === 关键控制点 ===
    
    # 1. 纯压点 (x -> infinity)
    N_pure_comp = (ALPHA_1 * F_C * b * h + F_Y_PRIME * As_total) / 1000
    points.append((N_pure_comp, 0.0))
    
    # 2. 生成 x 序列 (从大偏心到受拉)
    x_steps = []
    
    # 段1: 纯压附近过渡 (x > h)
    x_steps.append(h * 1.5)
    x_steps.append(h * 1.1)
    
    # 段2: 大偏心受压 (h -> xb), xb附近加密
    num_seg1 = 15
    for i in range(num_seg1):
        t = i / (num_seg1 - 1)
        val = x_b + (h - x_b) * (1 - t)**2
        x_steps.append(val)
        
    # 段3: 小偏心受压到受拉 (xb -> 0)
    num_seg2 = 15
    for i in range(1, num_seg2):
        t = i / num_seg2
        val = x_b * (1 - t)
        x_steps.append(val)
        
    # 3. 计算所有中间点
    for x in x_steps:
        points.append(compute_nm(x))
        
    # 4. 纯拉点 (x -> 0)
    N_pure_tension = -F_Y * As_total / 1000
    points.append((N_pure_tension, 0.0))
    
    # 5. 排序与去重 (按P降序: 大压 -> 小压 -> 拉)
    unique_points = sorted(list(set(points)), key=lambda p: p[0], reverse=True)
    
    return unique_points


def check_pm_capacity(P_u: float, M_u: float, pm_curve: List[Tuple[float, float]]) -> bool:
    """
    检查承载力 (支持压+ 拉-)
    """
    M_u_abs = abs(M_u)
    
    max_P = pm_curve[0][0]
    min_P = pm_curve[-1][0]
    
    # 1. 轴力超限检查
    if P_u > max_P: return False  # 压力太大
    if P_u < min_P: return False  # 拉力太大
    
    # 2. 插值检查
    for i in range(len(pm_curve) - 1):
        P1, M1 = pm_curve[i]
        P2, M2 = pm_curve[i+1]
        
        # 曲线是 P 降序: P1 >= P2
        if P2 <= P_u <= P1:
            if abs(P1 - P2) < 1e-4:
                M_cap = max(M1, M2)
            else:
                ratio = (P_u - P2) / (P1 - P2)
                M_cap = M2 + ratio * (M1 - M2)
            
            return M_u_abs <= M_cap * 1.05
            
    return False


# =============================================================================
# 默认配筋方案
# =============================================================================

REBAR_AREAS = {
    '2φ16': 402, '2φ18': 509, '2φ20': 628, '3φ20': 942, '4φ20': 1257,
    '2φ22': 760, '3φ22': 1140, '4φ22': 1520, '2φ25': 982, '3φ25': 1473, '4φ25': 1964
}
DEFAULT_REBAR = REBAR_AREAS['3φ20']


# =============================================================================
# 测试代码
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("承载力计算器测试 (GB 50010-2010)")
    print("=" * 60)
    
    b_col, h_col = 400, 400
    As_col = REBAR_AREAS['4φ22']
    
    pm_curve = generate_pm_curve(b_col, h_col, As_col)
    
    print(f"\n柱截面: {b_col}x{h_col} mm, 配筋: 4φ22 ({As_col} mm²)")
    print(f"P-M 曲线点数: {len(pm_curve)}")
    print(f"\n关键点:")
    print(f"  纯压: P = {pm_curve[0][0]:.1f} kN, M = {pm_curve[0][1]:.2f} kN·m")
    print(f"  纯拉: P = {pm_curve[-1][0]:.1f} kN, M = {pm_curve[-1][1]:.2f} kN·m")
    
    max_M_point = max(pm_curve, key=lambda p: p[1])
    print(f"  最大M: P = {max_M_point[0]:.1f} kN, M = {max_M_point[1]:.2f} kN·m")
