"""
优化器模块 - 遗传算法驱动的框架优化
基于 PyGAD 实现自适应惩罚和分组编码

特性:
- 支持多进程并行加速 (突破GIL限制，获得3-5x加速)
- 6基因分组编码: [标准梁, 屋面梁, 底层柱, 标准角柱, 标准内柱, 顶层柱]
- 自适应惩罚系数和变异率调整
"""

from typing import Dict, List, Tuple, Optional, Callable
import numpy as np
import os
import pygad
import multiprocessing as mp
from functools import partial

from src.calculation.section_database import SectionDatabase
from src.models.data_models import GridInput, ElementForces, OptimizationResult
from src.models.structure_model import StructureModel
from src.analysis.analyzer import SectionVerifier


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
        self.mutation_history: List[float] = []
        self.crossover_history: List[float] = []
        
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
        
        # 构件数量
        n_std_beams = len(self.model.beam_groups.get('standard', []))
        n_roof_beams = len(self.model.beam_groups.get('roof', []))
        n_bottom_cols = len(self.model.column_groups.get('bottom', []))
        n_std_corner_cols = len(self.model.column_groups.get('standard_corner', []))
        n_std_interior_cols = len(self.model.column_groups.get('standard_interior', []))
        n_top_cols = len(self.model.column_groups.get('top', []))
        
        # 平均长度 (m)
        avg_beam_length = np.mean(self.grid.x_spans) / 1000
        avg_col_length = np.mean(self.grid.z_heights) / 1000
        
        # 总造价
        cost = (
            std_beam['cost_per_m'] * avg_beam_length * n_std_beams +
            roof_beam['cost_per_m'] * avg_beam_length * n_roof_beams +
            bottom_col['cost_per_m'] * avg_col_length * n_bottom_cols +
            std_corner_col['cost_per_m'] * avg_col_length * n_std_corner_cols +
            std_interior_col['cost_per_m'] * avg_col_length * n_std_interior_cols +
            top_col['cost_per_m'] * avg_col_length * n_top_cols
        )
        
        return cost
    
    def _parallel_fitness_batch(self, ga_instance, solutions, solutions_indices):
        """
        批量并行评估适应度（使用进程池）
        
        当启用进程并行时，此函数会被PyGAD调用来批量评估整个种群。
        注意：每次评估都传递当前的惩罚系数，实现自适应惩罚策略在并行模式下的同步。
        """
        if self._pool is not None:
            # 使用进程池并行评估
            # 将 (genes, penalty_coeff, alpha) 打包为元组传递
            args_list = [
                ([int(g) for g in sol], self.penalty_coeff, self.alpha)
                for sol in solutions
            ]
            fitness_values = self._pool.map(self._evaluate_func, args_list)
            return fitness_values
        else:
            # 串行回退
            return [self.fitness_func(ga_instance, sol, idx) 
                    for sol, idx in zip(solutions, solutions_indices)]
    
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
        """
        gen = ga_instance.generations_completed
        fitness_values = ga_instance.last_generation_fitness
        
        # 计算统计量
        variance = np.var(fitness_values)
        best_fitness = np.max(fitness_values)
        avg_fitness = np.mean(fitness_values)
        
        # 归一化的多样性指标
        diversity = np.std(fitness_values) / (avg_fitness + 1e-12)
        
        # 可行解比例
        feasible_ratio = (self._current_gen_feasible / self._current_gen_total 
                          if self._current_gen_total > 0 else 0)
        
        # 获取历史最优解 (不是当代最优，是全局最优)
        best_solution, best_fit, _ = ga_instance.best_solution()
        best_genes = [int(g) for g in best_solution]
        best_cost = self.calculate_cost(best_genes)
        
        # 确保收敛曲线单调不增 (只记录更优的值)
        if len(self.cost_history) == 0 or best_cost < self.cost_history[-1]:
            self.cost_history.append(best_cost)
        else:
            self.cost_history.append(self.cost_history[-1])  # 保持前一代最优
        
        # 记录其他历史
        self.fitness_history.append(best_fitness)
        self.variance_history.append(variance)
        self.feasible_ratio_history.append(feasible_ratio)
        self.mutation_history.append(self.mutation_prob)
        self.crossover_history.append(self.crossover_prob)
        
        # 自适应参数调整 (每3代调整一次)
        if gen % 3 == 0:
            # 1. 自适应惩罚系数
            if feasible_ratio > 0.7:
                self.penalty_coeff *= 0.9
            elif feasible_ratio < 0.2:
                self.penalty_coeff *= 1.1
            self.penalty_coeff = np.clip(self.penalty_coeff, 0.5, 3.0)
            
            # 2. 自适应变异率
            if diversity < 0.05:
                self.mutation_prob = min(
                    self.mutation_prob * 1.2, 
                    self.mutation_prob_max
                )
            elif diversity > 0.3:
                self.mutation_prob = max(
                    self.mutation_prob * 0.85, 
                    self.mutation_prob_min
                )
            
            # 3. 自适应交叉概率
            progress = gen / ga_instance.num_generations
            target_crossover = self.crossover_prob_max - (
                (self.crossover_prob_max - self.crossover_prob_min) * progress
            )
            self.crossover_prob = 0.7 * self.crossover_prob + 0.3 * target_crossover
            
            # 更新 GA 实例的参数
            ga_instance.mutation_probability = self.mutation_prob
            ga_instance.crossover_probability = self.crossover_prob
        
        # 重置计数器
        self._current_gen_feasible = 0
        self._current_gen_total = 0
        
        # 打印进度 (更丰富的信息)
        if gen % 10 == 0 or gen == 1:
            # 进度条
            total_gens = ga_instance.num_generations
            progress_pct = gen / total_gens * 100
            bar_len = 20
            filled = int(bar_len * gen / total_gens)
            bar = '█' * filled + '░' * (bar_len - filled)
            
            print(f"  [{bar}] {progress_pct:5.1f}% | Gen {gen:3d}/{total_gens} | "
                  f"Cost: ¥{best_cost:,.0f} | Feasible: {feasible_ratio*100:.0f}% | "
                  f"Pm={self.mutation_prob:.2f} | λ={self.penalty_coeff:.2f}")
    
    def _on_generation_parallel(self, ga_instance):
        """
        并行模式每代回调 (带自适应策略)
        
        自适应策略 (基于收敛进度):
        1. 惩罚系数: 按进化阶段逐步递减 (前期严格，后期宽松)
        2. 变异率: 当连续多代无改进时增大变异率，防止陷入局部最优
        """
        gen = ga_instance.generations_completed
        total_gens = ga_instance.num_generations
        
        # 获取历史最优解
        best_solution, best_fitness, _ = ga_instance.best_solution()
        best_genes = [int(g) for g in best_solution]
        best_cost = self.calculate_cost(best_genes)
        
        # 记录是否有改进
        improved = False
        if len(self.cost_history) == 0 or best_cost < self.cost_history[-1]:
            self.cost_history.append(best_cost)
            improved = True
        else:
            self.cost_history.append(self.cost_history[-1])
        
        self.fitness_history.append(best_fitness)
        
        # ============ 自适应策略 (每5代调整一次) ============
        if gen % 5 == 0 and gen > 0:
            
            # 1. 自适应惩罚系数 (基于进化阶段)
            # 前期惩罚系数高，促进可行解搜索；后期降低，鼓励探索更优解
            progress = gen / total_gens
            target_penalty = 1.2 - 0.5 * progress  # 从1.2递减到0.7
            self.penalty_coeff = 0.8 * self.penalty_coeff + 0.2 * target_penalty
            self.penalty_coeff = np.clip(self.penalty_coeff, 0.5, 1.5)
            
            # 2. 自适应变异率 (基于收敛进度)
            # 检查最近10代的改进情况
            if len(self.cost_history) >= 10:
                recent_improvement = self.cost_history[-10] - self.cost_history[-1]
                improvement_rate = recent_improvement / (self.cost_history[-10] + 1e-9)
                
                if improvement_rate < 0.01:  # 改进不足1%，可能陷入局部最优
                    self.mutation_prob = min(self.mutation_prob * 1.15, 0.45)
                elif improvement_rate > 0.05:  # 改进良好，减小变异保护优良解
                    self.mutation_prob = max(self.mutation_prob * 0.9, 0.15)
            
            # 3. 更新GA实例参数
            ga_instance.mutation_probability = self.mutation_prob
        
        # 记录参数历史
        self.mutation_history.append(self.mutation_prob)
        
        # 打印进度
        if gen % 10 == 0 or gen == 1:
            progress_pct = gen / total_gens * 100
            bar_len = 20
            filled = int(bar_len * gen / total_gens)
            bar = '█' * filled + '░' * (bar_len - filled)
            
            print(f"  [{bar}] {progress_pct:5.1f}% | Gen {gen:3d}/{total_gens} | "
                  f"Cost: ¥{self.cost_history[-1]:,.0f} | Pm={self.mutation_prob:.2f} | λ={self.penalty_coeff:.2f}")
    
    def run(self, 
            num_generations: int = 100,
            sol_per_pop: int = 50,
            random_seed: int = 42,
            parallel: bool = True,
            n_workers: int = 6) -> OptimizationResult:
        """
        运行遗传算法优化
        
        Args:
            num_generations: 迭代代数
            sol_per_pop: 种群大小
            random_seed: 随机种子
            parallel: 是否启用并行计算
            n_workers: 并行工作进程数 (默认6，适合i7-12700H)
            
        Returns:
            OptimizationResult: 优化结果
        """
        import time
        
        mode_str = f"并行模式 ({n_workers} 进程)" if parallel else "串行模式"
        
        print("=" * 70)
        print("RC框架优化系统 - GB 55001-2021 合规版")
        print("=" * 70)
        print(f"框架规模: {self.grid.num_spans}跨 × {self.grid.num_stories}层")
        print(f"构件数量: {self.model.grid.num_beams}梁 + {self.model.grid.num_columns}柱")
        print(f"基因数量: 6 (分组编码)")
        print(f"搜索空间: {len(self.db)}^6 = {len(self.db)**6:,} 种组合")
        print(f"种群大小: {sol_per_pop}")
        print(f"迭代代数: {num_generations}")
        print(f"计算模式: {mode_str}")
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
        
        # 并行配置
        self._use_process_parallel = parallel
        self._pool = None
        self._grid_dict = None
        
        if parallel:
            # 使用多进程并行 (突破GIL限制)
            from src.optimization.parallel_worker import init_worker, evaluate_solution
            
            # 序列化GridInput为字典
            self._grid_dict = {
                'x_spans': list(self.grid.x_spans),
                'z_heights': list(self.grid.z_heights),
                'q_dead': self.grid.q_dead,
                'q_live': self.grid.q_live,
            }
            if hasattr(self.grid, 'alpha_max') and self.grid.alpha_max > 0:
                self._grid_dict['alpha_max'] = self.grid.alpha_max
            
            # 创建进程池
            self._pool = mp.Pool(
                n_workers, 
                initializer=init_worker, 
                initargs=(self._grid_dict, self.penalty_coeff, self.alpha)
            )
            self._evaluate_func = evaluate_solution
            print(f"[并行] 使用进程池 ({n_workers} 进程) - 突破GIL限制")
            
            # 进程并行时不使用PyGAD内置并行
            parallel_processing = None
        else:
            parallel_processing = None
        
        # GA配置 (统一配置)
        # 注: num_parents_mating 必须 <= sol_per_pop
        num_parents = min(max(10, sol_per_pop // 2), sol_per_pop - 2)
        
        # 选择fitness函数：进程并行使用批量评估
        if self._use_process_parallel:
            fitness_function = self._parallel_fitness_batch
            fitness_batch_size = sol_per_pop  # 整个种群批量评估
        else:
            fitness_function = self.fitness_func
            fitness_batch_size = None
        
        ga_instance = pygad.GA(
            num_generations=num_generations,
            num_parents_mating=num_parents,
            fitness_func=fitness_function,
            fitness_batch_size=fitness_batch_size,
            sol_per_pop=sol_per_pop,
            num_genes=6,
            gene_type=int,
            gene_space={'low': 0, 'high': len(self.db) - 1},
            
            # 选择
            parent_selection_type="tournament",
            K_tournament=3,
            keep_elitism=2,
            
            # 交叉
            crossover_type="two_points",
            crossover_probability=self.crossover_prob,
            
            # 变异
            mutation_type="random",
            mutation_probability=self.mutation_prob,
            mutation_num_genes=2,
            
            # 回调 (并行模式使用简化回调，只打印进度)
            on_generation=self._on_generation_parallel if parallel else self.on_generation,
            
            # 并行处理
            parallel_processing=parallel_processing,
            
            # 随机种子
            random_seed=random_seed,
        )
        
        # 运行优化
        print("\n优化进度:")
        start_time = time.time()
        ga_instance.run()
        elapsed_time = time.time() - start_time
        
        # 清理进程池
        if self._pool is not None:
            self._pool.close()
            self._pool.join()
            self._pool = None
        
        # 获取最优解
        solution, solution_fitness, _ = ga_instance.best_solution()
        best_genes = [int(g) for g in solution]
        
        # 重新计算纯造价（不含惩罚）
        best_cost = self.calculate_cost(best_genes)
        
        # 解析最优解
        self.model.set_sections_by_groups(best_genes)
        self.model.build_anastruct_model()
        forces = self.model.analyze()
        
        # 从GA历史重建收敛记录 (仅当回调未记录时)
        # 注: 如果 on_generation 回调已经记录了历史，这里不需要再添加
        if len(self.cost_history) == 0 and hasattr(ga_instance, 'best_solutions_fitness'):
            for fit in ga_instance.best_solutions_fitness:
                if fit > 0:
                    self.cost_history.append(1.0 / fit)
                    self.fitness_history.append(fit)
        
        # 打印详细结果
        print("\n" + "=" * 70)
        print("✓ 优化完成")
        print("=" * 70)
        
        # 时间和性能统计
        print(f"  运行时间: {elapsed_time:.1f} 秒")
        print(f"  总评估次数: ~{num_generations * sol_per_pop:,}")
        print(f"  搜索效率: {num_generations * sol_per_pop / elapsed_time:.0f} 解/秒")
        
        # 收敛统计
        if len(self.cost_history) > 1:
            initial_cost = self.cost_history[0]
            cost_reduction = (initial_cost - best_cost) / initial_cost * 100
            print(f"  初始造价: ¥{initial_cost:,.0f}")
            print(f"  最终造价: ¥{best_cost:,.0f}")
            print(f"  造价降幅: {cost_reduction:.1f}%")
        
        print("\n最优截面配置:")
        print("-" * 40)
        names = ['标准梁', '屋面梁', '底层柱', '标准角柱', '标准内柱', '顶层柱']
        for i, name in enumerate(names):
            sec_idx = best_genes[i]
            sec = self.db.get_by_index(sec_idx)
            cost_m = sec['cost_per_m']
            print(f"  {name:8s}: {sec['b']:3d}×{sec['h']:3d} mm  (¥{cost_m:.0f}/m)")
        print("=" * 70)
        
        return OptimizationResult(
            genes=best_genes,
            cost=best_cost,
            fitness=solution_fitness,
            forces=forces,
            convergence_history=self.cost_history,
            fitness_history=ga_instance.best_solutions_fitness if hasattr(ga_instance, 'best_solutions_fitness') else [],
            cost_history=self.cost_history,
            feasible_ratio_history=self.feasible_ratio_history,
        )


# =============================================================================
# 测试代码 - 串行/并行性能对比
# =============================================================================

if __name__ == "__main__":
    from src.models.data_models import GridInput
    import time
    
    # 配置
    grid = GridInput(
        x_spans=[6000, 6000, 6000],
        z_heights=[4000, 3500, 3500, 3500, 3500],
        q_dead=4.5,
    )
    
    NUM_GEN = 30
    POP_SIZE = 40
    N_WORKERS = 6  # i7-12700H 推荐使用 6 个 P 核
    
    print("\n" + "=" * 70)
    print("多核并行计算性能测试 (进程模式)")
    print("=" * 70)
    print(f"测试配置: {NUM_GEN} 代, 种群 {POP_SIZE}, 进程数 {N_WORKERS}")
    
    db = SectionDatabase()
    
    # 1. 并行模式测试
    print("\n>>> 测试 1: 并行模式 (6进程)")
    optimizer1 = FrameOptimizer(grid, db)
    t1_start = time.time()
    result1 = optimizer1.run(
        num_generations=NUM_GEN,
        sol_per_pop=POP_SIZE,
        random_seed=42,
        parallel=True,
        n_workers=N_WORKERS,
    )
    t1_elapsed = time.time() - t1_start
    
    # 2. 串行模式测试
    print("\n>>> 测试 2: 串行模式")
    optimizer2 = FrameOptimizer(grid, db)
    t2_start = time.time()
    result2 = optimizer2.run(
        num_generations=NUM_GEN,
        sol_per_pop=POP_SIZE,
        random_seed=42,
        parallel=False,
    )
    t2_elapsed = time.time() - t2_start
    
    # 性能对比
    print("\n" + "=" * 70)
    print("性能对比结果")
    print("=" * 70)
    print(f"并行模式耗时: {t1_elapsed:.1f} 秒")
    print(f"串行模式耗时: {t2_elapsed:.1f} 秒")
    if t1_elapsed > 0:
        speedup = t2_elapsed / t1_elapsed
        print(f"加速比: {speedup:.2f}x")
    print(f"并行最优造价: ¥{result1.cost:,.0f}")
    print(f"串行最优造价: ¥{result2.cost:,.0f}")
    print(f"结果一致性: {'✓ 一致' if abs(result1.cost - result2.cost) < 100 else '✗ 不一致'}")





