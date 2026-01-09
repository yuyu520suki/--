"""
Phase 4 主程序 - RC框架优化系统入口
端到端自动化：轴网输入 → 优化后的梁柱截面及配筋
"""

import sys
from pathlib import Path
from datetime import datetime

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from phase1.section_database import SectionDatabase
from phase4.data_models import GridInput
from phase4.structure_model import StructureModel
from phase4.section_verifier import SectionVerifier
from phase4.optimizer import FrameOptimizer
from phase4.report_generator import (
    generate_excel_report,
    generate_word_report,
    plot_pm_diagrams,
    plot_frame_diagrams,
    plot_convergence,
)


def main():
    """
    主函数：运行完整的RC框架优化流程
    
    步骤:
    1. 定义轴网（3跨 × 5层示例）
    2. 初始化组件
    3. 运行遗传算法优化
    4. 生成输出报表和图表
    """
    print("=" * 70)
    print("RC框架优化系统 - Phase 4 完整流程")
    print("=" * 70)
    
    # ==========================================================================
    # 1. 定义轴网配置
    # ==========================================================================
    grid = GridInput(
        x_spans=[4000, 6000, 6000],       # 3跨，每跨6m
        z_heights=[4000, 3500, 3500, 3500, 3500],  # 5层 (首层4m + 标准层3.5m)
        q_dead=25.0,                      # 恒载 (kN/m)
        q_live=10.0,                      # 活载 (kN/m)
    )
    
    print(f"\n轴网配置:")
    print(f"  跨数: {grid.num_spans} 跨")
    print(f"  层数: {grid.num_stories} 层")
    print(f"  总宽度: {grid.total_width/1000:.1f} m")
    print(f"  总高度: {grid.total_height/1000:.1f} m")
    print(f"  荷载: q = {grid.q_dead + grid.q_live} kN/m (恒+活)")
    
    # ==========================================================================
    # 2. 初始化系统组件
    # ==========================================================================
    db = SectionDatabase()
    print(f"\n截面数据库: {len(db)} 种截面 (200×300 ~ 500×800 mm)")
    
    # ==========================================================================
    # 3. 运行优化
    # ==========================================================================
    optimizer = FrameOptimizer(grid, db)
    
    result = optimizer.run(
        num_generations=100,  # 100代
        sol_per_pop=40,       # 种群40
        random_seed=42,
    )
    
    # ==========================================================================
    # 4. 生成输出
    # ==========================================================================
    print("\n" + "-" * 70)
    print("生成输出文件...")
    print("-" * 70)
    
    # 创建带时间戳的输出目录
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(__file__).parent.parent / "output" / f"run_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 文件路径
    path_excel = str(output_dir / "优化结果.xlsx")
    path_pm = str(output_dir / "PM曲线图.png")
    path_frame = str(output_dir / "框架内力图.png")
    path_conv = str(output_dir / "收敛曲线.png")
    path_word = str(output_dir / "设计计算书.docx")
    
    # 1. 绘制所有图表 (先绘图，后续插入Word)
    plot_pm_diagrams(result, optimizer.model, db, output_path=path_pm)
    plot_frame_diagrams(result, optimizer.model, grid, output_path=path_frame)
    plot_convergence(optimizer.cost_history, output_path=path_conv)
    
    # 2. Excel报表
    generate_excel_report(result, optimizer.model, db, output_path=path_excel)
    
    # 3. Word设计计算书
    image_paths = {
        'pm': path_pm,
        'frame': path_frame,
        'conv': path_conv
    }
    generate_word_report(
        result, 
        optimizer.model, 
        db, 
        grid, 
        output_path=path_word,
        image_paths=image_paths
    )
    
    # ==========================================================================
    # 5. Phase 5: 模型验证 (可选)
    # ==========================================================================
    print("\n提示: 如需运行模型验证，请执行: python phase5/model_validator.py")
    
    # ==========================================================================
    # 6. 输出最终结果摘要
    # ==========================================================================
    print("\n" + "=" * 70)
    print("✓ 优化完成 - 最终结果")
    print("=" * 70)
    
    print(f"\n最优截面配置:")
    names = ['标准层梁', '屋面梁', '底层柱', '标准角柱', '标准内柱', '顶层柱']
    for i, name in enumerate(names):
        sec = db.get_by_index(result.genes[i])
        print(f"  {name}: {sec['b']} × {sec['h']} mm")
    
    print(f"\n总造价: ¥{result.cost:,.2f}")
    
    print(f"\n输出文件:")
    print(f"  📊 {path_excel}")
    print(f"  📝 {path_word}")
    print(f"  📈 {path_pm}")
    print(f"  📐 {path_frame}")
    print(f"  📉 {path_conv}")
    
    print("\n" + "=" * 70)
    
    return result


# =============================================================================
# 单跨测试（用于与Phase 2对比验证）
# =============================================================================

def test_single_span_equivalence():
    """
    测试单跨等效性：对比新旧模块对同一单跨输入的分析结果
    """
    print("=" * 70)
    print("单跨等效性测试")
    print("=" * 70)
    
    # 单跨单层配置（与 phase2 相同）
    grid = GridInput(
        x_spans=[6000],
        z_heights=[3500],
        q_dead=25.0,
        q_live=10.0,
    )
    
    db = SectionDatabase()
    model = StructureModel(db)
    model.build_from_grid(grid)
    
    # 设置与 phase2 相同的截面 (6基因编码)
    genes = [35, 35, 45, 45, 45, 35]  # [标准梁, 屋面梁, 底层柱, 标准角柱, 标准内柱, 顶层柱]
    model.set_sections_by_groups(genes)
    
    model.build_anastruct_model()
    forces = model.analyze()
    
    print(f"\n单跨配置: {grid.num_spans}跨 × {grid.num_stories}层")
    print(f"梁数量: {len(model.beams)}, 柱数量: {len(model.columns)}")
    
    print(f"\n内力结果:")
    for elem_id, f in forces.items():
        print(f"  单元{elem_id} ({f.element_type}): "
              f"M={f.M_design:.2f} kN·m, V={f.V_design:.2f} kN, N={f.N_design:.2f} kN")
    
    print("\n✓ 单跨测试完成")
    return forces


if __name__ == "__main__":
    # 运行完整优化
    result = main()
    
    # 可选：运行单跨测试
    # test_single_span_equivalence()
