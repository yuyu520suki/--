"""
优化器模块 - 遗传算法驱动的框架优化
基于 PyGAD 实现自适应惩罚和分组编码

特性:
- 支持 PyGAD 内置线程并行加速
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


# =============================================================================
# 并行计算 - 进程本地存储和工作函数
# =============================================================================

# 每个工作进程的本地存储
_worker_model: Optional[StructureModel] = None
_worker_verifier: Optional[SectionVerifier] = None
_worker_db: Optional[SectionDatabase] = None
_worker_penalty_coeff: float = 1.0
_worker_alpha: float = 2.0


def _init_worker_process(grid_dict: Dict, penalty_coeff: float, alpha: float) -> None:
    """
    工作进程初始化函数 (在每个进程启动时调用一次)
    
    Args:
        grid_dict: 轴网配置字典 (可序列化)
        penalty_coeff: 惩罚系数
        alpha: 惩罚指数
    """
    global _worker_model, _worker_verifier, _worker_db
    global _worker_penalty_coeff, _worker_alpha
    
    _worker_penalty_coeff = penalty_coeff
    _worker_alpha = alpha
    
    # 重建 GridInput 对象
    grid = GridInput(
        x_spans=grid_dict['x_spans'],
        z_heights=grid_dict['z_heights'],
        q_dead=grid_dict.get('q_dead', 4.5),
        q_live=grid_dict.get('q_live', 2.5),
    )
    
    # 如果有地震参数
    if 'alpha_max' in grid_dict:
        grid.alpha_max = grid_dict['alpha_max']
    
    # 创建本地实例
    _worker_db = SectionDatabase()
    _worker_model = StructureModel(_worker_db)
    _worker_model.build_from_grid(grid)
    
    _worker_verifier = SectionVerifier(_worker_db)
    _worker_verifier.precompute_pm_curves()


def _evaluate_single_solution(genes_list: List[int]) -> float:
    """
    评估单个解的适应度 (在工作进程中执行)
    
    Args:
        genes_list: 基因列表
        
    Returns:
        适应度值
    """
    global _worker_model, _worker_verifier, _worker_db
    global _worker_penalty_coeff, _worker_alpha
    
    try:
        # 1. 设置截面
        _worker_model.set_sections_by_groups(genes_list)
        
        # 2. 重建和分析模型
        _worker_model.build_anastruct_model()
        forces = _worker_model.analyze()
        
        # 3. 验算所有构件
        total_penalty, _ = _worker_verifier.verify_all_elements(
            forces,
            _worker_model.beam_sections,
            _worker_model.column_sections
        )
        
        # 4. 检查拓扑约束 (强柱弱梁)
        topo_penalty = _worker_verifier.check_topology_constraints(genes_list, _worker_model.grid)
        total_penalty += topo_penalty
        
        # 5. 计算造价
        std_beam = _worker_db.get_by_index(genes_list[0])
        roof_beam = _worker_db.get_by_index(genes_list[1])
        bottom_col = _worker_db.get_by_index(genes_list[2])
        std_corner_col = _worker_db.get_by_index(genes_list[3])
        std_interior_col = _worker_db.get_by_index(genes_list[4])
        top_col = _worker_db.get_by_index(genes_list[5])
        
        n_std_beams = len(_worker_model.beam_groups.get('standard', []))
        n_roof_beams = len(_worker_model.beam_groups.get('roof', []))
        n_bottom_cols = len(_worker_model.column_groups.get('bottom', []))
        n_std_corner_cols = len(_worker_model.column_groups.get('standard_corner', []))
        n_std_interior_cols = len(_worker_model.column_groups.get('standard_interior', []))
        n_top_cols = len(_worker_model.column_groups.get('top', []))
        
        avg_beam_length = np.mean(_worker_model.grid.x_spans) / 1000
        avg_col_length = np.mean(_worker_model.grid.z_heights) / 1000
        
        cost = (
            std_beam['cost_per_m'] * avg_beam_length * n_std_beams +
            roof_beam['cost_per_m'] * avg_beam_length * n_roof_beams +
            bottom_col['cost_per_m'] * avg_col_length * n_bottom_cols +
            std_corner_col['cost_per_m'] * avg_col_length * n_std_corner_cols +
            std_interior_col['cost_per_m'] * avg_col_length * n_std_interior_cols +
            top_col['cost_per_m'] * avg_col_length * n_top_cols
        )
        
        # 6. 计算适应度
        F = cost * (1 + _worker_penalty_coeff * total_penalty) ** _worker_alpha
        fitness = 1.0 / (F + 1e-9)
        
        return fitness
        
    except Exception as e:
        return 1e-12


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
                  f"Pm={self.mutation_prob:.2f}")
    
    def _on_generation_parallel(self, ga_instance):
        """
        并行模式每代回调 (简化版，只打印进度)
        
        注: 并行模式下不进行自适应参数调整，因为线程并发时
        统计数据可能不准确。
        """
        gen = ga_instance.generations_completed
        
        # 获取历史最优解 (全局最优，不是当代最优)
        best_solution, best_fitness, _ = ga_instance.best_solution()
        best_genes = [int(g) for g in best_solution]
        best_cost = self.calculate_cost(best_genes)  # 使用 calculate_cost 而不是从适应度反推
        
        # 确保收敛曲线单调不增
        if len(self.cost_history) == 0 or best_cost < self.cost_history[-1]:
            self.cost_history.append(best_cost)
        else:
            self.cost_history.append(self.cost_history[-1])  # 保持前一代最优
        
        self.fitness_history.append(best_fitness)
        
        # 每10代打印一次进度 (带进度条)
        if gen % 10 == 0 or gen == 1:
            total_gens = ga_instance.num_generations
            progress_pct = gen / total_gens * 100
            bar_len = 20
            filled = int(bar_len * gen / total_gens)
            bar = '█' * filled + '░' * (bar_len - filled)
            
            print(f"  [{bar}] {progress_pct:5.1f}% | Gen {gen:3d}/{total_gens} | "
                  f"Cost: ¥{self.cost_history[-1]:,.0f} [Parallel]")
    
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
        if parallel:
            # 使用 PyGAD 的线程并行 (Windows 上更稳定)
            # 注: 由于 Python GIL，线程并行对 CPU 密集型任务加速有限
            # 但仍比完全串行快，因为有 NumPy 的 C 扩展可以释放 GIL
            parallel_processing = ['thread', n_workers]
            print(f"[并行] 使用线程池 ({n_workers} 线程)")
        else:
            parallel_processing = None
        
        # GA配置 (统一配置)
        # 注: num_parents_mating 必须 <= sol_per_pop
        num_parents = min(max(10, sol_per_pop // 2), sol_per_pop - 2)
        ga_instance = pygad.GA(
            num_generations=num_generations,
            num_parents_mating=num_parents,
            fitness_func=self.fitness_func,
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
    print("多核并行计算性能测试 (线程模式)")
    print("=" * 70)
    print(f"测试配置: {NUM_GEN} 代, 种群 {POP_SIZE}, 线程数 {N_WORKERS}")
    
    db = SectionDatabase()
    
    # 1. 并行模式测试
    print("\n>>> 测试 1: 并行模式 (6线程)")
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





