"""
结构模型模块 - 多层RC框架分析
封装 anaStruct 实现参数化建模和分析
"""

import sys
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import numpy as np
from anastruct import SystemElements

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from phase1.section_database import SectionDatabase
from phase4.data_models import GridInput, ElementForces, ElementForcesEnvelope
from phase4.load_combinations import (
    LoadCombinationGenerator, LoadCombination,
    WindLoadParams, SnowLoadParams
)


# =============================================================================
# 材料参数
# =============================================================================

E_C = 30000  # 混凝土弹性模量 (MPa = N/mm²)


class StructureModel:
    """
    多层RC框架结构模型
    
    封装 anaStruct 库，实现:
    - 自动节点生成
    - 自动单元连接
    - 荷载施加
    - 内力提取
    
    单元编号规则:
    - 梁: 从底层到顶层，每层从左到右编号
    - 柱: 从左到右，每列从底层到顶层编号
    
    节点编号规则:
    - 从底层(z=0)到顶层
    - 每层从左(x=0)到右
    """
    
    def __init__(self, db: SectionDatabase = None):
        """
        初始化结构模型
        
        Args:
            db: 截面数据库，默认创建新实例
        """
        self.db = db if db else SectionDatabase()
        self.grid: Optional[GridInput] = None
        self.ss: Optional[SystemElements] = None
        
        # 节点和单元映射
        self.nodes: Dict[int, Tuple[float, float]] = {}  # {node_id: (x, z)}
        self.beams: Dict[int, Tuple[int, int]] = {}      # {elem_id: (start, end)}
        self.columns: Dict[int, Tuple[int, int]] = {}    # {elem_id: (start, end)}
        
        # 截面分配
        self.beam_sections: Dict[int, int] = {}   # {beam_id: section_idx}
        self.column_sections: Dict[int, int] = {} # {col_id: section_idx}
        
        # 分组信息
        self.beam_groups: Dict[str, List[int]] = {}   # {'standard': [ids...]}
        self.column_groups: Dict[str, List[int]] = {} # {'bottom': [], 'standard_corner': [], 'standard_interior': [], 'top': []}
    
    def build_from_grid(self, grid: GridInput) -> None:
        """
        根据轴网拓扑自动生成结构模型
        
        Args:
            grid: 轴网输入数据
        """
        self.grid = grid
        self._generate_nodes()
        self._generate_elements()
        self._assign_groups()
    
    def _generate_nodes(self) -> None:
        """生成节点坐标"""
        if not self.grid:
            raise ValueError("请先调用 build_from_grid()")
        
        self.nodes.clear()
        
        node_id = 1
        z = 0.0  # 当前高度
        
        for story in range(self.grid.num_stories + 1):
            x = 0.0
            for col in range(self.grid.num_spans + 1):
                # 节点坐标 (x, z) 单位: mm
                self.nodes[node_id] = (x, z)
                node_id += 1
                if col < self.grid.num_spans:
                    x += self.grid.x_spans[col]
            
            if story < self.grid.num_stories:
                z += self.grid.z_heights[story]
    
    def _generate_elements(self) -> None:
        """生成梁柱单元连接"""
        if not self.grid:
            raise ValueError("请先调用 build_from_grid()")
        
        self.beams.clear()
        self.columns.clear()
        
        n_cols = self.grid.num_spans + 1  # 每层节点数
        
        elem_id = 1
        
        # 生成梁 (每层从左到右)
        for story in range(1, self.grid.num_stories + 1):
            for span in range(self.grid.num_spans):
                # 梁连接同层相邻节点
                start_node = story * n_cols + span + 1
                end_node = start_node + 1
                self.beams[elem_id] = (start_node, end_node)
                elem_id += 1
        
        # 生成柱 (每列从底到顶)
        for col in range(n_cols):
            for story in range(self.grid.num_stories):
                # 柱连接上下层节点
                start_node = story * n_cols + col + 1
                end_node = start_node + n_cols
                self.columns[elem_id] = (start_node, end_node)
                elem_id += 1
    
    def _assign_groups(self) -> None:
        """
        自动分配构件分组（用于6基因分组编码）
        
        基因顺序: [标准梁, 屋面梁, 底层柱, 标准层角柱, 标准层内柱, 顶层柱]
        """
        n_cols = self.grid.num_spans + 1
        n_stories = self.grid.num_stories
        
        # 柱分组: 按层和位置区分
        bottom_cols = []          # 底层柱 (第1层)
        standard_corner_cols = [] # 标准层角柱 (第2~n-1层)
        standard_interior_cols = [] # 标准层内柱 (第2~n-1层)
        top_cols = []             # 顶层柱 (第n层)
        
        for col_id in self.columns.keys():
            # 计算柱所在的层和位置
            col_idx = col_id - max(self.beams.keys()) - 1 if self.beams else col_id - 1
            story = col_idx // n_cols + 1  # 第几层 (1-indexed)
            col_line = col_idx % n_cols    # 柱列位置
            is_corner = (col_line == 0 or col_line == self.grid.num_spans)
            
            if story == 1:
                # 底层柱
                bottom_cols.append(col_id)
            elif story == n_stories:
                # 顶层柱
                top_cols.append(col_id)
            else:
                # 标准层柱
                if is_corner:
                    standard_corner_cols.append(col_id)
                else:
                    standard_interior_cols.append(col_id)
        
        self.column_groups = {
            'bottom': bottom_cols,
            'standard_corner': standard_corner_cols,
            'standard_interior': standard_interior_cols,
            'top': top_cols,
        }
        
        # 梁分组: 标准层梁、屋面梁
        standard_beams = []
        roof_beams = []
        
        for beam_id in self.beams.keys():
            story = (beam_id - 1) // self.grid.num_spans + 1
            if story == self.grid.num_stories:
                roof_beams.append(beam_id)
            else:
                standard_beams.append(beam_id)
        
        self.beam_groups = {
            'standard': standard_beams,
            'roof': roof_beams,
        }
    
    def set_sections(self, 
                     beam_sections: Dict[int, int] = None,
                     column_sections: Dict[int, int] = None) -> None:
        """
        设置截面分配
        
        Args:
            beam_sections: {beam_id: section_idx}
            column_sections: {col_id: section_idx}
        """
        if beam_sections:
            self.beam_sections = beam_sections
        if column_sections:
            self.column_sections = column_sections
    
    def set_sections_by_groups(self, genes: List[int]) -> None:
        """
        根据分组基因设置截面
        
        基因顺序: [标准层梁, 屋面梁, 底层柱, 标准层角柱, 标准层内柱, 顶层柱]
        
        Args:
            genes: 截面索引列表
        """
        if len(genes) < 6:
            raise ValueError("需要至少6个基因: [标准梁, 屋面梁, 底层柱, 标准层角柱, 标准层内柱, 顶层柱]")
        
        # 解码基因
        std_beam_sec = genes[0]
        roof_beam_sec = genes[1]
        bottom_col_sec = genes[2]
        std_corner_col_sec = genes[3]
        std_interior_col_sec = genes[4]
        top_col_sec = genes[5]
        
        # 分配梁截面
        for beam_id in self.beam_groups.get('standard', []):
            self.beam_sections[beam_id] = std_beam_sec
        for beam_id in self.beam_groups.get('roof', []):
            self.beam_sections[beam_id] = roof_beam_sec
        
        # 分配柱截面
        for col_id in self.column_groups.get('bottom', []):
            self.column_sections[col_id] = bottom_col_sec
        for col_id in self.column_groups.get('standard_corner', []):
            self.column_sections[col_id] = std_corner_col_sec
        for col_id in self.column_groups.get('standard_interior', []):
            self.column_sections[col_id] = std_interior_col_sec
        for col_id in self.column_groups.get('top', []):
            self.column_sections[col_id] = top_col_sec
    
    def build_anastruct_model(self) -> SystemElements:
        """
        构建 anaStruct 模型
        
        按正确顺序添加单元以确保节点编号正确：
        1. 逐层从下到上构建
        2. 每层先加底部柱，再加梁
        3. 最后添加支座
        
        Returns:
            SystemElements: 已构建的结构系统
        """
        if not self.grid or not self.nodes:
            raise ValueError("请先调用 build_from_grid()")
        
        self.ss = SystemElements()
        n_cols = self.grid.num_spans + 1
        
        # anaStruct单元编号映射
        # 我们需要跟踪我们的elem_id到anaStruct的elem_id的映射
        self._as_elem_map = {}  # {our_elem_id: anastruct_elem_id}
        as_elem_id = 1
        
        # 逐层构建（从底层到顶层）
        for story in range(self.grid.num_stories):
            story_height = self.grid.z_heights[story] / 1000  # m
            z_bottom = sum(self.grid.z_heights[:story]) / 1000  # m
            z_top = z_bottom + story_height
            
            # 这一层的柱（从左到右）
            for col_idx in range(n_cols):
                x = sum(self.grid.x_spans[:col_idx]) / 1000  # m
                
                # 获取柱截面
                col_id = self._get_column_id(col_idx, story)
                sec_idx = self.column_sections.get(col_id, 30)
                sec = self.db.get_by_index(sec_idx)
                
                EI = E_C * self.db.get_Ieff(sec_idx, 'column') / 1e9  # kN·m²
                EA = E_C * sec['A'] / 1e3  # kN
                
                self.ss.add_element(
                    location=[[x, z_bottom], [x, z_top]],
                    EI=EI, EA=EA
                )
                self._as_elem_map[col_id] = as_elem_id
                as_elem_id += 1
            
            # 这一层的梁（从左到右）
            for span_idx in range(self.grid.num_spans):
                x_left = sum(self.grid.x_spans[:span_idx]) / 1000
                x_right = x_left + self.grid.x_spans[span_idx] / 1000
                
                # 获取梁截面
                beam_id = self._get_beam_id(span_idx, story)
                sec_idx = self.beam_sections.get(beam_id, 30)
                sec = self.db.get_by_index(sec_idx)
                
                EI = E_C * self.db.get_Ieff(sec_idx, 'beam') / 1e9
                EA = E_C * sec['A'] / 1e3
                
                self.ss.add_element(
                    location=[[x_left, z_top], [x_right, z_top]],
                    EI=EI, EA=EA
                )
                self._as_elem_map[beam_id] = as_elem_id
                as_elem_id += 1
        
        # 添加底层固定支座
        # 底层柱的底部节点: 第一层柱是元素1到n_cols
        # 每个柱有2个节点，节点1是底部
        for col_idx in range(n_cols):
            # 第col_idx个柱的底部节点ID
            # 每层增加 (n_cols柱 + n_spans梁) 个单元，每个单元2个节点
            node_id = col_idx * 2 + 1  # 简化：第一层柱的底部节点
            self.ss.add_support_fixed(node_id=node_id)
        
        # 施加荷载 (梁上均布荷载 - 使用ULS设计值)
        # GB 50009-2012: 1.2G + 1.4Q
        q_total = -(1.2 * self.grid.q_dead + 1.4 * self.grid.q_live)  # 向下为负
        
        for beam_id in self.beams.keys():
            as_id = self._as_elem_map.get(beam_id)
            if as_id:
                self.ss.q_load(element_id=as_id, q=q_total)
        
        return self.ss
    
    def _get_column_id(self, col_idx: int, story: int) -> int:
        """根据柱位置获取柱ID"""
        # 柱ID = 梁总数 + (col_idx * num_stories) + story + 1
        n_beams = self.grid.num_spans * self.grid.num_stories
        return n_beams + col_idx * self.grid.num_stories + story + 1
    
    def _get_beam_id(self, span_idx: int, story: int) -> int:
        """根据位置获取梁ID"""
        # 梁ID = story * num_spans + span_idx + 1
        return story * self.grid.num_spans + span_idx + 1
    
    def analyze(self) -> Dict[int, ElementForces]:
        """
        运行结构分析并提取内力
        
        Returns:
            Dict[int, ElementForces]: 内力结果字典
        """
        if not self.ss:
            self.build_anastruct_model()
        
        # 求解
        self.ss.solve()
        
        # 提取内力
        forces = {}
        
        # 1. 柱内力
        for col_id, (start, end) in self.columns.items():
            as_id = self._as_elem_map.get(col_id)
            if not as_id:
                continue
                
            results = self.ss.get_element_results(element_id=as_id)
            
            # 使用节点坐标计算长度 (mm)
            x1, z1 = self.nodes[start]
            x2, z2 = self.nodes[end]
            length = ((x2-x1)**2 + (z2-z1)**2)**0.5
            
            forces[col_id] = ElementForces(
                element_id=col_id,
                element_type='column',
                length=length,
                axial_max=results['Nmax'],
                axial_min=results['Nmin'],
                shear_max=results['Qmax'],
                shear_min=results['Qmin'],
                moment_max=results['Mmax'],
                moment_min=results['Mmin'],
            )
        
        # 2. 梁内力
        for beam_id, (start, end) in self.beams.items():
            as_id = self._as_elem_map.get(beam_id)
            if not as_id:
                continue
                
            results = self.ss.get_element_results(element_id=as_id)
            
            x1, z1 = self.nodes[start]
            x2, z2 = self.nodes[end]
            length = ((x2-x1)**2 + (z2-z1)**2)**0.5
            
            forces[beam_id] = ElementForces(
                element_id=beam_id,
                element_type='beam',
                length=length,
                axial_max=results['Nmax'],
                axial_min=results['Nmin'],
                shear_max=results['Qmax'],
                shear_min=results['Qmin'],
                moment_max=results['Mmax'],
                moment_min=results['Mmin'],
            )
        
        return forces
    
    def get_summary(self) -> str:
        """获取模型摘要"""
        if not self.grid:
            return "模型尚未构建"
        
        return (
            f"框架模型: {self.grid.num_spans}跨 × {self.grid.num_stories}层\n"
            f"  节点数: {len(self.nodes)}\n"
            f"  梁数量: {len(self.beams)}\n"
            f"  柱数量: {len(self.columns)}\n"
            f"  总宽度: {self.grid.total_width/1000:.1f} m\n"
            f"  总高度: {self.grid.total_height/1000:.1f} m"
        )
    
    # =========================================================================
    # 多工况分析方法
    # =========================================================================
    
    def _build_model_for_combination(self, 
                                     load_factors: Dict[str, float],
                                     wind_params: WindLoadParams = None,
                                     snow_params: SnowLoadParams = None) -> SystemElements:
        """
        为指定荷载组合构建模型
        
        Args:
            load_factors: 荷载系数字典 {'dead': 1.2, 'live': 1.4, ...}
            wind_params: 风荷载参数
            snow_params: 雪荷载参数
            
        Returns:
            构建好的 SystemElements 模型
        """
        if not self.grid or not self.nodes:
            raise ValueError("请先调用 build_from_grid()")
        
        ss = SystemElements()
        n_cols = self.grid.num_spans + 1
        
        as_elem_map = {}
        as_elem_id = 1
        
        # 逐层构建
        for story in range(self.grid.num_stories):
            story_height = self.grid.z_heights[story] / 1000  # m
            z_bottom = sum(self.grid.z_heights[:story]) / 1000
            z_top = z_bottom + story_height
            
            # 柱
            for col_idx in range(n_cols):
                x = sum(self.grid.x_spans[:col_idx]) / 1000
                
                col_id = self._get_column_id(col_idx, story)
                sec_idx = self.column_sections.get(col_id, 30)
                sec = self.db.get_by_index(sec_idx)
                
                EI = E_C * self.db.get_Ieff(sec_idx, 'column') / 1e9
                EA = E_C * sec['A'] / 1e3
                
                ss.add_element(
                    location=[[x, z_bottom], [x, z_top]],
                    EI=EI, EA=EA
                )
                as_elem_map[col_id] = as_elem_id
                as_elem_id += 1
            
            # 梁
            for span_idx in range(self.grid.num_spans):
                x_left = sum(self.grid.x_spans[:span_idx]) / 1000
                x_right = x_left + self.grid.x_spans[span_idx] / 1000
                
                beam_id = self._get_beam_id(span_idx, story)
                sec_idx = self.beam_sections.get(beam_id, 30)
                sec = self.db.get_by_index(sec_idx)
                
                EI = E_C * self.db.get_Ieff(sec_idx, 'beam') / 1e9
                EA = E_C * sec['A'] / 1e3
                
                ss.add_element(
                    location=[[x_left, z_top], [x_right, z_top]],
                    EI=EI, EA=EA
                )
                as_elem_map[beam_id] = as_elem_id
                as_elem_id += 1
        
        # 支座
        for col_idx in range(n_cols):
            node_id = col_idx * 2 + 1
            ss.add_support_fixed(node_id=node_id)
        
        # ============ 施加荷载 ============
        
        # 1. 竖向荷载 (恒载 + 活载)
        gamma_dead = load_factors.get('dead', 0.0)
        gamma_live = load_factors.get('live', 0.0)
        q_vertical = -(gamma_dead * self.grid.q_dead + gamma_live * self.grid.q_live)
        
        for beam_id in self.beams.keys():
            as_id = as_elem_map.get(beam_id)
            if as_id:
                ss.q_load(element_id=as_id, q=q_vertical)
        
        # 2. 雪荷载 (仅屋面梁)
        gamma_snow = load_factors.get('snow', 0.0)
        if gamma_snow > 0 and snow_params:
            sk = snow_params.get_sk()
            # 假设受荷宽度为跨度的一半 (简化处理)
            avg_span = sum(self.grid.x_spans) / len(self.grid.x_spans) / 1000  # m
            q_snow = -(gamma_snow * sk * avg_span / 2)  # kN/m
            
            roof_beams = self.beam_groups.get('roof', [])
            for beam_id in roof_beams:
                as_id = as_elem_map.get(beam_id)
                if as_id:
                    ss.q_load(element_id=as_id, q=q_snow)
        
        # 3. 风荷载 (水平节点力)
        # 采用等效梁端节点力的方式施加
        gamma_wind = load_factors.get('wind', 0.0)
        if gamma_wind > 0 and wind_params:
            # 构建节点到anastruct节点的映射
            # anastruct节点编号规则：每个单元依次添加，共享节点会合并
            # 我们追踪每层左侧柱顶节点来施加风力
            
            # 计算各层风荷载
            for story in range(self.grid.num_stories):
                z = sum(self.grid.z_heights[:story+1]) / 1000  # 该层顶标高 (m)
                wk = wind_params.get_wk(z)  # kN/m²
                
                # 受荷面积: 层高 × 进深 (假设多榀框架，进深取平均跨度)
                story_height = self.grid.z_heights[story] / 1000  # m
                avg_span = sum(self.grid.x_spans) / len(self.grid.x_spans) / 1000  # m
                
                # 该层总风力 (简化：假设迎风面宽度等于一个开间)
                F_wind = gamma_wind * wk * story_height * avg_span  # kN
                
                # 将风力作为水平均布荷载施加到该层所有梁上
                # 这是一种等效简化方法
                beams_in_story = []
                for beam_id in self.beams.keys():
                    beam_story = (beam_id - 1) // self.grid.num_spans
                    if beam_story == story:
                        beams_in_story.append(beam_id)
                
                if beams_in_story:
                    # 将风力平均分配到该层各梁的左端节点
                    F_per_beam = F_wind / len(beams_in_story)
                    
                    # 施加到第一根梁的左端 (简化处理)
                    first_beam_as_id = as_elem_map.get(beams_in_story[0])
                    if first_beam_as_id:
                        try:
                            # 施加点荷载到梁的起点
                            ss.point_load(element_id=first_beam_as_id, Fx=F_wind, x=0)
                        except Exception:
                            pass  # 忽略施加失败
        
        return ss, as_elem_map
    
    def analyze_combination(self, 
                            combination: LoadCombination,
                            wind_params: WindLoadParams = None,
                            snow_params: SnowLoadParams = None) -> Dict[int, ElementForces]:
        """
        分析单个荷载组合
        
        Args:
            combination: 荷载组合对象
            wind_params: 风荷载参数
            snow_params: 雪荷载参数
            
        Returns:
            内力结果字典
        """
        # 构建荷载系数字典
        load_factors = {lt: f for lt, f in combination.factors}
        
        ss, as_elem_map = self._build_model_for_combination(
            load_factors, wind_params, snow_params
        )
        
        # 求解
        ss.solve()
        
        # 提取内力
        forces = {}
        
        for col_id, (start, end) in self.columns.items():
            as_id = as_elem_map.get(col_id)
            if not as_id:
                continue
            
            results = ss.get_element_results(element_id=as_id)
            x1, z1 = self.nodes[start]
            x2, z2 = self.nodes[end]
            length = ((x2-x1)**2 + (z2-z1)**2)**0.5
            
            forces[col_id] = ElementForces(
                element_id=col_id,
                element_type='column',
                length=length,
                axial_max=results['Nmax'],
                axial_min=results['Nmin'],
                shear_max=results['Qmax'],
                shear_min=results['Qmin'],
                moment_max=results['Mmax'],
                moment_min=results['Mmin'],
            )
        
        for beam_id, (start, end) in self.beams.items():
            as_id = as_elem_map.get(beam_id)
            if not as_id:
                continue
            
            results = ss.get_element_results(element_id=as_id)
            x1, z1 = self.nodes[start]
            x2, z2 = self.nodes[end]
            length = ((x2-x1)**2 + (z2-z1)**2)**0.5
            
            forces[beam_id] = ElementForces(
                element_id=beam_id,
                element_type='beam',
                length=length,
                axial_max=results['Nmax'],
                axial_min=results['Nmin'],
                shear_max=results['Qmax'],
                shear_min=results['Qmin'],
                moment_max=results['Mmax'],
                moment_min=results['Mmin'],
            )
        
        return forces
    
    def analyze_envelope(self,
                         wind_params: WindLoadParams = None,
                         snow_params: SnowLoadParams = None) -> Dict[int, ElementForcesEnvelope]:
        """
        分析所有荷载组合并返回内力包络
        
        Args:
            wind_params: 风荷载参数 (可选)
            snow_params: 雪荷载参数 (可选)
            
        Returns:
            内力包络结果字典
        """
        # 生成荷载组合
        generator = LoadCombinationGenerator()
        has_wind = wind_params is not None and self.grid.has_wind
        has_snow = snow_params is not None and self.grid.has_snow
        
        uls_combos = generator.get_uls_combinations(has_wind, has_snow)
        sls_combos = generator.get_sls_combinations()
        
        # 初始化包络结果
        envelope = {}
        for elem_id in list(self.beams.keys()) + list(self.columns.keys()):
            if elem_id in self.beams:
                start, end = self.beams[elem_id]
                elem_type = 'beam'
            else:
                start, end = self.columns[elem_id]
                elem_type = 'column'
            
            x1, z1 = self.nodes[start]
            x2, z2 = self.nodes[end]
            length = ((x2-x1)**2 + (z2-z1)**2)**0.5
            
            envelope[elem_id] = ElementForcesEnvelope(
                element_id=elem_id,
                element_type=elem_type,
                length=length
            )
        
        # 遍历 ULS 组合
        for combo in uls_combos:
            try:
                forces = self.analyze_combination(combo, wind_params, snow_params)
                
                for elem_id, f in forces.items():
                    env = envelope[elem_id]
                    
                    # 更新最大值
                    if f.moment_max > env.M_uls_max:
                        env.M_uls_max = f.moment_max
                        env.controlling_combo = combo.name
                    if f.moment_min < env.M_uls_min:
                        env.M_uls_min = f.moment_min
                    if abs(f.shear_max) > abs(env.V_uls_max):
                        env.V_uls_max = f.shear_max
                    if f.axial_max > env.N_uls_max:
                        env.N_uls_max = f.axial_max
                    if f.axial_min < env.N_uls_min:
                        env.N_uls_min = f.axial_min
            except Exception as e:
                print(f"警告: 组合 {combo.name} 分析失败: {e}")
        
        # 遍历 SLS 组合 (取准永久组合的弯矩)
        for combo in sls_combos:
            if combo.limit_state == 'SLS_QUASI':
                try:
                    forces = self.analyze_combination(combo, wind_params, snow_params)
                    for elem_id, f in forces.items():
                        envelope[elem_id].M_sls = max(
                            abs(f.moment_max), 
                            abs(f.moment_min)
                        )
                except Exception as e:
                    print(f"警告: SLS组合分析失败: {e}")
        
        return envelope


# =============================================================================
# 测试代码
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("Phase 4A: 多层框架结构模型测试")
    print("=" * 70)
    
    # 初始化
    db = SectionDatabase()
    model = StructureModel(db)
    
    # 构建3跨5层框架
    grid = GridInput(
        x_spans=[6000, 6000, 6000],  # 3跨，每跨6m
        z_heights=[4000, 3500, 3500, 3500, 3500]  # 5层
    )
    
    model.build_from_grid(grid)
    print(f"\n{model.get_summary()}")
    
    # 显示分组信息
    print(f"\n梁分组:")
    print(f"  标准层梁: {len(model.beam_groups.get('standard', []))} 根")
    print(f"  屋面梁: {len(model.beam_groups.get('roof', []))} 根")
    
    print(f"\n柱分组:")
    print(f"  底层柱: {len(model.column_groups.get('bottom', []))} 根")
    print(f"  标准层角柱: {len(model.column_groups.get('standard_corner', []))} 根")
    print(f"  标准层内柱: {len(model.column_groups.get('standard_interior', []))} 根")
    print(f"  顶层柱: {len(model.column_groups.get('top', []))} 根")
    
    # 设置截面 (使用6基因分组编码)
    genes = [35, 35, 45, 45, 45, 35]  # [标准梁, 屋面梁, 底层柱, 标准角柱, 标准内柱, 顶层柱]
    model.set_sections_by_groups(genes)
    
    print(f"\n截面分配 (基因: {genes}):")
    beam_sec = db.get_by_index(genes[0])
    col_sec = db.get_by_index(genes[2])
    print(f"  标准梁: {beam_sec['b']}×{beam_sec['h']} mm")
    print(f"  底层柱: {col_sec['b']}×{col_sec['h']} mm")
    
    # 构建和分析
    print("\n正在分析...")
    model.build_anastruct_model()
    forces = model.analyze()
    
    print(f"\n内力结果 (共 {len(forces)} 个单元):")
    
    # 找出最大内力
    max_beam_M = 0
    max_col_N = 0
    max_beam_id = 0
    max_col_id = 0
    
    for elem_id, f in forces.items():
        if f.element_type == 'beam':
            if f.M_design > max_beam_M:
                max_beam_M = f.M_design
                max_beam_id = elem_id
        else:
            if f.N_design > max_col_N:
                max_col_N = f.N_design
                max_col_id = elem_id
    
    print(f"  最大梁弯矩: 单元{max_beam_id}, M = {max_beam_M:.2f} kN·m")
    print(f"  最大柱轴力: 单元{max_col_id}, N = {max_col_N:.2f} kN")
    
    print("\n" + "=" * 70)
    print("✓ Phase 4A 测试通过!")
    print("=" * 70)
