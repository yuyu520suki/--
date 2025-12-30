# 工程合规性检查脚本
import sys
sys.path.insert(0, '.')

from phase1.section_database import SectionDatabase
from phase4.data_models import GridInput
from phase4.structure_model import StructureModel
from phase4.section_verifier import SectionVerifier

db = SectionDatabase()

print("=" * 60)
print("工程合规性检查报告")
print("=" * 60)

# 1. 截面宽高比检查 (柱: b/h >= 0.4)
print("\n1. 柱截面宽高比检查 (GB50010规定b/h>=0.4):")
bad_ratio = []
for i in range(len(db)):
    sec = db.get_by_index(i)
    if sec['b'] / sec['h'] < 0.4:
        bad_ratio.append((i, sec['b'], sec['h']))
if bad_ratio:
    print(f"   违规截面数: {len(bad_ratio)} 个")
    for idx, b, h in bad_ratio[:3]:
        print(f"   - 截面{idx}: {b}x{h}, b/h={b/h:.2f}")
else:
    print("   ✓ 所有截面均满足 b/h >= 0.4")

# 2. 梁最小宽度检查 (b >= 200mm)
print("\n2. 梁最小宽度检查 (GB50010规定b>=200mm):")
small = [i for i in range(len(db)) if db.get_by_index(i)['b'] < 200]
print(f"   宽度<200mm的截面数: {len(small)}")

# 3. 内力值合理性检查
print("\n3. 内力值合理性检查:")
grid = GridInput(
    x_spans=[6000, 6000, 6000],
    z_heights=[4000, 3500, 3500, 3500, 3500],
    q_dead=25.0, q_live=10.0
)
model = StructureModel(db)
model.build_from_grid(grid)
model.set_sections_by_groups([35, 35, 45, 40])
model.build_anastruct_model()
forces = model.analyze()

beams = [f for f in forces.values() if f.element_type == 'beam']
cols = [f for f in forces.values() if f.element_type == 'column']

print(f"   梁弯矩范围: {min(f.M_design for f in beams):.0f} ~ {max(f.M_design for f in beams):.0f} kN·m")
print(f"   梁剪力范围: {min(f.V_design for f in beams):.0f} ~ {max(f.V_design for f in beams):.0f} kN")
print(f"   柱轴力范围: {min(f.N_design for f in cols):.0f} ~ {max(f.N_design for f in cols):.0f} kN")

# 理论校核
q = 1.2*25 + 1.4*10  # 44 kN/m (设计荷载)
L = 6  # m
M_simple = q * L**2 / 8
print(f"   理论简支梁弯矩: qL^2/8 = {M_simple:.0f} kN.m (连续梁约70%)")
print(f"   实测/理论比: {max(f.M_design for f in beams)/M_simple:.2f} (应约0.6~0.8)")

# 4. 轴压比检查
print("\n4. 柱轴压比检查 (非抗震μ≤0.9):")
verifier = SectionVerifier(db)
fc = 14.3  # C30
max_mu = 0
for f in cols:
    sec_idx = model.column_sections.get(f.element_id, 40)
    sec = db.get_by_index(sec_idx)
    Ag = sec['b'] * sec['h']
    mu = abs(f.N_design) * 1000 / (fc * Ag)
    if mu > max_mu:
        max_mu = mu
        max_col = f.element_id
print(f"   最大轴压比: μ={max_mu:.3f} (柱{max_col})")
print(f"   状态: {'✓ 满足' if max_mu <= 0.9 else '✗ 超限'}")

# 5. 配筋率检查
print("\n5. 配筋率检查 (GB50010):")
from phase4.section_verifier import DEFAULT_BEAM_AS, DEFAULT_COL_AS
sec35 = db.get_by_index(35)
rho_beam = DEFAULT_BEAM_AS / (sec35['b'] * (sec35['h']-40)) * 100
sec45 = db.get_by_index(45)
rho_col = DEFAULT_COL_AS / (sec45['b'] * sec45['h']) * 100
print(f"   梁配筋率: {rho_beam:.2f}% (最小0.2%, 最大2.5%)")
print(f"   柱配筋率: {rho_col:.2f}% (最小0.6%, 最大5%)")
beam_ok = 0.2 <= rho_beam <= 2.5
col_ok = 0.6 <= rho_col <= 5.0
print(f"   梁: {'✓' if beam_ok else '✗ 违规'}, 柱: {'✓' if col_ok else '✗ 违规'}")

print("\n" + "=" * 60)
print("检查完成")
print("=" * 60)
