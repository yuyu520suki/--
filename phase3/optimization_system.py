"""
闭环优化系统 - 遗传算法驱动的结构优化
集成 Solver + Verifier + Navigator 三引擎
"""

import sys
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
import pygad

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from phase1.section_database import SectionDatabase
from phase1.capacity_calculator import (
    calculate_capacity,
    generate_pm_curve,
    check_pm_capacity,
    REBAR_AREAS,
)
from phase2.parametric_frame import ParametricFrame


# =============================================================================
# 全局配置
# =============================================================================

# 截面数据库
db = SectionDatabase()

# 参数化框架
frame = ParametricFrame(db, span=6000, height=3500)

# 默认配筋
DEFAULT_BEAM_AS = REBAR_AREAS['3φ20']   # 942 mm²
DEFAULT_COL_AS = REBAR_AREAS['4φ22']    # 1520 mm²

# 惩罚系数
ALPHA = 2.0  # 惩罚指数

# 拓扑约束 (柱截面不能比梁小太多)
MIN_COL_TO_BEAM_RATIO = 0.8


# =============================================================================
# 拓扑约束检查
# =============================================================================

def check_topology(genes: list) -> float:
    """
    检查拓扑约束
    返回违反程度 (0 表示满足，>0 表示违反)
    """
    beam_sec = db.get_by_index(genes[0])
    col_sec = db.get_by_index(genes[1])
    
    # 柱截面面积不应小于梁截面面积的 80%
    ratio = col_sec['A'] / beam_sec['A']
    
    if ratio < MIN_COL_TO_BEAM_RATIO:
        return MIN_COL_TO_BEAM_RATIO - ratio
    
    return 0


# =============================================================================
# 承载力验算
# =============================================================================

def check_beam_capacity(M_u: float, V_u: float, section: dict) -> tuple:
    """
    验算梁承载力
    返回 (弯矩超限程度, 剪力超限程度)
    """
    cap = calculate_capacity(section['b'], section['h'], DEFAULT_BEAM_AS)
    
    # D/C Ratio
    m_ratio = M_u / cap['phi_Mn'] if cap['phi_Mn'] > 0 else 999
    v_ratio = V_u / cap['phi_Vn'] if cap['phi_Vn'] > 0 else 999
    
    # 超限程度 (>0 表示不满足)
    m_excess = max(0, m_ratio - 1.0)
    v_excess = max(0, v_ratio - 1.0)
    
    return m_excess, v_excess


def check_column_capacity(M_u: float, N_u: float, section: dict) -> float:
    """
    验算柱承载力 (P-M 曲线)
    返回超限程度
    """
    pm_curve = generate_pm_curve(section['b'], section['h'], DEFAULT_COL_AS)
    
    # 检查是否在 P-M 曲线内
    is_safe = check_pm_capacity(N_u, M_u, pm_curve)
    
    if is_safe:
        return 0
    else:
        # 简化处理：返回固定惩罚
        return 0.5


# =============================================================================
# 成本计算
# =============================================================================

def calculate_total_cost(genes: list) -> float:
    """
    计算总造价 (元)
    假设梁长 = span, 柱长 = 2 * height
    """
    beam_sec = db.get_by_index(genes[0])
    col_sec = db.get_by_index(genes[1])
    
    beam_length = frame.span / 1000  # m
    col_length = 2 * frame.height / 1000  # 两根柱
    
    cost = (beam_sec['cost_per_m'] * beam_length + 
            col_sec['cost_per_m'] * col_length)
    
    return cost


# =============================================================================
# 适应度函数 (核心)
# =============================================================================

def fitness_function(ga_instance, solution, solution_idx):
    """
    适应度函数
    
    流程:
    1. 拓扑约束检查
    2. 结构分析 (Solver)
    3. 规范验算 (Verifier)
    4. 惩罚成本计算
    5. 返回适应度
    """
    genes = [int(g) for g in solution]
    
    violations = []
    
    # 1. 拓扑约束
    topo_violation = check_topology(genes)
    violations.append(topo_violation)
    
    # 2. 结构分析
    try:
        ss = frame.build_frame(genes)
        forces = frame.extract_forces(ss)
    except Exception as e:
        # 分析失败，返回极低适应度
        return 1e-9
    
    # 3. 承载力验算
    # 梁
    beam_sec = db.get_by_index(genes[0])
    for beam in forces['beams']:
        m_ex, v_ex = check_beam_capacity(beam['M_max'], beam['V_max'], beam_sec)
        violations.extend([m_ex, v_ex])
    
    # 柱
    col_sec = db.get_by_index(genes[1])
    for col in forces['columns']:
        col_ex = check_column_capacity(col['M_max'], col['N_max'], col_sec)
        violations.append(col_ex)
    
    # 4. 惩罚成本
    cost = calculate_total_cost(genes)
    P = sum(max(0, v) for v in violations)
    F = cost * (1 + P) ** ALPHA
    
    # 5. 适应度 (越大越好)
    fitness = 1.0 / (F + 1e-9)
    
    return fitness


# =============================================================================
# 自适应变异率回调
# =============================================================================

VARIANCE_HISTORY = []

def on_generation(ga_instance):
    """每代回调：自适应调整变异率"""
    global VARIANCE_HISTORY
    
    fitness_values = ga_instance.last_generation_fitness
    variance = np.var(fitness_values)
    VARIANCE_HISTORY.append(variance)
    
    # 自适应变异率
    if variance < 1e-6:  # 多样性极低
        ga_instance.mutation_probability = 0.25
    elif variance < 1e-4:  # 多样性不足
        ga_instance.mutation_probability = 0.15
    else:
        ga_instance.mutation_probability = 0.05
    
    # 每20代打印进度
    gen = ga_instance.generations_completed
    if gen % 20 == 0:
        best_fitness = np.max(fitness_values)
        best_cost = 1.0 / best_fitness if best_fitness > 0 else float('inf')
        print(f"  Gen {gen:3d}: Best Cost = {best_cost:.1f} 元, "
              f"Var = {variance:.2e}, Mut = {ga_instance.mutation_probability:.2f}")


# =============================================================================
# 运行优化
# =============================================================================

def run_optimization(num_generations: int = 100,
                     sol_per_pop: int = 50,
                     show_plot: bool = True) -> dict:
    """
    运行遗传算法优化
    
    Args:
        num_generations: 迭代代数
        sol_per_pop: 种群大小
        show_plot: 是否显示收敛曲线
    
    Returns:
        dict: 优化结果
    """
    global VARIANCE_HISTORY
    VARIANCE_HISTORY = []
    
    print("=" * 70)
    print("第三阶段: 闭环优化系统")
    print("=" * 70)
    print(f"种群大小: {sol_per_pop}")
    print(f"迭代代数: {num_generations}")
    print(f"基因数量: 2 (梁索引, 柱索引)")
    print(f"搜索空间: {len(db)} × {len(db)} = {len(db)**2} 种组合")
    print("-" * 70)
    
    # GA 配置
    ga_instance = pygad.GA(
        num_generations=num_generations,
        num_parents_mating=10,
        fitness_func=fitness_function,
        sol_per_pop=sol_per_pop,
        num_genes=2,  # [beam_idx, col_idx]
        gene_type=int,
        gene_space={'low': 0, 'high': len(db) - 1},
        
        # 选择
        parent_selection_type="tournament",
        K_tournament=5,
        keep_elitism=5,
        
        # 交叉
        crossover_type="single_point",
        crossover_probability=0.8,
        
        # 变异 (初始值，会被自适应调整)
        mutation_type="random",
        mutation_probability=0.1,
        
        # 回调
        on_generation=on_generation,
        
        # 随机种子
        random_seed=42,
    )
    
    # 运行优化
    print("\n优化进度:")
    ga_instance.run()
    
    # 获取最优解
    solution, solution_fitness, solution_idx = ga_instance.best_solution()
    best_genes = [int(g) for g in solution]
    best_cost = 1.0 / solution_fitness
    
    # 解析最优解
    beam_sec = db.get_by_index(best_genes[0])
    col_sec = db.get_by_index(best_genes[1])
    
    # 验算最优解
    ss = frame.build_frame(best_genes)
    forces = frame.extract_forces(ss)
    
    print("\n" + "=" * 70)
    print("✓ 优化完成")
    print("=" * 70)
    print(f"最优基因: {best_genes}")
    print(f"  梁截面: {beam_sec['b']} × {beam_sec['h']} mm")
    print(f"  柱截面: {col_sec['b']} × {col_sec['h']} mm")
    print(f"  总造价: {best_cost:.2f} 元")
    print(f"\n内力结果:")
    print(f"  梁 M_max = {forces['beams'][0]['M_max']:.2f} kN·m")
    print(f"  柱 N_max = {forces['columns'][0]['N_max']:.2f} kN")
    print("=" * 70)
    
    # 绘制收敛曲线
    if show_plot:
        plot_convergence(ga_instance)
    
    return {
        'genes': best_genes,
        'cost': best_cost,
        'beam_section': beam_sec,
        'column_section': col_sec,
        'forces': forces,
        'ga_instance': ga_instance,
    }


def plot_convergence(ga_instance):
    """绘制收敛曲线"""
    fitness_history = ga_instance.best_solutions_fitness
    cost_history = [1.0 / f if f > 0 else float('inf') for f in fitness_history]
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))
    
    # 成本曲线
    ax1.plot(cost_history, 'b-', linewidth=2)
    ax1.set_xlabel('Generation')
    ax1.set_ylabel('Best Cost (元)')
    ax1.set_title('Cost Convergence')
    ax1.grid(True, alpha=0.3)
    
    # 适应度方差曲线
    if VARIANCE_HISTORY:
        ax2.semilogy(VARIANCE_HISTORY, 'r-', linewidth=2)
        ax2.set_xlabel('Generation')
        ax2.set_ylabel('Fitness Variance (log)')
        ax2.set_title('Population Diversity')
        ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('convergence_curve.png', dpi=150)
    print("\n收敛曲线已保存: convergence_curve.png")
    plt.show()


# =============================================================================
# 主程序
# =============================================================================

if __name__ == "__main__":
    result = run_optimization(
        num_generations=100,
        sol_per_pop=50,
        show_plot=True
    )
