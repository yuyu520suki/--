"""
模型验证器 - Phase 5 主模块
整合所有验证检查，提供统一的验证接口

详细输出计算过程和公式
"""

import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.data_models import GridInput, ElementForces
from src.analysis.equilibrium_check import check_global_equilibrium
from src.analysis.symmetry_check import check_symmetry
from src.analysis.deformation_check import check_deformation
from src.analysis.monte_carlo_test import run_monte_carlo_test


@dataclass
class ValidationResult:
    """验证结果汇总"""
    all_passed: bool = True
    checks: Dict[str, Dict] = field(default_factory=dict)
    summary: str = ""
    detailed_report: str = ""
    
    def add_check(self, name: str, passed: bool, details: Dict):
        """添加检查结果"""
        self.checks[name] = {
            'passed': passed,
            'details': details
        }
        if not passed:
            self.all_passed = False
    
    def generate_summary(self) -> str:
        """生成验证摘要"""
        lines = ["=" * 60, "Phase 5: 模型验证报告", "=" * 60, ""]
        
        for name, result in self.checks.items():
            status = "✓ 通过" if result['passed'] else "✗ 失败"
            message = result['details'].get('message', '')
            lines.append(f"{name}: {status}")
            if message:
                lines.append(f"  {message}")
            lines.append("")
        
        lines.append("-" * 60)
        overall = "✓ 所有验证通过" if self.all_passed else "✗ 存在未通过的验证项"
        lines.append(f"总体结果: {overall}")
        lines.append("=" * 60)
        
        self.summary = "\n".join(lines)
        return self.summary
    
    def generate_detailed_report(self) -> str:
        """生成详细验证报告"""
        lines = [
            "=" * 70,
            "Phase 5: 模型验证详细报告",
            "=" * 70,
            "",
            "本报告包含四项验证检查的完整计算过程和结论。",
            ""
        ]
        
        for name, result in self.checks.items():
            details = result['details']
            lines.append("=" * 70)
            lines.append(f"【{name}】")
            lines.append("=" * 70)
            
            if 'calculation_details' in details and details['calculation_details']:
                lines.append(details['calculation_details'])
            else:
                lines.append(f"  结果: {details.get('message', '无')}")
            
            lines.append("")
        
        lines.append("=" * 70)
        overall = "所有验证通过" if self.all_passed else "存在未通过的验证项"
        lines.append(f"【总体结论】{overall}")
        lines.append("=" * 70)
        
        self.detailed_report = "\n".join(lines)
        return self.detailed_report


class ModelValidator:
    """
    模型验证器
    
    提供四种验证检查:
    1. 全局平衡检查 - 牛顿第三定律
    2. 对称性检查 - 几何对称原理
    3. 变形协调性检查 - 数量级验证
    4. 蒙特卡洛基准测试 - 统计学验证
    
    Example:
        >>> validator = ModelValidator()
        >>> result = validator.validate_all(grid, model, forces, db)
        >>> print(result.detailed_report)
    """
    
    def __init__(self):
        self.result = ValidationResult()
    
    def validate_all(self,
                     grid: GridInput,
                     model,
                     forces: Dict[int, ElementForces],
                     db = None,
                     run_monte_carlo: bool = True) -> ValidationResult:
        """
        运行所有验证检查（完整版）
        
        Args:
            grid: 轴网配置
            model: 结构模型
            forces: 内力结果
            db: 截面数据库 (用于蒙特卡洛测试)
            run_monte_carlo: 是否运行蒙特卡洛测试
            
        Returns:
            ValidationResult: 验证结果
        """
        self.result = ValidationResult()
        
        print("\n")
        print("╔" + "═" * 68 + "╗")
        print("║" + "Phase 5: 模型验证系统 - 完整验证".center(66) + "║")
        print("╠" + "═" * 68 + "╣")
        print("║" + "验证项目:".ljust(66) + "║")
        print("║" + "  1. 全局平衡检查 (牛顿第三定律)".ljust(64) + "║")
        print("║" + "  2. 对称性检查 (几何对称原理)".ljust(64) + "║")
        print("║" + "  3. 变形协调性检查 (数量级验证)".ljust(64) + "║")
        print("║" + "  4. 蒙特卡洛基准测试 (统计学验证)".ljust(64) + "║")
        print("╚" + "═" * 68 + "╝")
        
        # 1. 全局平衡检查
        print("\n" + "▓" * 70)
        print("▓  [1/4] 全局平衡检查".ljust(68) + "▓")
        print("▓" * 70)
        passed, details = check_global_equilibrium(grid, forces)
        self.result.add_check("全局平衡检查", passed, details)
        
        # 2. 对称性检查
        print("\n" + "▓" * 70)
        print("▓  [2/4] 对称性检查".ljust(68) + "▓")
        print("▓" * 70)
        passed, details = check_symmetry(grid, forces, model)
        self.result.add_check("对称性检查", passed, details)
        
        # 3. 变形协调性检查
        print("\n" + "▓" * 70)
        print("▓  [3/4] 变形协调性检查".ljust(68) + "▓")
        print("▓" * 70)
        passed, details = check_deformation(grid, forces)
        self.result.add_check("变形协调性检查", passed, details)
        
        # 4. 蒙特卡洛测试
        if run_monte_carlo and db:
            print("\n" + "▓" * 70)
            print("▓  [4/4] 蒙特卡洛基准测试".ljust(68) + "▓")
            print("▓" * 70)
            from src.models.structure_model import StructureModel
            passed, details = run_monte_carlo_test(grid, StructureModel, db, n_samples=15)
            self.result.add_check("蒙特卡洛测试", passed, details)
        else:
            print("\n" + "▓" * 70)
            print("▓  [4/4] 蒙特卡洛测试: 跳过 (无数据库)".ljust(68) + "▓")
            print("▓" * 70)
        
        # 生成报告
        self.result.generate_summary()
        self.result.generate_detailed_report()
        
        # 打印最终结果
        print("\n")
        print("╔" + "═" * 68 + "╗")
        print("║" + "验证结果汇总".center(66) + "║")
        print("╠" + "═" * 68 + "╣")
        
        for name, check_result in self.result.checks.items():
            status = "✓ 通过" if check_result['passed'] else "✗ 失败"
            line = f"  {name}: {status}"
            print("║" + line.ljust(66) + "║")
        
        print("╠" + "═" * 68 + "╣")
        overall = "✓ 所有验证通过" if self.result.all_passed else "✗ 存在未通过的验证项"
        print("║" + f"  总体结论: {overall}".ljust(64) + "║")
        print("╚" + "═" * 68 + "╝")
        
        return self.result


def validate_optimization_result(grid: GridInput,
                                 model,
                                 forces: Dict[int, ElementForces],
                                 db = None) -> ValidationResult:
    """
    便捷函数：验证优化结果（完整版）
    
    Args:
        grid: 轴网配置
        model: 结构模型
        forces: 内力结果
        db: 截面数据库
        
    Returns:
        验证结果
    """
    validator = ModelValidator()
    return validator.validate_all(
        grid=grid,
        model=model,
        forces=forces,
        db=db,
        run_monte_carlo=(db is not None)  # 有数据库才运行蒙特卡洛
    )


# =============================================================================
# 测试代码
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("Phase 5: 模型验证器完整测试")
    print("=" * 70)
    
    # 创建测试数据
    from src.models.data_models import GridInput
    from src.models.structure_model import StructureModel
    from src.calculation.section_database import SectionDatabase
    
    grid = GridInput(
        x_spans=[6000, 6000, 6000],
        z_heights=[4000, 3500, 3500, 3500, 3500],
        q_dead=4.5,
        q_live=2.5,  # GB 55001-2021
    )
    
    db = SectionDatabase()
    model = StructureModel(db)
    model.build_from_grid(grid)
    
    genes = [35, 35, 45, 45, 45, 35]
    model.set_sections_by_groups(genes)
    model.build_anastruct_model()
    forces = model.analyze()
    
    # 运行完整验证
    validator = ModelValidator()
    result = validator.validate_all(
        grid=grid,
        model=model,
        forces=forces,
        db=db,
        run_monte_carlo=True
    )
    
    print("\n" + "=" * 70)
    print("详细验证报告:")
    print("=" * 70)
    print(result.detailed_report)
    
    print("\n✓ 验证完成")
