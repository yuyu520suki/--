"""
梁求解器 - 暴力搜索最经济截面
给定设计弯矩 Mu，找出满足承载力要求且成本最低的截面
"""

import sys
from pathlib import Path

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from phase1.section_database import SectionDatabase
from phase1.capacity_calculator import (
    calculate_capacity, 
    DEFAULT_REBAR,
    REBAR_AREAS,
)


def find_cheapest_section(Mu: float, 
                          rebar_options: list = None,
                          verbose: bool = False) -> dict:
    """
    暴力搜索：给定设计弯矩 Mu，找出满足 φMn >= Mu 且成本最低的截面
    
    Args:
        Mu: 设计弯矩 (kN·m)
        rebar_options: 可选的配筋列表 [As1, As2, ...] (mm²)
        verbose: 是否打印详细信息
    
    Returns:
        dict: 最优截面信息，包含索引、尺寸、配筋、成本等
              如未找到可行解，返回 None
    """
    db = SectionDatabase()
    
    # 默认配筋选项
    if rebar_options is None:
        rebar_options = [
            REBAR_AREAS['2φ16'],  # 402 mm²
            REBAR_AREAS['2φ20'],  # 628 mm²
            REBAR_AREAS['3φ20'],  # 942 mm²
            REBAR_AREAS['4φ20'],  # 1257 mm²
            REBAR_AREAS['3φ22'],  # 1140 mm²
            REBAR_AREAS['4φ22'],  # 1520 mm²
            REBAR_AREAS['3φ25'],  # 1473 mm²
            REBAR_AREAS['4φ25'],  # 1964 mm²
        ]
    
    feasible_solutions = []
    
    # 遍历所有截面和配筋组合
    for idx in range(len(db)):
        sec = db.get_by_index(idx)
        b, h = sec['b'], sec['h']
        
        for As in rebar_options:
            cap = calculate_capacity(b, h, As)
            phi_Mn = cap['phi_Mn']
            
            # 检查是否满足承载力要求
            if phi_Mn >= Mu:
                # 计算总成本 (混凝土+估算配筋)
                # 基础成本 + 额外钢筋成本
                base_cost = sec['cost_per_m']
                # 钢筋成本增量 (相对1.5%基准配筋率)
                A_base = 0.015 * b * h
                delta_steel = max(0, As - A_base) * 7.85e-6 * 1000 * 5.5
                total_cost = base_cost + delta_steel
                
                # 计算 D/C ratio
                dc_ratio = Mu / phi_Mn
                
                feasible_solutions.append({
                    'index': idx,
                    'b': b,
                    'h': h,
                    'As': As,
                    'phi_Mn': phi_Mn,
                    'phi_Vn': cap['phi_Vn'],
                    'cost_per_m': round(total_cost, 2),
                    'dc_ratio': round(dc_ratio, 3),
                })
    
    if not feasible_solutions:
        if verbose:
            print(f"警告: 未找到满足 Mu = {Mu} kN·m 的可行解!")
        return None
    
    # 按成本排序
    feasible_solutions.sort(key=lambda x: x['cost_per_m'])
    
    if verbose:
        print(f"\n找到 {len(feasible_solutions)} 个可行解")
        print("\n最经济的前5个解:")
        for i, sol in enumerate(feasible_solutions[:5]):
            print(f"  {i+1}. {sol['b']}x{sol['h']} mm, As={sol['As']} mm², "
                  f"φMn={sol['phi_Mn']:.1f} kN·m, 成本={sol['cost_per_m']:.1f} 元/m")
    
    return feasible_solutions[0]


def find_all_feasible_sections(Mu: float, Vu: float = None) -> list:
    """
    找出所有满足弯剪承载力要求的截面
    
    Args:
        Mu: 设计弯矩 (kN·m)
        Vu: 设计剪力 (kN), 可选
    
    Returns:
        list: 所有可行解列表，按成本排序
    """
    db = SectionDatabase()
    rebar_options = list(REBAR_AREAS.values())
    
    feasible = []
    
    for idx in range(len(db)):
        sec = db.get_by_index(idx)
        b, h = sec['b'], sec['h']
        
        for As in rebar_options:
            cap = calculate_capacity(b, h, As)
            
            # 弯矩验算
            if cap['phi_Mn'] < Mu:
                continue
            
            # 剪力验算 (如果指定)
            if Vu is not None and cap['phi_Vn'] < Vu:
                continue
            
            feasible.append({
                'index': idx,
                'b': b,
                'h': h,
                'As': As,
                'phi_Mn': cap['phi_Mn'],
                'phi_Vn': cap['phi_Vn'],
                'cost_per_m': sec['cost_per_m'],
            })
    
    feasible.sort(key=lambda x: x['cost_per_m'])
    return feasible


# =============================================================================
# 主程序 - 第一阶段里程碑测试
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("第一阶段里程碑: 单构件自动设计 (The Beam Solver)")
    print("=" * 70)
    print("目标: 给定设计弯矩 Mu = 150 kN·m, 找出最经济的梁截面")
    print("-" * 70)
    
    # 里程碑测试: Mu = 150 kN·m
    Mu_target = 150.0  # kN·m
    
    result = find_cheapest_section(Mu_target, verbose=True)
    
    if result:
        print("\n" + "=" * 70)
        print("✓ 最优解")
        print("=" * 70)
        print(f"  截面索引: {result['index']}")
        print(f"  截面尺寸: {result['b']} × {result['h']} mm")
        print(f"  配筋面积: {result['As']} mm²")
        print(f"  弯矩承载力: φMn = {result['phi_Mn']:.2f} kN·m")
        print(f"  剪力承载力: φVn = {result['phi_Vn']:.2f} kN")
        print(f"  设计弯矩: Mu = {Mu_target} kN·m")
        print(f"  D/C Ratio: {result['dc_ratio']:.3f} ({'安全' if result['dc_ratio'] <= 1.0 else '超限'})")
        print(f"  单位成本: {result['cost_per_m']:.2f} 元/m")
        print("=" * 70)
        print("\n✓ 第一阶段里程碑达成!")
        print("  输入: 弯矩值 Mu")
        print("  输出: 最经济的梁截面 (尺寸 + 配筋 + 成本)")
    else:
        print("\n✗ 第一阶段里程碑未达成: 未找到可行解")
    
    # 额外测试: 不同 Mu 值
    print("\n" + "-" * 70)
    print("扩展测试: 不同设计弯矩下的最优截面")
    print("-" * 70)
    
    test_Mu_values = [50, 100, 150, 200, 300, 400]
    
    print(f"{'Mu (kN·m)':<12} {'最优截面':<15} {'As (mm²)':<12} {'φMn':<12} {'成本 (元/m)':<12}")
    print("-" * 70)
    
    for Mu in test_Mu_values:
        result = find_cheapest_section(Mu)
        if result:
            print(f"{Mu:<12} {result['b']}x{result['h']:<10} {result['As']:<12} "
                  f"{result['phi_Mn']:<12.1f} {result['cost_per_m']:<12.1f}")
        else:
            print(f"{Mu:<12} {'无可行解':<15}")
