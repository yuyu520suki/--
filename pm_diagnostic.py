# PM曲线深度诊断脚本
# 按用户建议逐项检查

import sys
sys.path.insert(0, 'c:/Users/tw/Desktop/毕设')

from phase1.capacity_calculator import (
    generate_pm_curve, check_pm_capacity, REBAR_AREAS,
    F_C, F_Y, F_Y_PRIME, E_S, ALPHA_1, BETA_1, get_h0
)
from phase1.section_database import SectionDatabase

print("=" * 70)
print("PM曲线深度诊断")
print("=" * 70)

# 测试截面: 400x400, C30, HRB400, 对称配筋 4φ22 (约1.9%)
b = 400  # mm
h = 400  # mm
As_total = REBAR_AREAS['4φ22']  # 1521 mm²
As = As_total / 2  # 每侧

print(f"\n【1】截面参数检查")
print(f"  b = {b} mm, h = {h} mm")
print(f"  总配筋面积 As_total = {As_total} mm²")
print(f"  每侧配筋 As = As' = {As} mm²")
print(f"  配筋率 ρ = {As_total / (b * h) * 100:.2f}%")

h0 = get_h0(h)
a_s = h - h0
print(f"  有效高度 h0 = h - as = {h} - {a_s} = {h0} mm")

print(f"\n【2】材料参数检查")
print(f"  混凝土 fc = {F_C} MPa")
print(f"  钢筋 fy = {F_Y} MPa, fy' = {F_Y_PRIME} MPa")
print(f"  α1 = {ALPHA_1}, β1 = {BETA_1}")
print(f"  Es = {E_S} MPa")

# 界限受压区高度
xi_b = BETA_1 / (1 + F_Y / (E_S * 0.0033))
x_b = xi_b * h0
print(f"  界限相对受压区高度 ξb = {xi_b:.4f}")
print(f"  界限受压区高度 xb = ξb × h0 = {x_b:.1f} mm")

print(f"\n【3】手算关键点验算")

# 关键点1: 纯压状态 (x = h)
# N0 = α1*fc*b*h + fy'*As' + fy'*As (全截面受压，两侧钢筋都受压)
N0 = ALPHA_1 * F_C * b * h + F_Y_PRIME * As + F_Y_PRIME * As
P0 = N0 / 1000
print(f"  纯压承载力 N0 = α1*fc*b*h + 2*fy'*As")
print(f"     = {ALPHA_1}×{F_C}×{b}×{h} + 2×{F_Y_PRIME}×{As}")
print(f"     = {ALPHA_1 * F_C * b * h / 1000:.1f} + {2 * F_Y_PRIME * As / 1000:.1f}")
print(f"     = {N0/1000:.1f} kN")

# 关键点2: 界限状态 (x = xb, 大小偏心分界)
# Nb = α1*fc*b*xb + fy'*As' - fy*As
Nb = ALPHA_1 * F_C * b * x_b + F_Y_PRIME * As - F_Y * As
# Mb = α1*fc*b*xb*(h0 - xb/2) + fy'*As'*(h0 - as')
Mb = ALPHA_1 * F_C * b * x_b * (h0 - x_b / 2) + F_Y_PRIME * As * (h0 - a_s)
print(f"\n  界限状态 (x = xb = {x_b:.1f} mm):")
print(f"    Nb = α1*fc*b*xb + fy'*As' - fy*As")
print(f"       = {ALPHA_1 * F_C * b * x_b / 1000:.1f} + {F_Y_PRIME * As / 1000:.1f} - {F_Y * As / 1000:.1f}")
print(f"       = {Nb/1000:.1f} kN")
print(f"    Mb = α1*fc*b*xb*(h0-xb/2) + fy'*As'*(h0-as')")
print(f"       = {Mb/1e6:.2f} kN·m")

# 关键点3: 纯弯状态 (N = 0)
# 对于对称配筋，N=0时 x很小
# α1*fc*b*x + fy'*As' = fy*As
# 对称配筋时 x = 0 (或接近0)
# M0 ≈ fy*As*(h0 - as')
M0_approx = F_Y * As * (h0 - a_s)
print(f"\n  纯弯状态 (N ≈ 0):")
print(f"    M0 ≈ fy*As*(h0-as') = {F_Y}×{As}×({h0}-{a_s})")
print(f"       ≈ {M0_approx/1e6:.2f} kN·m")

print(f"\n【4】代码生成的PM曲线")
pm_curve = generate_pm_curve(b, h, As_total, num_points=50)
P_vals = [p[0] for p in pm_curve]
M_vals = [p[1] for p in pm_curve]

print(f"  点数: {len(pm_curve)}")
print(f"  P范围: {min(P_vals):.1f} ~ {max(P_vals):.1f} kN")
print(f"  M范围: {min(M_vals):.2f} ~ {max(M_vals):.2f} kN·m")

# 找到关键点
P_at_max = max(P_vals)
M_at_P_max = M_vals[P_vals.index(P_at_max)]
M_max = max(M_vals)
P_at_M_max = P_vals[M_vals.index(M_max)]

print(f"\n  曲线关键点:")
print(f"    最大P点: P = {P_at_max:.1f} kN, M = {M_at_P_max:.2f} kN·m")
print(f"    最大M点: P = {P_at_M_max:.1f} kN, M = {M_max:.2f} kN·m")

print(f"\n【5】与手算结果对比")
print(f"  纯压承载力: 手算 {P0:.1f} kN, 代码 {P_at_max:.1f} kN, 偏差 {(P_at_max-P0)/P0*100:+.1f}%")
print(f"  界限弯矩:   手算 {Mb/1e6:.2f} kN·m, (需找相近P点对比)")

# 找最接近Nb的点
closest_idx = min(range(len(P_vals)), key=lambda i: abs(P_vals[i] - Nb/1000))
M_at_Nb = M_vals[closest_idx]
print(f"  在P≈{Nb/1000:.0f}kN处: 手算M={Mb/1e6:.2f} kN·m, 代码M={M_at_Nb:.2f} kN·m")

print(f"\n【6】问题诊断")
print(f"  ⚠ 检查点:")
# 检查弯矩计算公式
# 原代码: M = α1*fc*b*x*(h/2 - x/2) + As*σs'*(h/2 - as) + As*σs*(h/2 - as)
# 正确公式应该是对受拉钢筋合力点取矩，或对形心取矩后转换
print(f"  - 原代码弯矩公式对形心取矩，但力臂计算可能有误")
print(f"  - 应该检查: 受压筋力臂 = h/2 - as' = {h/2 - a_s:.1f} mm")
print(f"  - 应该检查: 混凝土压力臂 = h/2 - x/2 (随x变化)")

# 输出完整曲线供分析
print(f"\n【7】完整PM曲线数据 (每隔5点)")
print(f"  {'i':>3} | {'P(kN)':>10} | {'M(kN·m)':>10}")
print(f"  {'-'*3} | {'-'*10} | {'-'*10}")
for i in range(0, len(pm_curve), 5):
    print(f"  {i:>3} | {P_vals[i]:>10.1f} | {M_vals[i]:>10.2f}")
print(f"  {len(pm_curve)-1:>3} | {P_vals[-1]:>10.1f} | {M_vals[-1]:>10.2f}")
