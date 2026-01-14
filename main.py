"""
RC框架优化系统 - 主程序入口
基于遗传算法的多层多跨框架截面优化

依据规范:
    - GB 50010-2010 混凝土结构设计规范
    - GB 50009-2012 建筑结构荷载规范
    - GB 55001-2021 工程结构通用规范

更新日志:
    2026-01: 活载默认值调整为 2.5 kN/m²，ULS 组合调整为 1.3G+1.5L (GB 55001-2021)
"""

import sys
from pathlib import Path
from datetime import datetime

# 确保 src 在路径中
sys.path.insert(0, str(Path(__file__).parent))

from src.models.data_models import GridInput
from src.models.structure_model import StructureModel
from src.calculation.section_database import SectionDatabase
from src.optimization.optimizer import FrameOptimizer
from src.utils.report_generator import (
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
    print("RC框架优化系统 - GB 55001-2021 合规版")
    print("=" * 70)
    
    # ==========================================================================
    # 1. 定义轴网配置
    # ==========================================================================
    grid = GridInput(
        x_spans=[6000, 6000, 6000],       # 3跨，每跨6m
        z_heights=[4000, 3500, 3500, 3500, 3500],  # 5层 (首层4m + 标准层3.5m)
        q_dead=25.0,                      # 恒载 (kN/m)
        # q_live 默认为 2.5 kN/m² (GB 55001-2021)
    )
    
    print(f"\n轴网配置:")
    print(f"  跨数: {grid.num_spans} 跨")
    print(f"  层数: {grid.num_stories} 层")
    print(f"  总宽度: {grid.total_width/1000:.1f} m")
    print(f"  总高度: {grid.total_height/1000:.1f} m")
    print(f"  恒载: {grid.q_dead} kN/m")
    print(f"  活载: {grid.q_live} kN/m² (GB 55001-2021 默认值)")
    
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
    output_dir = Path(__file__).parent / "output" / f"run_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 文件路径
    path_excel = str(output_dir / "优化结果.xlsx")
    path_pm = str(output_dir / "PM曲线图.png")
    path_frame = str(output_dir / "框架内力图.png")
    path_conv = str(output_dir / "收敛曲线.png")
    path_word = str(output_dir / "设计计算书.docx")
    
    # 1. 绘制所有图表
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
    # 5. 输出最终结果摘要
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


if __name__ == "__main__":
    result = main()
