"""
参数化框架模块 - anaStruct 封装
实现单层单跨门式刚架的参数化建模
"""

import sys
from pathlib import Path
from anastruct import SystemElements

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from phase1.section_database import SectionDatabase


# =============================================================================
# 材料和结构参数
# =============================================================================

E_C = 30000  # 混凝土弹性模量 (MPa = N/mm²)

# 框架几何参数 (单层单跨)
SPAN = 6000     # 跨度 (mm)
HEIGHT = 3500   # 层高 (mm)

# 荷载参数
Q_DEAD = 25.0   # 恒载线荷载 (kN/m)
Q_LIVE = 10.0   # 活载线荷载 (kN/m)


class ParametricFrame:
    """
    参数化门式刚架
    
    单层单跨示例:
    
         q (均布荷载)
    ┌─────────────────────┐  ← 梁
    │           |         │
    │           v         │
    │                     │
    │                     │
    │                     │  ← 柱
    │                     │
    ▲                     ▲  ← 固支
    (0,0)             (L,0)
    """
    
    def __init__(self, db: SectionDatabase = None, 
                 span: float = SPAN, 
                 height: float = HEIGHT):
        self.db = db if db else SectionDatabase()
        self.span = span
        self.height = height
        
    def build_frame(self, genes: list) -> SystemElements:
        """
        根据基因向量构建框架模型
        
        Args:
            genes: [beam_idx, col_idx] - 梁和柱的截面索引
            
        Returns:
            SystemElements: 已求解的 anaStruct 模型
        """
        beam_idx = genes[0]
        col_idx = genes[1] if len(genes) > 1 else genes[0]
        
        # 获取截面属性
        beam_sec = self.db.get_by_index(beam_idx)
        col_sec = self.db.get_by_index(col_idx)
        
        # 计算有效刚度 (考虑开裂折减)
        # EI 单位: N·mm² = MPa·mm⁴
        beam_EI = E_C * self.db.get_Ieff(beam_idx, 'beam')
        col_EI = E_C * self.db.get_Ieff(col_idx, 'column')
        
        # 截面面积 EA
        beam_EA = E_C * beam_sec['A']
        col_EA = E_C * col_sec['A']
        
        # 转换单位: mm → m 用于建模 (anaStruct 使用 m)
        L = self.span / 1000  # m
        H = self.height / 1000  # m
        
        # 转换 EI: N·mm² → kN·m² (除以 1e12)
        beam_EI_kNm2 = beam_EI / 1e12
        col_EI_kNm2 = col_EI / 1e12
        
        # 转换 EA: N → kN (除以 1e3)
        beam_EA_kN = beam_EA / 1e3
        col_EA_kN = col_EA / 1e3
        
        # 创建结构系统
        ss = SystemElements()
        
        # 节点坐标 (m)
        # 1: (0, 0)  - 左柱底
        # 2: (0, H)  - 左柱顶 / 梁左端
        # 3: (L, H)  - 梁右端 / 右柱顶
        # 4: (L, 0)  - 右柱底
        
        # 添加单元
        # 左柱 (element 1)
        ss.add_element([[0, 0], [0, H]], EI=col_EI_kNm2, EA=col_EA_kN)
        
        # 梁 (element 2)
        ss.add_element([[0, H], [L, H]], EI=beam_EI_kNm2, EA=beam_EA_kN)
        
        # 右柱 (element 3)
        ss.add_element([[L, H], [L, 0]], EI=col_EI_kNm2, EA=col_EA_kN)
        
        # 添加固定支座
        ss.add_support_fixed(node_id=1)
        ss.add_support_fixed(node_id=4)
        
        # 施加荷载 (在梁上施加均布荷载)
        # q 单位: kN/m
        q_total = Q_DEAD + Q_LIVE
        ss.q_load(element_id=2, q=-q_total)  # 向下为负
        
        # 求解
        ss.solve()
        
        return ss
    
    def extract_forces(self, ss: SystemElements) -> dict:
        """
        从求解后的模型中提取内力
        
        Args:
            ss: 已求解的 SystemElements 对象
            
        Returns:
            dict: 内力结果
                {
                    'beams': [{'M_max': kN·m, 'V_max': kN}],
                    'columns': [{'M_max': kN·m, 'N_max': kN, 'V_max': kN}]
                }
        """
        # 元素编号: 1=左柱, 2=梁, 3=右柱
        
        # 获取弯矩
        # anaStruct 返回每个单元的弯矩, 格式为 {element_id: {node_id: M}}
        
        # 梁的内力 (element 2)
        beam_moments = ss.get_element_results(element_id=2)
        beam_M = max(abs(beam_moments['Mmin']), abs(beam_moments['Mmax']))
        beam_V = max(abs(beam_moments['Qmin']), abs(beam_moments['Qmax']))
        
        # 左柱的内力 (element 1)
        col1_results = ss.get_element_results(element_id=1)
        col1_M = max(abs(col1_results['Mmin']), abs(col1_results['Mmax']))
        col1_V = max(abs(col1_results['Qmin']), abs(col1_results['Qmax']))
        col1_N = max(abs(col1_results['Nmin']), abs(col1_results['Nmax']))
        
        # 右柱的内力 (element 3)
        col3_results = ss.get_element_results(element_id=3)
        col3_M = max(abs(col3_results['Mmin']), abs(col3_results['Mmax']))
        col3_V = max(abs(col3_results['Qmin']), abs(col3_results['Qmax']))
        col3_N = max(abs(col3_results['Nmin']), abs(col3_results['Nmax']))
        
        return {
            'beams': [{
                'element_id': 2,
                'M_max': beam_M,
                'V_max': beam_V,
            }],
            'columns': [
                {
                    'element_id': 1,
                    'M_max': col1_M,
                    'V_max': col1_V,
                    'N_max': col1_N,
                },
                {
                    'element_id': 3,
                    'M_max': col3_M,
                    'V_max': col3_V,
                    'N_max': col3_N,
                }
            ],
        }
    
    def get_max_displacement(self, ss: SystemElements) -> dict:
        """获取最大位移"""
        # 获取节点位移
        displacements = ss.get_node_displacements()
        
        max_horizontal = 0
        max_vertical = 0
        
        for node_id, disp in displacements.items():
            if 'ux' in disp:
                max_horizontal = max(max_horizontal, abs(disp['ux']))
            if 'uy' in disp:
                max_vertical = max(max_vertical, abs(disp['uy']))
        
        return {
            'max_horizontal': max_horizontal * 1000,  # 转换为 mm
            'max_vertical': max_vertical * 1000,
        }


# =============================================================================
# 测试代码
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("第二阶段: 参数化框架建模 (The Parametric Wrapper)")
    print("=" * 70)
    
    # 初始化
    db = SectionDatabase()
    frame = ParametricFrame(db, span=6000, height=3500)
    
    print(f"\n框架参数:")
    print(f"  跨度: {frame.span} mm")
    print(f"  层高: {frame.height} mm")
    print(f"  恒载: {Q_DEAD} kN/m")
    print(f"  活载: {Q_LIVE} kN/m")
    
    # 测试不同基因组合
    test_genes = [
        [30, 40],  # 梁截面索引30, 柱截面索引40
        [35, 45],  # 不同组合
        [40, 50],  # 更大截面
    ]
    
    print("\n" + "-" * 70)
    print("基因变化测试: 观察内力随截面变化")
    print("-" * 70)
    
    for genes in test_genes:
        beam_sec = db.get_by_index(genes[0])
        col_sec = db.get_by_index(genes[1])
        
        print(f"\n基因: {genes}")
        print(f"  梁: {beam_sec['b']}x{beam_sec['h']} mm")
        print(f"  柱: {col_sec['b']}x{col_sec['h']} mm")
        
        # 构建并求解
        ss = frame.build_frame(genes)
        forces = frame.extract_forces(ss)
        
        print(f"  内力结果:")
        print(f"    梁: M_max = {forces['beams'][0]['M_max']:.2f} kN·m, "
              f"V_max = {forces['beams'][0]['V_max']:.2f} kN")
        print(f"    柱1: M_max = {forces['columns'][0]['M_max']:.2f} kN·m, "
              f"N_max = {forces['columns'][0]['N_max']:.2f} kN")
    
    print("\n" + "=" * 70)
    print("✓ 第二阶段里程碑: 基因向量变化 → 自动分析 → 内力输出")
    print("=" * 70)
    
    # 可视化测试 (可选)
    try:
        print("\n尝试绘制结构图...")
        ss = frame.build_frame([35, 45])
        # ss.show_structure()  # 取消注释以显示结构
        # ss.show_bending_moment()  # 取消注释以显示弯矩图
        print("  (可取消注释 show_structure() 和 show_bending_moment() 查看图形)")
    except Exception as e:
        print(f"  绘图跳过: {e}")
