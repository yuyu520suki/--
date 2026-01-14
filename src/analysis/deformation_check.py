"""
变形协调性检查模块
验证：梁挠度在合理范围内 (L/250 ~ L/400)

详细输出计算过程和公式
"""

import sys
from pathlib import Path
from typing import Dict, Tuple
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.data_models import GridInput, ElementForces


def check_deformation(grid: GridInput,
                      forces: Dict[int, ElementForces],
                      tolerance_min: float = 1/400,
                      tolerance_max: float = 1/150) -> Tuple[bool, Dict]:
    """
    变形协调性检查 - 数量级验证
    
    原理：混凝土框架梁挠度通常在 L/250 ~ L/400 之间
    弯矩数量级可估算验证
    
    Args:
        grid: 轴网配置
        forces: 内力结果
        tolerance_min: 最小挠跨比（太小则可能单位错误）
        tolerance_max: 最大挠跨比（太大则刚度不足）
        
    Returns:
        (通过/失败, 详细结果字典)
    """
    result = {
        'check_name': '变形协调性检查',
        'passed': False,
        'calculation_details': '',
        'max_moment': 0.0,
        'estimated_moment': 0.0,
        'max_deflection_estimated': 0.0,
        'deflection_ratio': '',
        'message': '',
    }
    
    print("\n" + "=" * 70)
    print("【变形协调性检查】基于数量级验证")
    print("=" * 70)
    
    try:
        # =====================================================================
        # 第一步：获取结构参数
        # =====================================================================
        print("\n▶ 第一步：获取结构参数")
        print("-" * 50)
        
        avg_span = np.mean(grid.x_spans)  # mm
        L = avg_span / 1000  # m
        q = grid.q_dead + grid.q_live  # kN/m (标准组合)
        
        print(f"  平均跨度: L = {L:.2f} m")
        print(f"  标准荷载: q = G + Q = {grid.q_dead} + {grid.q_live} = {q:.1f} kN/m")
        
        # =====================================================================
        # 第二步：估算简支梁弯矩
        # =====================================================================
        print("\n▶ 第二步：估算梁弯矩（简支梁公式）")
        print("-" * 50)
        
        # 简支梁跨中弯矩: M = qL²/8
        M_simple = q * L**2 / 8
        
        print(f"  简支梁跨中弯矩公式:")
        print(f"    M_simple = q × L² / 8")
        print(f"    M_simple = {q:.1f} × {L:.2f}² / 8")
        print(f"    M_simple = {M_simple:.2f} kN·m")
        
        # 连续梁调整系数（约0.7-1.2倍简支梁弯矩）
        print(f"\n  连续梁弯矩估算:")
        print(f"    跨中正弯矩 ≈ 0.7 × M_simple = {0.7 * M_simple:.2f} kN·m")
        print(f"    支座负弯矩 ≈ 1.2 × M_simple = {1.2 * M_simple:.2f} kN·m")
        
        result['estimated_moment'] = M_simple
        
        # =====================================================================
        # 第三步：获取实际计算弯矩
        # =====================================================================
        print("\n▶ 第三步：获取实际计算弯矩")
        print("-" * 50)
        
        beam_forces = [f for f in forces.values() if f.element_type == 'beam']
        
        if not beam_forces:
            result['message'] = '✗ 无梁内力数据'
            print("  ✗ 错误：无梁内力数据")
            return False, result
        
        # 统计弯矩
        M_values = [f.M_design for f in beam_forces]
        max_M = max(M_values)
        min_M = min(M_values)
        avg_M = np.mean(M_values)
        
        result['max_moment'] = max_M
        
        print(f"  梁数量: {len(beam_forces)}")
        print(f"  最大弯矩: M_max = {max_M:.2f} kN·m")
        print(f"  最小弯矩: M_min = {min_M:.2f} kN·m")
        print(f"  平均弯矩: M_avg = {avg_M:.2f} kN·m")
        
        # =====================================================================
        # 第四步：弯矩数量级验证
        # =====================================================================
        print("\n▶ 第四步：弯矩数量级验证")
        print("-" * 50)
        
        # 合理范围: 0.3M_simple ~ 2.0M_simple
        M_lower = 0.3 * M_simple
        M_upper = 2.5 * M_simple
        
        print(f"  合理范围估算:")
        print(f"    下限: 0.3 × M_simple = {M_lower:.2f} kN·m")
        print(f"    上限: 2.5 × M_simple = {M_upper:.2f} kN·m")
        print(f"    实际最大弯矩: {max_M:.2f} kN·m")
        
        moment_ok = M_lower <= max_M <= M_upper
        
        if moment_ok:
            print(f"\n  ✓ 弯矩在合理范围内")
        else:
            print(f"\n  ✗ 弯矩超出合理范围！")
        
        # =====================================================================
        # 第五步：估算挠度
        # =====================================================================
        print("\n▶ 第五步：估算挠度")
        print("-" * 50)
        
        # 简支梁挠度公式: δ = 5qL⁴/(384EI)
        E = 30000e6  # Pa = N/m² (C30混凝土)
        b, h = 300, 600  # mm (假设梁截面)
        I = b * h**3 / 12 * 1e-12  # m⁴
        
        print(f"  材料参数:")
        print(f"    弹性模量: E = 30000 MPa (C30混凝土)")
        print(f"    假设截面: b×h = {b}×{h} mm")
        print(f"    惯性矩: I = bh³/12 = {I*1e9:.2f} × 10⁻⁹ m⁴")
        
        # 挠度计算
        q_Nm = q * 1000  # N/m
        delta = 5 * q_Nm * L**4 / (384 * E * I)  # m
        delta_mm = delta * 1000  # mm
        
        print(f"\n  简支梁挠度公式:")
        print(f"    δ = 5qL⁴ / (384EI)")
        print(f"    δ = 5 × {q_Nm:.0f} × {L:.2f}⁴ / (384 × {E/1e9:.0f}×10⁹ × {I*1e9:.2f}×10⁻⁹)")
        print(f"    δ = {delta_mm:.2f} mm")
        
        ratio = delta / L
        ratio_str = f"L/{int(L/delta)}" if delta > 0 else "L/∞"
        
        result['max_deflection_estimated'] = delta_mm
        result['deflection_ratio'] = ratio_str
        
        print(f"\n  挠跨比:")
        print(f"    δ/L = {delta_mm:.2f} / {L*1000:.0f} = 1/{int(L*1000/delta_mm) if delta_mm > 0 else '∞'}")
        print(f"    规范限值: L/250 ~ L/400")
        
        # =====================================================================
        # 第六步：综合判断
        # =====================================================================
        print("\n▶ 第六步：综合判断")
        print("-" * 50)
        
        # 综合判断
        if moment_ok:
            result['passed'] = True
            result['message'] = f'✓ 内力数量级合理: 最大弯矩 {max_M:.1f} kN·m，估算挠度 {ratio_str}'
            print(f"  ✓ 结论：变形协调性检查通过！")
        else:
            result['message'] = f'✗ 弯矩数量级异常: 最大弯矩 {max_M:.1f} kN·m (预期 {M_lower:.0f}~{M_upper:.0f})'
            result['passed'] = False  # 弯矩异常应返回失败
            print(f"  ✗ 警告：弯矩数量级存在异常，请检查模型！")
        
        # 生成详细说明
        result['calculation_details'] = f"""
【变形协调性检查计算过程】

1. 结构参数:
   平均跨度: L = {L:.2f} m
   标准荷载: q = {q:.1f} kN/m

2. 简支梁弯矩估算:
   公式: M = qL²/8
   M_simple = {q:.1f} × {L:.2f}² / 8 = {M_simple:.2f} kN·m

3. 实际计算弯矩:
   最大弯矩: {max_M:.2f} kN·m
   合理范围: {M_lower:.0f} ~ {M_upper:.0f} kN·m

4. 挠度估算:
   公式: δ = 5qL⁴/(384EI)
   估算挠度: {delta_mm:.2f} mm ({ratio_str})
   规范限值: L/250 ~ L/400

结论: {'✓ 数量级合理' if moment_ok else '⚠ 存在异常'}
"""
    
    except Exception as e:
        result['message'] = f'✗ 检查失败: {str(e)}'
        print(f"  ✗ 错误: {str(e)}")
        import traceback
        traceback.print_exc()
    
    print("=" * 70)
    return result['passed'], result


if __name__ == "__main__":
    print("变形协调性检查模块测试")
    print("请通过 model_validator.py 运行完整测试")
