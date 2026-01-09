"""
优化器模块 - 遗传算法驱动的框架优化
基于 PyGAD 实现自适应惩罚和分组编码
"""

import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Callable
import numpy as np
import pygad

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from phase1.section_database import SectionDatabase
from phase4.data_models import GridInput, ElementForces, OptimizationResult
from phase4.structure_model import StructureModel
from phase4.section_verifier import SectionVerifier


class FrameOptimizer:
    """
    框架优化器
    
    使用遗传算法优化多层RC框架的截面配置
    
    特性:
    - 分组编码: 6个基因 [标准梁, 屋面梁, 底层柱, 标准角柱, 标准内柱, 顶层柱]
    - 自适应惩罚: 根据可行解比例动态调整惩罚系数
    - 自适应变异: 根据种群多样性动态调整变异率
    - 自适应交叉: 根据收敛进度动态调整交叉概率
    """
    
    def __init__(self, 
                 grid: GridInput, 
                 db: SectionDatabase = None):
        """
        初始化优化器
        
        Args:
            grid: 轴网配置
            db: 截面数据库
        """
        self.grid = grid
        self.db = db if db else SectionDatabase()
        
        # 核心组件
        self.model = StructureModel(self.db)
        self.verifier = SectionVerifier(self.db)
        
        # 构建结构模型
        self.model.build_from_grid(grid)
        
        # 预计算P-M曲线
        self.verifier.precompute_pm_curves()
        
        # 自适应惩罚系数
        self.alpha = 2.0           # 惩罚指数
        self.penalty_coeff = 1.0   # 惩罚系数 (动态调整)
        
        # 自适应遗传算法参数
        self.mutation_prob = 0.30      # 初始变异率
        self.crossover_prob = 0.85     # 初始交叉概率
        self.mutation_prob_min = 0.10  # 变异率下限
        self.mutation_prob_max = 0.50  # 变异率上限
        self.crossover_prob_min = 0.60 # 交叉概率下限
        self.crossover_prob_max = 0.95 # 交叉概率上限
        
        # 优化历史
        self.fitness_history: List[float] = []
        self.cost_history: List[float] = []
        self.variance_history: List[float] = []
        self.feasible_ratio_history: List[float] = []
        self.mutation_history: List[float] = []   # 变异率历史
        self.crossover_history: List[float] = []  # 交叉概率历史
        
        # 当代统计
        self._current_gen_feasible = 0
        self._current_gen_total = 0
    
    def calculate_cost(self, genes: List[int]) -> float:
        """
        计算总造价
        
        Args:
            genes: [标准梁, 屋面梁, 底层柱, 标准角柱, 标准内柱, 顶层柱]
            
        Returns:
            造价 (元)
        """
        # 获取截面信息
        std_beam = self.db.get_by_index(genes[0])
        roof_beam = self.db.get_by_index(genes[1])
        bottom_col = self.db.get_by_index(genes[2])
        std_corner_col = self.db.get_by_index(genes[3])
        std_interior_col = self.db.get_by_index(genes[4])
        top_col = self.db.get_by_index(genes[5])
        
        # 构件数量 - 使用正确的分组键
        n_std_beams = len(self.model.beam_groups.get('standard', []))
        n_roof_beams = len(self.model.beam_groups.get('roof', []))
        n_bottom_cols = len(self.model.column_groups.get('bottom', []))
        n_std_corner_cols = len(self.model.column_groups.get('standard_corner', []))
        n_std_interior_cols = len(self.model.column_groups.get('standard_interior', []))
        n_top_cols = len(self.model.column_groups.get('top', []))
        
        # 平均长度 (m)
        avg_beam_length = np.mean(self.grid.x_spans) / 1000
        avg_col_length = np.mean(self.grid.z_heights) / 1000
        
        # 总造价 - 计算所有6类构件
        cost = (
            std_beam['cost_per_m'] * avg_beam_length * n_std_beams +
            roof_beam['cost_per_m'] * avg_beam_length * n_roof_beams +
            bottom_col['cost_per_m'] * avg_col_length * n_bottom_cols +
            std_corner_col['cost_per_m'] * avg_col_length * n_std_corner_cols +
            std_interior_col['cost_per_m'] * avg_col_length * n_std_interior_cols +
            top_col['cost_per_m'] * avg_col_length * n_top_cols
        )
        
        return cost
    
    def fitness_func(self, ga_instance, solution, solution_idx) -> float:
        """
        适应度函数
        
        流程:
        1. 解码基因 → 截面配置
        2. 更新结构模型
        3. 运行分析
        4. 验算所有构件
        5. 计算惩罚和造价
        6. 返回适应度
        
        Args:
            ga_instance: PyGAD实例
            solution: 基因序列
            solution_idx: 个体索引
            
        Returns:
            适应度值 (越大越好)
        """
        genes = [int(g) for g in solution]
        
        try:
            # 1. 设置截面
            self.model.set_sections_by_groups(genes)
            
            # 2. 重建和分析模型
            self.model.build_anastruct_model()
            forces = self.model.analyze()
            
            # 3. 验算所有构件 (承载力验算)
            total_penalty, _ = self.verifier.verify_all_elements(
                forces,
                self.model.beam_sections,
                self.model.column_sections
            )
            
            # 4. 检查拓扑约束 (强柱弱梁)
            topo_penalty = self.verifier.check_topology_constraints(genes, self.grid)
            total_penalty += topo_penalty
            
            # 5. 计算造价
            cost = self.calculate_cost(genes)
            
            # 7. 计算适应度
            # F = cost × (1 + penalty)^α
            F = cost * (1 + self.penalty_coeff * total_penalty) ** self.alpha
            fitness = 1.0 / (F + 1e-9)
            
            # 统计可行解
            self._current_gen_total += 1
            if total_penalty == 0:
                self._current_gen_feasible += 1
            
            return fitness
            
        except Exception as e:
            # 分析失败，返回极低适应度
            return 1e-12
    
    def on_generation(self, ga_instance) -> None:
        """
        每代回调：记录历史并自适应调整所有参数
        
        自适应策略:
        1. 惩罚系数: 根据可行解比例调整
        2. 变异率: 根据种群多样性(适应度方差)调整
        3. 交叉概率: 根据收敛进度调整
        """
        gen = ga_instance.generations_completed
        fitness_values = ga_instance.last_generation_fitness
        
        # 计算统计量
        variance = np.var(fitness_values)
        best_fitness = np.max(fitness_values)
        avg_fitness = np.mean(fitness_values)
        
        # 归一化的多样性指标 (基于变异系数)
        # 避免除零
        diversity = np.std(fitness_values) / (avg_fitness + 1e-12)
        
        # 可行解比例
        feasible_ratio = (self._current_gen_feasible / self._current_gen_total 
                          if self._current_gen_total > 0 else 0)
        
        # 正确计算当代最优造价
        best_idx = np.argmax(fitness_values)
        best_solution = ga_instance.population[best_idx]
        best_genes = [int(g) for g in best_solution]
        best_cost = self.calculate_cost(best_genes)
        
        # 记录历史
        self.fitness_history.append(best_fitness)
        self.cost_history.append(best_cost)
        self.variance_history.append(variance)
        self.feasible_ratio_history.append(feasible_ratio)
        self.mutation_history.append(self.mutation_prob)
        self.crossover_history.append(self.crossover_prob)
        
        # ============== 自适应参数调整 (每3代调整一次) ==============
        if gen % 3 == 0:
            # 1. 自适应惩罚系数
            if feasible_ratio > 0.7:
                self.penalty_coeff *= 0.9  # 放松惩罚
            elif feasible_ratio < 0.2:
                self.penalty_coeff *= 1.1  # 加强惩罚
            self.penalty_coeff = np.clip(self.penalty_coeff, 0.5, 3.0)
            
            # 2. 自适应变异率 (根据多样性)
            # 多样性低 -> 提高变异 ; 多样性高 -> 降低变异
            if diversity < 0.05:  # 种群收敛，多样性低
                self.mutation_prob = min(
                    self.mutation_prob * 1.2, 
                    self.mutation_prob_max
                )
            elif diversity > 0.3:  # 种群发散，多样性高
                self.mutation_prob = max(
                    self.mutation_prob * 0.85, 
                    self.mutation_prob_min
                )
            
            # 3. 自适应交叉概率 (根据收敛进度)
            # 早期高交叉促进探索，后期低交叉促进开发
            progress = gen / ga_instance.num_generations
            target_crossover = self.crossover_prob_max - (
                (self.crossover_prob_max - self.crossover_prob_min) * progress
            )
            # 平滑过渡
            self.crossover_prob = 0.7 * self.crossover_prob + 0.3 * target_crossover
            
            # 更新 GA 实例的参数
            ga_instance.mutation_probability = self.mutation_prob
            ga_instance.crossover_probability = self.crossover_prob
        
        # 重置计数器
        self._current_gen_feasible = 0
        self._current_gen_total = 0
        
        # 打印进度
        if gen % 10 == 0 or gen == 1:
            print(f"  Gen {gen:3d}: 造价={best_cost:,.0f}元, "
                  f"可行解={feasible_ratio*100:.0f}%, "
                  f"Pm={self.mutation_prob:.2f}, "
                  f"Pc={self.crossover_prob:.2f}")
    
    def run(self, 
            num_generations: int = 100,
            sol_per_pop: int = 50,
            random_seed: int = 42) -> OptimizationResult:
        """
        运行遗传算法优化
        
        Args:
            num_generations: 迭代代数
            sol_per_pop: 种群大小
            random_seed: 随机种子
            
        Returns:
            OptimizationResult: 优化结果
        """
        print("=" * 70)
        print("Phase 4C: 框架优化系统")
        print("=" * 70)
        print(f"框架规模: {self.grid.num_spans}跨 × {self.grid.num_stories}层")
        print(f"构件数量: {self.model.grid.num_beams}梁 + {self.model.grid.num_columns}柱")
        print(f"基因数量: 6 (分组编码)")
        print(f"搜索空间: {len(self.db)}^6 = {len(self.db)**6:,} 种组合")
        print(f"种群大小: {sol_per_pop}")
        print(f"迭代代数: {num_generations}")
        print("-" * 70)
        
        # 重置历史和自适应参数
        self.fitness_history.clear()
        self.cost_history.clear()
        self.variance_history.clear()
        self.feasible_ratio_history.clear()
        self.mutation_history.clear()
        self.crossover_history.clear()
        self.penalty_coeff = 1.0
        self.mutation_prob = 0.30
        self.crossover_prob = 0.85
        
        # GA配置 - 全自动自适应参数
        # 变异率和交叉概率将在 on_generation 回调中动态调整
        ga_instance = pygad.GA(
            num_generations=num_generations,
            num_parents_mating=max(20, sol_per_pop // 2),  # 父代数量50%
            fitness_func=self.fitness_func,
            sol_per_pop=sol_per_pop,
            num_genes=6,  # [标准梁, 屋面梁, 底层柱, 标准角柱, 标准内柱, 顶层柱]
            gene_type=int,
            gene_space={'low': 0, 'high': len(self.db) - 1},
            
            # 选择 - 锦标赛选择平衡探索与开发
            parent_selection_type="tournament",
            K_tournament=3,
            keep_elitism=2,  # 保留2个精英
            
            # 交叉 - 初始值，后续自适应调整
            crossover_type="two_points",  # 两点交叉
            crossover_probability=self.crossover_prob,
            
            # 变异 - 初始值，后续自适应调整
            mutation_type="random",
            mutation_probability=self.mutation_prob,
            mutation_num_genes=2,  # 每次变异2个基因
            
            # 回调
            on_generation=self.on_generation,
            
            # 随机种子
            random_seed=random_seed,
        )
        
        # 运行优化
        print("\n优化进度:")
        ga_instance.run()
        
        # 获取最优解
        solution, solution_fitness, _ = ga_instance.best_solution()
        best_genes = [int(g) for g in solution]
        best_cost = 1.0 / solution_fitness
        
        # 解析最优解
        self.model.set_sections_by_groups(best_genes)
        self.model.build_anastruct_model()
        forces = self.model.analyze()
        
        # 打印结果
        print("\n" + "=" * 70)
        print("✓ 优化完成")
        print("=" * 70)
        print(f"最优基因: {best_genes}")
        
        names = ['标准梁', '屋面梁', '底层柱', '标准角柱', '标准内柱', '顶层柱']
        for i, name in enumerate(names):
            sec_idx = best_genes[i]
            sec = self.db.get_by_index(sec_idx)
            print(f"  {name}: {sec['b']}×{sec['h']}")
        
        return OptimizationResult(
            genes=best_genes,
            cost=best_cost,
            fitness=solution_fitness,
            forces=forces,
            convergence_history=self.cost_history,
            fitness_history=ga_instance.best_solutions_fitness,
            cost_history=self.cost_history,  # 传递造价历史
            feasible_ratio_history=self.feasible_ratio_history,  # 传递可行解比例历史
        )



# =============================================================================
# 测试代码
# =============================================================================

if __name__ == "__main__":
    # 定义示例轴网
    grid = GridInput(
        x_spans=[6000, 6000, 6000],    # 3跨，每跨6m
        z_heights=[4000, 3500, 3500, 3500, 3500],  # 5层
        q_dead=25.0,
        q_live=10.0,
    )
    
    # 创建优化器
    db = SectionDatabase()
    optimizer = FrameOptimizer(grid, db)
    
    # 运行优化 (测试用较少代数)
    result = optimizer.run(
        num_generations=30,  # 测试用30代
        sol_per_pop=30,
        random_seed=42,
    )
    
    print(f"\n收敛历史: 初始={optimizer.cost_history[0]:,.0f}元 → "
          f"最终={optimizer.cost_history[-1]:,.0f}元")
