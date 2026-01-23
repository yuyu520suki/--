"""
并行工作进程模块 - 用于多进程并行计算适应度

此模块提供进程安全的适应度评估函数，每个工作进程独立维护自己的模型实例，
避免了anaStruct对象的序列化问题，突破Python GIL限制实现真正的并行加速。

使用方法:
    from src.optimization.parallel_worker import init_worker, evaluate_solution
    
    with mp.Pool(n_workers, initializer=init_worker, initargs=(grid_dict, penalty_coeff)) as pool:
        fitness_values = pool.map(evaluate_solution, solutions)
"""

from typing import Dict, List, Optional
import numpy as np

# 延迟导入，避免循环依赖
_SectionDatabase = None
_StructureModel = None
_SectionVerifier = None
_GridInput = None

# 每个工作进程的本地存储
_worker_model = None
_worker_verifier = None
_worker_db = None
_worker_grid = None
_worker_penalty_coeff = 1.0
_worker_alpha = 2.0


def _lazy_import():
    """延迟导入模块，避免在主进程import时触发"""
    global _SectionDatabase, _StructureModel, _SectionVerifier, _GridInput
    if _SectionDatabase is None:
        from src.calculation.section_database import SectionDatabase as SD
        from src.models.structure_model import StructureModel as SM
        from src.analysis.analyzer import SectionVerifier as SV
        from src.models.data_models import GridInput as GI
        _SectionDatabase = SD
        _StructureModel = SM
        _SectionVerifier = SV
        _GridInput = GI


def init_worker(grid_dict: Dict, penalty_coeff: float = 1.0, alpha: float = 2.0) -> None:
    """
    工作进程初始化函数 (在每个进程启动时调用一次)
    
    Args:
        grid_dict: 轴网配置字典 (可序列化)
        penalty_coeff: 惩罚系数
        alpha: 惩罚指数
    """
    global _worker_model, _worker_verifier, _worker_db, _worker_grid
    global _worker_penalty_coeff, _worker_alpha
    
    _lazy_import()
    
    _worker_penalty_coeff = penalty_coeff
    _worker_alpha = alpha
    
    # 重建 GridInput 对象
    _worker_grid = _GridInput(
        x_spans=grid_dict['x_spans'],
        z_heights=grid_dict['z_heights'],
        q_dead=grid_dict.get('q_dead', 4.5),
        q_live=grid_dict.get('q_live', 2.5),
    )
    
    # 如果有地震参数
    if 'alpha_max' in grid_dict:
        _worker_grid.alpha_max = grid_dict['alpha_max']
    
    # 创建本地实例
    _worker_db = _SectionDatabase()
    _worker_model = _StructureModel(_worker_db)
    _worker_model.build_from_grid(_worker_grid)
    
    _worker_verifier = _SectionVerifier(_worker_db)
    _worker_verifier.precompute_pm_curves()


def evaluate_solution(genes_list: List[int]) -> float:
    """
    评估单个解的适应度 (在工作进程中执行)
    
    Args:
        genes_list: 基因列表 [标准梁, 屋面梁, 底层柱, 角柱, 内柱, 顶层柱]
        
    Returns:
        适应度值 (越大越好)
    """
    global _worker_model, _worker_verifier, _worker_db
    global _worker_penalty_coeff, _worker_alpha, _worker_grid
    
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
        topo_penalty = _worker_verifier.check_topology_constraints(genes_list, _worker_grid)
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
        
        avg_beam_length = np.mean(_worker_grid.x_spans) / 1000
        avg_col_length = np.mean(_worker_grid.z_heights) / 1000
        
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
        # 分析失败，返回极低适应度
        return 1e-12


def update_penalty_coeff(new_coeff: float) -> None:
    """更新惩罚系数（用于自适应调整）"""
    global _worker_penalty_coeff
    _worker_penalty_coeff = new_coeff
