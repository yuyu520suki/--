"""
承载力计算器模块 - 基于 GB 50010-2010 规范
包含：弯曲承载力、剪切承载力、P-M 相互作用曲线
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
    a_s = C_COVER + D_STIRRUP + 10  # 假设主筋直径20mm, 取半径
    return h - a_s


# =============================================================================
# 梁正截面受弯承载力 (GB 50010-2010 第6.2节)
# =============================================================================

def calculate_beam_Mn(b: float, h: float, As: float, As_prime: float = 0) -> float:
    """
    计算单筋/双筋矩形截面受弯承载力
    
    Args:
        b: 截面宽度 (mm)
        h: 截面高度 (mm)
        As: 受拉钢筋面积 (mm²)
        As_prime: 受压钢筋面积 (mm²), 默认0
    
    Returns:
        Mn: 名义弯矩承载力 (kN·m)
    """
    h0 = get_h0(h)
    a_s_prime = C_COVER + D_STIRRUP + 10  # 受压钢筋合力点到压边的距离
    
    # 相对界限受压区高度
    xi_b = BETA_1 / (1 + F_Y / (E_S * 0.0033))  # 约 0.518 for HRB400
    
    # 受压区高度 x
    x = (F_Y * As - F_Y_PRIME * As_prime) / (ALPHA_1 * F_C * b)
    
    # 检查是否超筋
    if x > xi_b * h0:
        # 超筋梁，按界限状态计算
        x = xi_b * h0
    
    # 确保 x >= 2*a_s' (否则受压钢筋不屈服)
    if x < 2 * a_s_prime and As_prime > 0:
        x = 2 * a_s_prime
    
    # 弯矩承载力
    Mn = ALPHA_1 * F_C * b * x * (h0 - x / 2) + F_Y_PRIME * As_prime * (h0 - a_s_prime)
    
    # 转换为 kN·m
    return Mn / 1e6


def calculate_phi_Mn(b: float, h: float, As: float, As_prime: float = 0) -> float:
    """计算设计弯矩承载力 φMn (取 φ=0.9)"""
    return 0.9 * calculate_beam_Mn(b, h, As, As_prime)


# =============================================================================
# 梁斜截面受剪承载力 (GB 50010-2010 第6.3节)
# =============================================================================

def calculate_beam_Vn(b: float, h: float, s: float = 150, Asv: float = 100.5) -> float:
    """
    计算梁斜截面受剪承载力
    
    Args:
        b: 截面宽度 (mm)
        h: 截面高度 (mm)
        s: 箍筋间距 (mm), 默认150
        Asv: 单肢箍筋面积×肢数 (mm²), 默认 2φ8 = 100.5
    
    Returns:
        Vn: 受剪承载力 (kN)
    """
    h0 = get_h0(h)
    
    # 混凝土贡献项
    Vc = 0.7 * F_T * b * h0
    
    # 箍筋贡献项
    Vs = F_Y * Asv * h0 / s
    
    Vn = Vc + Vs
    
    return Vn / 1000  # 转换为 kN


def calculate_phi_Vn(b: float, h: float, s: float = 150, Asv: float = 100.5) -> float:
    """计算设计剪力承载力 φVn (取 φ=0.75)"""
    return 0.75 * calculate_beam_Vn(b, h, s, Asv)


# =============================================================================
# 综合承载力计算
# =============================================================================

def calculate_capacity(b: float, h: float, As: float, 
                       As_prime: float = 0, s: float = 150, 
                       Asv: float = 100.5) -> dict:
    """
    计算截面综合承载力
    
    Args:
        b, h: 截面尺寸 (mm)
        As: 受拉钢筋面积 (mm²)
        As_prime: 受压钢筋面积 (mm²)
        s: 箍筋间距 (mm)
        Asv: 箍筋面积 (mm²)
    
    Returns:
        dict: {'phi_Mn': kN·m, 'phi_Vn': kN, 'Mn': kN·m, 'Vn': kN}
    """
    return {
        'phi_Mn': calculate_phi_Mn(b, h, As, As_prime),
        'phi_Vn': calculate_phi_Vn(b, h, s, Asv),
        'Mn': calculate_beam_Mn(b, h, As, As_prime),
        'Vn': calculate_beam_Vn(b, h, s, Asv),
    }


# =============================================================================
# P-M 相互作用曲线 (柱) - GB 50010-2010 第6.2节
# =============================================================================

def generate_pm_curve(b: float, h: float, As_total: float, 
                      num_points: int = 50) -> List[Tuple[float, float]]:
    """
    生成 P-M 相互作用曲线 (GB 50010-2010 第6.2节)
    
    修正：弯矩 M 计算基于截面几何中心 (h/2)，以匹配结构分析输出。
    
    Args:
        b, h: 截面尺寸 (mm), b为宽度，h为弯矩作用方向高度
        As_total: 总配筋面积 (mm²), 假设对称配筋
        num_points: 曲线点数
    
    Returns:
        List[(P, M)]: P (kN) [压为正], M (kN·m) [取正值] 点列表
    """
    h0 = get_h0(h)
    a_s = h - h0  # 受拉钢筋合力点到受拉边缘距离
    a_s_prime = a_s  # 受压钢筋合力点到受压边缘距离（对称配筋）
    As = As_total / 2  # 对称配筋，每侧一半
    As_prime = As
    
    # 界限相对受压区高度
    xi_b = BETA_1 / (1 + F_Y / (E_S * 0.0033))
    x_b = xi_b * h0
    
    points = []
    
    # 从纯压 (x=h) 到接近纯弯 (x→0) 遍历
    for i in range(num_points + 1):
        # x 从 h (纯压) 递减到 接近0 (纯弯附近)
        x = h * (1 - i / num_points)
        x = max(1.0, min(x, h))  # 避免x过小导致除零
        
        # ===== 钢筋应力计算 =====
        # 受压钢筋应力 sigma_s_prime (Top steel)
        # 定义：正值为压力 (Compression)
        if x >= 2 * a_s_prime:
            sigma_s_prime = F_Y_PRIME
        else:
            # 应变: eps = 0.0033 * (x - as') / x
            # 若 x < as', 应变为负(拉)，应力为负(拉)
            eps_s_prime = 0.0033 * (x - a_s_prime) / x
            sigma_s_prime = E_S * eps_s_prime
            sigma_s_prime = max(-F_Y, min(F_Y_PRIME, sigma_s_prime))
        
        # 受拉钢筋应力 sigma_s (Bottom steel)
        # 定义：正值为拉力 (Tension)
        if x <= x_b:
            sigma_s = F_Y
        else:
            # 应变: eps = 0.0033 * (h0 - x) / x
            # 若 x > h0 (小偏压), 应变为负(压), 应力为负(压)
            eps_s = 0.0033 * (h0 - x) / x
            sigma_s = E_S * eps_s
            sigma_s = max(-F_Y_PRIME, min(F_Y, sigma_s))
        
        # ===== 截面承载力计算 (对几何中心取矩) =====
        
        # 1. 轴力 N (压为正)
        # N = C_c + C_s' - T_s
        # sigma_s_prime为正(压)，sigma_s为正(拉)
        N = ALPHA_1 * F_C * b * x + sigma_s_prime * As_prime - sigma_s * As
        
        # 2. 弯矩 M (对截面几何中心 h/2 取矩)
        # 规定：使截面受压区(Top)受压的弯矩为正
        # - 混凝土压力 C_c: 位于 x/2 处。力臂 (h/2 - x/2)。产生正弯矩。
        # - 上部钢筋力 C_s': 位于 as' 处。力臂 (h/2 - as')。
        #   若 sigma_s_prime > 0 (压), 产生正弯矩。
        #   若 sigma_s_prime < 0 (拉), 产生负弯矩 (抵抗)。
        #   项: + sigma_s_prime * As_prime * (h/2 - a_s_prime)
        # - 下部钢筋力 T_s: 位于 h-as 处。
        #   若 sigma_s > 0 (拉), 向外拉。力臂 (h/2 - as)。产生正弯矩 (助攻)。
        #   若 sigma_s < 0 (压), 向里压。产生负弯矩 (抵抗)。
        #   项: + sigma_s * As * (h/2 - a_s)
        
        M_center = (ALPHA_1 * F_C * b * x * (0.5 * h - 0.5 * x) + 
                    sigma_s_prime * As_prime * (0.5 * h - a_s_prime) + 
                    sigma_s * As * (0.5 * h - a_s))
        
        # 转换单位
        P = N / 1000            # kN (压为正)
        M_val = abs(M_center) / 1e6  # kN·m (取绝对值用于包络线)
        
        points.append((P, M_val))
    
    return points


def check_pm_capacity(P_u: float, M_u: float, pm_curve: List[Tuple[float, float]]) -> bool:
    """
    检查 (P_u, M_u) 是否在 P-M 曲线内部
    
    Args:
        P_u: 设计轴力 (kN)
        M_u: 设计弯矩 (kN·m)
        pm_curve: P-M 曲线点列表
    
    Returns:
        bool: True 表示安全
    """
    # 简化判断：线性插值找对应轴力下的承载力
    for i in range(len(pm_curve) - 1):
        P1, M1 = pm_curve[i]
        P2, M2 = pm_curve[i + 1]
        
        # 检查 P_u 是否在 P1, P2 区间内
        if min(P1, P2) <= P_u <= max(P1, P2):
            # 线性插值计算当前轴力下的最大弯矩 M_capacity
            if abs(P2 - P1) < 1e-6:
                M_capacity = max(M1, M2)
            else:
                t = (P_u - P1) / (P2 - P1)
                M_capacity = M1 + t * (M2 - M1)
            
            # 允许 5% 的计算容差
            return abs(M_u) <= abs(M_capacity) * 1.05
    
    # P_u 超出范围 (例如极大压力或极大拉力)
    P_min = min(p[0] for p in pm_curve)
    P_max = max(p[0] for p in pm_curve)
    
    return P_min <= P_u <= P_max


# =============================================================================
# 默认配筋方案
# =============================================================================

# 常用钢筋面积 (mm²)
REBAR_AREAS = {
    '2φ16': 402,
    '2φ18': 509,
    '2φ20': 628,
    '3φ20': 942,
    '4φ20': 1257,
    '2φ22': 760,
    '3φ22': 1140,
    '4φ22': 1520,
    '2φ25': 982,
    '3φ25': 1473,
    '4φ25': 1964,
}

# 默认配筋 (用于快速验算)
DEFAULT_REBAR = REBAR_AREAS['3φ20']  # 942 mm²


# =============================================================================
# 测试代码
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("承载力计算器测试 (GB 50010-2010)")
    print("=" * 60)
    
    # 测试梁承载力
    b, h = 250, 500
    As = REBAR_AREAS['3φ20']  # 942 mm²
    
    cap = calculate_capacity(b, h, As)
    print(f"\n梁截面: {b}x{h} mm, 配筋: 3φ20 ({As} mm²)")
    print(f"  φMn = {cap['phi_Mn']:.2f} kN·m")
    
    # 测试 P-M 曲线
    print("\n" + "=" * 60)
    print("柱 P-M 相互作用曲线测试")
    print("=" * 60)
    
    b_col, h_col = 400, 400
    As_col = REBAR_AREAS['4φ22']  # 1520 mm²
    
    pm_curve = generate_pm_curve(b_col, h_col, As_col)
    
    print(f"\n柱截面: {b_col}x{h_col} mm, 配筋: 4φ22 ({As_col} mm²)")
    print("P-M 曲线关键点 (P, M_center):")
    for i in [0, len(pm_curve)//2, -1]:
        P, M = pm_curve[i]
        print(f"  P = {P:.1f} kN, M = {M:.2f} kN·m")
    
    # 简单验证: 纯压承载力
    # N0 = 1.0*14.3*400*400 + 360*1520 = 2288000 + 547200 = 2835200 N = 2835 kN
    print(f"  预期纯压承载力 N0 ≈ 2835 kN")
    print(f"  计算最大轴力 Pmax = {max(p[0] for p in pm_curve):.1f} kN")
