# 柱荷载点与PM曲线对比测试
import sys
sys.path.insert(0, 'c:/Users/tw/Desktop/毕设')

from phase1.capacity_calculator import generate_pm_curve, check_pm_capacity, REBAR_AREAS
from phase4.structure_model import StructureModel
from phase4.data_models import GridInput
from phase1.section_database import SectionDatabase

print("=" * 70)
print("柱荷载点 vs PM曲线 诊断")
print("=" * 70)

# 创建测试模型
grid = GridInput(
    x_spans=[6000, 6000, 6000],
    z_heights=[4000, 3500, 3500, 3500, 3500],
    q_dead=25.0,
    q_live=10.0,
)

db = SectionDatabase()
model = StructureModel(db)
model.build_from_grid(grid)

# 使用一个典型的优化结果基因
genes = [35, 35, 45, 45, 45, 35]
model.set_sections_by_groups(genes)
model.build_anastruct_model()
forces = model.analyze()

# 统计每种截面的情况
print(f"\n【1】结构分析完成")
print(f"  梁数: {len([f for f in forces.values() if f.element_type == 'beam'])}")
print(f"  柱数: {len([f for f in forces.values() if f.element_type == 'column'])}")

# 按截面分组统计柱
sec_groups = {}
for eid, f in forces.items():
    if f.element_type == 'column':
        sec_idx = model.column_sections.get(eid, 40)
        if sec_idx not in sec_groups:
            sec_groups[sec_idx] = []
        sec_groups[sec_idx].append((eid, f))

print(f"\n【2】柱截面分组")
for sec_idx, cols in sec_groups.items():
    sec = db.get_by_index(sec_idx)
    print(f"  截面{sec_idx} ({sec['b']}x{sec['h']} mm): {len(cols)} 根柱")

# 对每种截面检查PM曲线
As_col = REBAR_AREAS['4φ22']
print(f"\n【3】PM曲线验算 (配筋 As={As_col} mm²)")
print("-" * 70)

total_outside = 0
for sec_idx, cols in sec_groups.items():
    sec = db.get_by_index(sec_idx)
    pm_curve = generate_pm_curve(sec['b'], sec['h'], As_col, num_points=50)
    
    P_vals = [p[0] for p in pm_curve]
    M_vals = [p[1] for p in pm_curve]
    P_max = max(P_vals)
    M_max = max(M_vals)
    
    print(f"\n截面 {sec['b']}x{sec['h']} mm:")
    print(f"  PM曲线: P_max={P_max:.0f}kN, M_max={M_max:.1f}kN.m")
    
    outside_cols = []
    for eid, f in cols:
        # 轴力：anaStruct返回压力为负，取绝对值
        N = abs(f.axial_min)
        M = f.M_design
        
        # 检查是否在PM曲线内
        is_safe = check_pm_capacity(N, M, pm_curve)
        
        if not is_safe:
            outside_cols.append((eid, N, M))
            total_outside += 1
    
    if outside_cols:
        print(f"  ⚠ 超出包络线的柱 ({len(outside_cols)}/{len(cols)}):")
        for eid, N, M in outside_cols[:3]:  # 只显示前3个
            # 找对应N的M_capacity
            M_cap = 0
            for i in range(len(pm_curve)-1):
                P1, M1 = pm_curve[i]
                P2, M2 = pm_curve[i+1]
                if min(P1,P2) <= N <= max(P1,P2):
                    t = (N - P1) / (P2 - P1) if abs(P2-P1) > 1 else 0
                    M_cap = M1 + t * (M2 - M1)
                    break
            print(f"    柱{eid}: N={N:.0f}kN, M={M:.1f}kN.m (M_cap={M_cap:.1f})")
    else:
        print(f"  ✓ 全部在包络线内")

print(f"\n【4】总结")
print(f"  超出包络线的柱总数: {total_outside}")
if total_outside > 0:
    print(f"  ⚠ 存在不安全设计，需检查截面尺寸或PM曲线计算")
else:
    print(f"  ✓ 所有柱均在PM包络线内")
