"""
蒙特卡洛基准测试模块
通过随机截面组合验证结果分布的合理性

详细输出计算过程和公式
"""

import sys
from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np
import random

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.data_models import GridInput, ElementForces


def run_monte_carlo_test(grid: GridInput,
                         model_class,
                         db,
                         n_samples: int = 15,
                         seed: int = 42) -> Tuple[bool, Dict]:
    """
    蒙特卡洛基准测试
    
    原理：随机生成多组截面配置，统计内力分布，检测异常值
    
    Args:
        grid: 轴网配置
        model_class: StructureModel类（用于创建新模型）
        db: 截面数据库
        n_samples: 采样次数
        seed: 随机种子
        
    Returns:
        (通过/失败, 详细结果字典)
    """
    result = {
        'check_name': '蒙特卡洛基准测试',
        'passed': False,
        'n_samples': n_samples,
        'calculation_details': '',
        'cost_mean': 0.0,
        'cost_std': 0.0,
        'cost_cv': 0.0,
        'max_moment_mean': 0.0,
        'max_moment_std': 0.0,
        'max_axial_mean': 0.0,
        'max_axial_std': 0.0,
        'outliers': [],
        'message': '',
    }
    
    print("\n" + "=" * 70)
    print("【蒙特卡洛基准测试】基于统计学原理")
    print("=" * 70)
    
    try:
        random.seed(seed)
        np.random.seed(seed)
        
        # =====================================================================
        # 第一步：测试参数说明
        # =====================================================================
        print("\n▶ 第一步：测试参数说明")
        print("-" * 50)
        
        n_sections = len(db)
        
        print(f"  采样次数: n = {n_samples}")
        print(f"  随机种子: seed = {seed}")
        print(f"  截面库大小: {n_sections} 种截面")
        print(f"  结构规模: {grid.num_spans}跨 × {grid.num_stories}层")
        
        print(f"\n  随机采样策略:")
        print(f"    每次随机生成6个基因（截面索引）")
        print(f"    运行结构分析，记录内力和造价")
        print(f"    统计分析检测异常值")
        
        # =====================================================================
        # 第二步：执行随机采样
        # =====================================================================
        print("\n▶ 第二步：执行随机采样")
        print("-" * 50)
        
        costs = []
        max_moments = []
        max_axials = []
        sample_results = []
        
        print(f"\n  正在采样 (共{n_samples}次)...")
        
        for i in range(n_samples):
            try:
                # 随机生成6基因截面配置
                genes = [
                    random.randint(20, n_sections - 10),  # 标准梁
                    random.randint(20, n_sections - 10),  # 屋面梁
                    random.randint(30, n_sections - 1),   # 底层柱
                    random.randint(25, n_sections - 5),   # 标准角柱
                    random.randint(25, n_sections - 5),   # 标准内柱
                    random.randint(20, n_sections - 10),  # 顶层柱
                ]
                
                # 创建模型并分析
                model = model_class(db)
                model.build_from_grid(grid)
                model.set_sections_by_groups(genes)
                model.build_anastruct_model()
                forces = model.analyze()
                
                # 计算造价
                cost = _calculate_cost(genes, db, grid, model)
                costs.append(cost)
                
                # 统计最大内力
                max_M = max(f.M_design for f in forces.values())
                max_N = max(f.N_design for f in forces.values())
                max_moments.append(max_M)
                max_axials.append(max_N)
                
                sample_results.append({
                    'id': i + 1,
                    'genes': genes,
                    'cost': cost,
                    'max_M': max_M,
                    'max_N': max_N
                })
                
                # 显示进度
                if (i + 1) % 5 == 0 or i == 0:
                    print(f"    样本 {i+1}: 造价={cost:.0f}元, 最大弯矩={max_M:.1f}kN·m, 最大轴力={max_N:.0f}kN")
                
            except Exception as e:
                print(f"    样本 {i+1}: 失败 - {str(e)}")
                continue
        
        if len(costs) < 5:
            result['message'] = f'✗ 采样不足: 仅有 {len(costs)} 个有效样本'
            print(f"\n  ✗ 错误：有效样本数量不足")
            return False, result
        
        print(f"\n  成功采样: {len(costs)} / {n_samples}")
        
        # =====================================================================
        # 第三步：统计分析
        # =====================================================================
        print("\n▶ 第三步：统计分析")
        print("-" * 50)
        
        # 计算统计量
        cost_mean = np.mean(costs)
        cost_std = np.std(costs)
        cost_cv = cost_std / cost_mean if cost_mean > 0 else 0
        
        moment_mean = np.mean(max_moments)
        moment_std = np.std(max_moments)
        
        axial_mean = np.mean(max_axials)
        axial_std = np.std(max_axials)
        
        result['cost_mean'] = cost_mean
        result['cost_std'] = cost_std
        result['cost_cv'] = cost_cv
        result['max_moment_mean'] = moment_mean
        result['max_moment_std'] = moment_std
        result['max_axial_mean'] = axial_mean
        result['max_axial_std'] = axial_std
        
        print(f"  造价统计:")
        print(f"    均值: μ = {cost_mean:,.0f} 元")
        print(f"    标准差: σ = {cost_std:,.0f} 元")
        print(f"    变异系数: CV = σ/μ = {cost_cv*100:.1f}%")
        
        print(f"\n  弯矩统计:")
        print(f"    均值: μ_M = {moment_mean:.1f} kN·m")
        print(f"    标准差: σ_M = {moment_std:.1f} kN·m")
        
        print(f"\n  轴力统计:")
        print(f"    均值: μ_N = {axial_mean:.0f} kN")
        print(f"    标准差: σ_N = {axial_std:.0f} kN")
        
        # =====================================================================
        # 第四步：异常值检测 (3σ准则)
        # =====================================================================
        print("\n▶ 第四步：异常值检测 (3σ准则)")
        print("-" * 50)
        
        print(f"  3σ准则说明:")
        print(f"    若样本值超出 μ ± 3σ 范围，判定为异常值")
        print(f"    z = |x - μ| / σ > 3 → 异常")
        
        outliers = []
        for sample in sample_results:
            z_cost = abs(sample['cost'] - cost_mean) / cost_std if cost_std > 0 else 0
            z_M = abs(sample['max_M'] - moment_mean) / moment_std if moment_std > 0 else 0
            z_N = abs(sample['max_N'] - axial_mean) / axial_std if axial_std > 0 else 0
            
            if z_cost > 3 or z_M > 3 or z_N > 3:
                outliers.append({
                    'sample_id': sample['id'],
                    'z_cost': z_cost,
                    'z_M': z_M,
                    'z_N': z_N
                })
        
        result['outliers'] = outliers
        
        print(f"\n  异常值检测结果:")
        if outliers:
            for out in outliers:
                print(f"    样本 {out['sample_id']}: z_cost={out['z_cost']:.2f}, z_M={out['z_M']:.2f}, z_N={out['z_N']:.2f}")
        else:
            print(f"    未检测到异常值 ✓")
        
        # =====================================================================
        # 第五步：综合判断
        # =====================================================================
        print("\n▶ 第五步：综合判断")
        print("-" * 50)
        
        # 判断标准
        cv_ok = 0.05 < cost_cv < 0.60  # 变异系数在合理范围
        outlier_ok = len(outliers) < n_samples * 0.15  # 异常值少于15%
        
        print(f"  判断标准:")
        print(f"    1. 变异系数: 5% < CV < 60%")
        print(f"       实际: CV = {cost_cv*100:.1f}% → {'✓' if cv_ok else '✗'}")
        print(f"    2. 异常值比例: < 15%")
        print(f"       实际: {len(outliers)}/{len(costs)} = {len(outliers)/len(costs)*100:.0f}% → {'✓' if outlier_ok else '✗'}")
        
        if cv_ok and outlier_ok:
            result['passed'] = True
            result['message'] = f'✓ 蒙特卡洛测试通过: CV={cost_cv*100:.1f}%, 异常值={len(outliers)}个'
            print(f"\n  ✓ 结论：蒙特卡洛测试通过！")
        else:
            issues = []
            if not cv_ok:
                issues.append(f'CV={cost_cv*100:.1f}%异常')
            if not outlier_ok:
                issues.append(f'异常值={len(outliers)}个')
            result['message'] = f'✗ 蒙特卡洛测试不通过: {", ".join(issues)}'
            print(f"\n  ✗ 结论：蒙特卡洛测试不通过！")
        
        # 生成详细说明
        result['calculation_details'] = f"""
【蒙特卡洛基准测试计算过程】

1. 测试参数:
   采样次数: n = {n_samples}
   有效样本: {len(costs)}

2. 造价统计:
   均值: μ = {cost_mean:,.0f} 元
   标准差: σ = {cost_std:,.0f} 元
   变异系数: CV = σ/μ = {cost_cv*100:.1f}%

3. 弯矩统计:
   均值: μ_M = {moment_mean:.1f} kN·m
   标准差: σ_M = {moment_std:.1f} kN·m

4. 轴力统计:
   均值: μ_N = {axial_mean:.0f} kN
   标准差: σ_N = {axial_std:.0f} kN

5. 异常值检测 (3σ准则):
   异常值数量: {len(outliers)}
   异常值比例: {len(outliers)/len(costs)*100:.0f}%

6. 判断标准:
   变异系数: 5% < CV < 60% → {'✓' if cv_ok else '✗'}
   异常值比例: < 15% → {'✓' if outlier_ok else '✗'}

结论: {'✓ 测试通过' if result['passed'] else '✗ 测试不通过'}
"""
    
    except Exception as e:
        result['message'] = f'✗ 测试失败: {str(e)}'
        print(f"  ✗ 错误: {str(e)}")
        import traceback
        traceback.print_exc()
    
    print("=" * 70)
    return result['passed'], result


def _calculate_cost(genes: List[int], db, grid: GridInput, model) -> float:
    """简化的造价计算"""
    try:
        cost = 0.0
        avg_beam_len = np.mean(grid.x_spans) / 1000
        avg_col_len = np.mean(grid.z_heights) / 1000
        
        # 梁
        for i, group in enumerate(['standard', 'roof']):
            n = len(model.beam_groups.get(group, []))
            sec = db.get_by_index(genes[i])
            cost += sec['cost_per_m'] * avg_beam_len * n
        
        # 柱
        for i, group in enumerate(['bottom', 'standard_corner', 'standard_interior', 'top']):
            n = len(model.column_groups.get(group, []))
            sec = db.get_by_index(genes[i + 2])
            cost += sec['cost_per_m'] * avg_col_len * n
        
        return cost
    except:
        return 0.0


if __name__ == "__main__":
    print("蒙特卡洛基准测试模块")
    print("请通过 model_validator.py 运行完整测试")
