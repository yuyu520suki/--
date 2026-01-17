"""
对称性检查模块
验证：对称结构 + 对称荷载 → 对称内力

详细输出计算过程和公式
"""

import sys
from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.data_models import GridInput, ElementForces


def check_symmetry(grid: GridInput,
                   forces: Dict[int, ElementForces],
                   model,
                   tolerance: float = 0.10) -> Tuple[bool, Dict]:
    """
    对称性检查 - 几何直觉验证
    
    原理：对称结构在对称荷载下产生对称内力
    
    Args:
        grid: 轴网配置
        forces: 内力结果字典
        model: 结构模型（用于获取节点信息）
        tolerance: 允许偏差（默认10%）
        
    Returns:
        (通过/失败, 详细结果字典)
    """
    result = {
        'check_name': '对称性检查',
        'passed': False,
        'is_symmetric_grid': False,
        'calculation_details': '',
        'max_column_deviation': 0.0,
        'max_beam_deviation': 0.0,
        'tolerance_percent': tolerance * 100,
        'details': [],
        'message': '',
    }
    
    print("\n" + "=" * 70)
    print("【对称性检查】基于几何对称原理")
    print("=" * 70)
    
    try:
        # =====================================================================
        # 第一步：检查轴网是否对称
        # =====================================================================
        print("\n▶ 第一步：检查轴网对称性")
        print("-" * 50)
        
        spans = grid.x_spans
        n_spans = len(spans)
        
        print(f"  跨度列表: {[s/1000 for s in spans]} m")
        print(f"  跨数: {n_spans}")
        
        is_symmetric = True
        print(f"\n  对称性判断:")
        for i in range(n_spans // 2):
            left_span = spans[i]
            right_span = spans[n_spans - 1 - i]
            diff = abs(left_span - right_span)
            status = "✓" if diff < 1 else "✗"
            print(f"    L_{i+1} vs L_{n_spans-i}: {left_span/1000}m vs {right_span/1000}m → {status}")
            if diff >= 1:
                is_symmetric = False
        
        result['is_symmetric_grid'] = is_symmetric
        
        if not is_symmetric:
            result['message'] = '⚠ 轴网不对称，跳过对称性检查'
            result['passed'] = True
            print(f"\n  ⚠ 结论：轴网不对称，跳过对称性检查")
            return True, result
        
        print(f"\n  ✓ 轴网对称")
        
        # =====================================================================
        # 第一步续：检查荷载是否对称（水平荷载会打破对称性）
        # =====================================================================
        print("\n▶ 第一步续：检查荷载对称性")
        print("-" * 50)
        
        has_horizontal_load = False
        horizontal_load_type = []
        
        # 检查地震荷载
        if hasattr(grid, 'alpha_max') and grid.alpha_max > 0:
            has_horizontal_load = True
            horizontal_load_type.append(f"地震 (αmax={grid.alpha_max})")
            
        # 检查风荷载
        if hasattr(grid, 'w0') and grid.w0 > 0:
            has_horizontal_load = True
            horizontal_load_type.append(f"风 (w0={grid.w0} kN/m²)")
        
        if has_horizontal_load:
            result['passed'] = True
            result['message'] = f"⚠ 存在水平荷载 ({', '.join(horizontal_load_type)})，跳过对称性检查"
            print(f"  检测到水平荷载: {', '.join(horizontal_load_type)}")
            print(f"\n  ⚠ 结论：水平荷载会打破内力对称性，这是正常物理现象，跳过检查")
            print("=" * 70)
            return True, result
        
        print(f"  ✓ 仅有竖向荷载，继续检查内力对称性")
        
        # =====================================================================
        # 第二步：收集柱和梁的内力数据
        # =====================================================================
        print("\n▶ 第二步：收集构件内力数据")
        print("-" * 50)
        
        col_forces = {eid: f for eid, f in forces.items() if f.element_type == 'column'}
        beam_forces = {eid: f for eid, f in forces.items() if f.element_type == 'beam'}
        
        print(f"  柱数量: {len(col_forces)}")
        print(f"  梁数量: {len(beam_forces)}")
        
        # =====================================================================
        # 第三步：检查对称柱的轴力
        # =====================================================================
        print("\n▶ 第三步：检查对称柱的轴力")
        print("-" * 50)
        
        n_stories = grid.num_stories
        n_cols_per_story = n_spans + 1
        n_beams = n_spans * n_stories
        
        print(f"  每层柱数: {n_cols_per_story}")
        print(f"  层数: {n_stories}")
        
        max_col_dev = 0.0
        col_deviations = []
        
        print(f"\n  对称性验证公式:")
        print(f"    偏差 = |N_left - N_right| / max(N_left, N_right) × 100%")
        print(f"    允许偏差: {tolerance*100:.0f}%")
        
        # 柱ID计算: 柱ID = n_beams + col_idx * n_stories + story + 1
        # 即按柱列分组：col_idx=0的所有层、col_idx=1的所有层...
        
        for story in range(n_stories):  # 检查所有层
            print(f"\n  第 {story + 1} 层:")
            
            # 正确获取对称柱对
            for i in range(n_cols_per_story // 2):
                left_col_idx = i
                right_col_idx = n_cols_per_story - 1 - i
                
                # 使用正确的柱ID公式
                left_col_id = n_beams + left_col_idx * n_stories + story + 1
                right_col_id = n_beams + right_col_idx * n_stories + story + 1
                
                if left_col_id not in col_forces or right_col_id not in col_forces:
                    continue
                
                left_col = col_forces[left_col_id]
                right_col = col_forces[right_col_id]
                
                N_left = abs(left_col.axial_min)
                N_right = abs(right_col.axial_min)
                
                if max(N_left, N_right) > 1:
                    dev = abs(N_left - N_right) / max(N_left, N_right)
                    max_col_dev = max(max_col_dev, dev)
                    
                    status = "✓" if dev <= tolerance else "✗"
                    print(f"    柱{left_col_idx+1}(ID:{left_col_id}) vs 柱{right_col_idx+1}(ID:{right_col_id}): N={N_left:.1f} vs {N_right:.1f} kN → 偏差 {dev*100:.1f}% {status}")
                    
                    if dev > tolerance:
                        col_deviations.append({
                            'story': story + 1,
                            'left_id': left_col_id,
                            'right_id': right_col_id,
                            'N_left': N_left,
                            'N_right': N_right,
                            'deviation': dev * 100
                        })
        
        result['max_column_deviation'] = max_col_dev * 100
        
        # =====================================================================
        # 第四步：检查对称梁的弯矩
        # =====================================================================
        print("\n▶ 第四步：检查对称梁的弯矩")
        print("-" * 50)
        
        max_beam_dev = 0.0
        beam_deviations = []
        
        print(f"  对称性验证公式:")
        print(f"    偏差 = |M_left - M_right| / max(M_left, M_right) × 100%")
        
        # 梁ID计算: 梁ID = story * n_spans + span_idx + 1
        
        for story in range(n_stories):  # 检查所有层
            print(f"\n  第 {story + 1} 层:")
            
            for i in range(n_spans // 2):
                left_span_idx = i
                right_span_idx = n_spans - 1 - i
                
                # 使用正确的梁ID公式
                left_beam_id = story * n_spans + left_span_idx + 1
                right_beam_id = story * n_spans + right_span_idx + 1
                
                if left_beam_id not in beam_forces or right_beam_id not in beam_forces:
                    continue
                
                left_beam = beam_forces[left_beam_id]
                right_beam = beam_forces[right_beam_id]
                
                M_left = left_beam.M_design
                M_right = right_beam.M_design
                
                if max(M_left, M_right) > 1:
                    dev = abs(M_left - M_right) / max(M_left, M_right)
                    max_beam_dev = max(max_beam_dev, dev)
                    
                    status = "✓" if dev <= tolerance else "✗"
                    print(f"    梁{left_span_idx+1}(ID:{left_beam_id}) vs 梁{right_span_idx+1}(ID:{right_beam_id}): M={M_left:.1f} vs {M_right:.1f} kN·m → 偏差 {dev*100:.1f}% {status}")
                    
                    if dev > tolerance:
                        beam_deviations.append({
                            'story': story + 1,
                            'left_id': left_beam_id,
                            'right_id': right_beam_id,
                            'M_left': M_left,
                            'M_right': M_right,
                            'deviation': dev * 100
                        })
        
        result['max_beam_deviation'] = max_beam_dev * 100
        result['details'] = {
            'column_deviations': col_deviations,
            'beam_deviations': beam_deviations
        }
        
        # =====================================================================
        # 第五步：综合判断
        # =====================================================================
        print("\n▶ 第五步：综合判断")
        print("-" * 50)
        
        print(f"  柱最大偏差: {max_col_dev*100:.1f}%")
        print(f"  梁最大偏差: {max_beam_dev*100:.1f}%")
        print(f"  允许偏差: {tolerance*100:.0f}%")
        
        if max_col_dev <= tolerance and max_beam_dev <= tolerance:
            result['passed'] = True
            result['message'] = f'✓ 对称性满足: 柱偏差 {max_col_dev*100:.1f}%, 梁偏差 {max_beam_dev*100:.1f}%'
            print(f"\n  ✓ 结论：对称性检查通过！")
        else:
            result['message'] = f'✗ 对称性不满足: 柱偏差 {max_col_dev*100:.1f}%, 梁偏差 {max_beam_dev*100:.1f}%'
            print(f"\n  ✗ 结论：对称性检查不通过！")
        
        # 生成详细说明
        result['calculation_details'] = f"""
【对称性检查计算过程】

1. 轴网对称性:
   跨度: {[s/1000 for s in spans]} m
   结论: {'对称' if is_symmetric else '不对称'}

2. 柱ID计算公式:
   柱ID = 梁总数 + 柱列号 × 层数 + 层号 + 1

3. 对称柱轴力比较:
   公式: 偏差 = |N_left - N_right| / max(N_left, N_right) × 100%
   最大柱偏差: {max_col_dev*100:.1f}%

4. 对称梁弯矩比较:
   公式: 偏差 = |M_left - M_right| / max(M_left, M_right) × 100%
   最大梁偏差: {max_beam_dev*100:.1f}%

5. 验证标准:
   允许偏差: {tolerance*100:.0f}%
   
结论: {'✓ 满足对称性' if result['passed'] else '✗ 不满足对称性'}
"""
    
    except Exception as e:
        result['message'] = f'✗ 检查失败: {str(e)}'
        print(f"  ✗ 错误: {str(e)}")
        import traceback
        traceback.print_exc()
    
    print("=" * 70)
    return result['passed'], result


if __name__ == "__main__":
    print("对称性检查模块测试")
    print("请通过 model_validator.py 运行完整测试")
