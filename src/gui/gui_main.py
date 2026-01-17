"""
RC框架结构优化系统 - GUI界面

功能:
- 结构参数输入与校验
- 实时2D框架几何可视化  
- 优化结果展示与导出
- 承载力验证
"""

import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Dict, List, Optional
import threading

# 添加项目根目录到路径 (从 src/gui/ 往上两级)
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# 从重构后的 src 包导入
from src.models.data_models import (
    GridInput, OptimizationResult, 
    BUILDING_TYPES, REGION_PARAMS,
    get_building_params, get_region_params
)
from src.models.structure_model import StructureModel
from src.optimization.optimizer import FrameOptimizer
from src.calculation.section_database import SectionDatabase


# =============================================================================
# 参数输入面板
# =============================================================================

class ParameterPanel(ttk.LabelFrame):
    """参数输入面板"""
    
    def __init__(self, parent, on_update_callback=None):
        super().__init__(parent, text="参数配置", padding=10)
        self.on_update = on_update_callback
        
        # 参数变量 (默认值符合 GB 55001-2021)
        self.vars = {
            'num_spans': tk.IntVar(value=3),
            'num_stories': tk.IntVar(value=5),
            'span_width': tk.DoubleVar(value=6000),
            'first_story_height': tk.DoubleVar(value=4000),
            'story_height': tk.DoubleVar(value=3500),
            'q_dead': tk.DoubleVar(value=4.5),
            'q_live': tk.DoubleVar(value=2.5),   # GB 55001-2021 住宅楼面活荷载
            'w0': tk.DoubleVar(value=0.35),       # 六安基本风压
            's0': tk.DoubleVar(value=0.55),       # 六安基本雪压
            'alpha_max': tk.DoubleVar(value=0.08),  # 六安地震影响系数最大值
            'gamma_0': tk.DoubleVar(value=1.0),    # 结构重要性系数
        }
        
        # 下拉框变量
        self.building_type_var = tk.StringVar(value="办公")
        self.region_var = tk.StringVar(value="六安")
        
        self._create_widgets()
    
    def _create_widgets(self):
        """创建输入控件"""
        row = 0
        
        # ========== 建筑与地区配置 ==========
        ttk.Label(self, text="── 建筑与地区 ──", font=('SimHei', 10, 'bold')).grid(
            row=row, column=0, columnspan=3, sticky='w', pady=(0, 5))
        row += 1
        
        # 建筑类型下拉框
        ttk.Label(self, text="建筑类型:").grid(row=row, column=0, sticky='e', padx=(0, 5))
        building_types = list(BUILDING_TYPES.keys())
        self.building_combo = ttk.Combobox(self, textvariable=self.building_type_var,
                                           values=building_types, width=10, state='readonly')
        self.building_combo.grid(row=row, column=1, sticky='w')
        self.building_combo.bind('<<ComboboxSelected>>', self._on_building_type_changed)
        row += 1
        
        # 地区选择下拉框
        ttk.Label(self, text="项目地区:").grid(row=row, column=0, sticky='e', padx=(0, 5))
        regions = list(REGION_PARAMS.keys())
        self.region_combo = ttk.Combobox(self, textvariable=self.region_var,
                                         values=regions, width=10, state='readonly')
        self.region_combo.grid(row=row, column=1, sticky='w')
        self.region_combo.bind('<<ComboboxSelected>>', self._on_region_changed)
        row += 1
        
        # ========== 轴网配置 ==========
        ttk.Separator(self, orient='horizontal').grid(
            row=row, column=0, columnspan=3, sticky='ew', pady=10); row += 1
        
        ttk.Label(self, text="── 轴网配置 ──", font=('SimHei', 10, 'bold')).grid(
            row=row, column=0, columnspan=2, sticky='w', pady=(0, 5))
        row += 1
        
        self._add_entry(row, "跨数:", self.vars['num_spans'], "(1-10)"); row += 1
        self._add_entry(row, "层数:", self.vars['num_stories'], "(1-20)"); row += 1
        self._add_entry(row, "开间 (mm):", self.vars['span_width'], "≥3000"); row += 1
        self._add_entry(row, "首层高 (mm):", self.vars['first_story_height'], "≥3000"); row += 1
        self._add_entry(row, "标准层高 (mm):", self.vars['story_height'], "≥2800"); row += 1
        
        # ========== 荷载配置 ==========
        ttk.Separator(self, orient='horizontal').grid(
            row=row, column=0, columnspan=3, sticky='ew', pady=10); row += 1
        
        ttk.Label(self, text="── 荷载配置 ──", font=('SimHei', 10, 'bold')).grid(
            row=row, column=0, columnspan=2, sticky='w', pady=(0, 5)); row += 1
        
        self._add_entry(row, "恒载 (kN/m²):", self.vars['q_dead'], "自动填充"); row += 1
        self._add_entry(row, "活载 (kN/m²):", self.vars['q_live'], "自动填充"); row += 1
        self._add_entry(row, "基本风压 (kN/m²):", self.vars['w0'], "自动填充"); row += 1
        self._add_entry(row, "基本雪压 (kN/m²):", self.vars['s0'], "自动填充"); row += 1
        
        # ========== 地震配置 ==========
        ttk.Separator(self, orient='horizontal').grid(
            row=row, column=0, columnspan=3, sticky='ew', pady=10); row += 1
        
        ttk.Label(self, text="── 地震参数 ──", font=('SimHei', 10, 'bold')).grid(
            row=row, column=0, columnspan=2, sticky='w', pady=(0, 5)); row += 1
        
        self._add_entry(row, "αmax:", self.vars['alpha_max'], "0=不考虑地震"); row += 1
        self._add_entry(row, "γ₀ (重要性系数):", self.vars['gamma_0'], "1.0-1.1"); row += 1
        
        # ========== 更新按钮 ==========
        ttk.Button(self, text="更新预览", command=self._on_update).grid(
            row=row, column=0, columnspan=2, pady=15, sticky='ew')
    
    def _on_building_type_changed(self, event=None):
        """建筑类型改变时联动更新恒载、活载和重要性系数"""
        building_type = self.building_type_var.get()
        params = get_building_params(building_type)
        self.vars['q_dead'].set(params['q_dead'])
        self.vars['q_live'].set(params['q_live'])
        self.vars['gamma_0'].set(params['gamma_0'])
    
    def _on_region_changed(self, event=None):
        """地区改变时联动更新风压、雪压、地震参数"""
        region = self.region_var.get()
        params = get_region_params(region)
        self.vars['w0'].set(params['w0'])
        self.vars['s0'].set(params['s0'])
        self.vars['alpha_max'].set(params['alpha_max'])
    
    def _add_entry(self, row: int, label: str, var: tk.Variable, hint: str):
        """添加标签+输入框+提示"""
        ttk.Label(self, text=label).grid(row=row, column=0, sticky='e', padx=(0, 5))
        entry = ttk.Entry(self, textvariable=var, width=10)
        entry.grid(row=row, column=1, sticky='w')
        ttk.Label(self, text=hint, foreground='gray').grid(row=row, column=2, sticky='w', padx=5)
    
    def _on_update(self):
        """更新按钮回调"""
        if self.validate() and self.on_update:
            self.on_update()
    
    def validate(self) -> bool:
        """参数校验"""
        try:
            v = self.vars
            errors = []
            
            if not (1 <= v['num_spans'].get() <= 10):
                errors.append("跨数应在1-10之间")
            if not (1 <= v['num_stories'].get() <= 20):
                errors.append("层数应在1-20之间")
            if v['span_width'].get() < 3000:
                errors.append("开间应≥3000mm")
            if v['first_story_height'].get() < 3000:
                errors.append("首层高应≥3000mm")
            if v['story_height'].get() < 2800:
                errors.append("标准层高应≥2800mm")
            if v['q_dead'].get() <= 0:
                errors.append("恒载应>0")
            if v['q_live'].get() <= 0:
                errors.append("活载应>0")
            
            if errors:
                messagebox.showerror("参数错误", "\n".join(errors))
                return False
            return True
            
        except tk.TclError as e:
            messagebox.showerror("输入错误", "请输入有效数值")
            return False
    
    def get_grid_input(self) -> GridInput:
        """获取 GridInput 对象"""
        v = self.vars
        n_spans = v['num_spans'].get()
        n_stories = v['num_stories'].get()
        
        x_spans = [v['span_width'].get()] * n_spans
        z_heights = [v['first_story_height'].get()] + [v['story_height'].get()] * (n_stories - 1)
        
        return GridInput(
            x_spans=x_spans,
            z_heights=z_heights,
            q_dead=v['q_dead'].get(),
            q_live=v['q_live'].get(),
            w0=v['w0'].get(),
            s0=v['s0'].get(),
            alpha_max=v['alpha_max'].get(),
            gamma_0=v['gamma_0'].get(),
            building_type=self.building_type_var.get(),
            region=self.region_var.get(),
        )


# =============================================================================
# 2D框架可视化画布
# =============================================================================

class FrameCanvas(tk.Canvas):
    """2D框架可视化画布"""
    
    def __init__(self, parent, width=500, height=400):
        super().__init__(parent, width=width, height=height, bg='white', 
                         highlightthickness=1, highlightbackground='gray')
        self.width = width
        self.height = height
        self.grid_input: Optional[GridInput] = None
        
        # 绘图参数
        self.margin = 50
        self.node_radius = 4
        
        # 绑定事件
        self.bind('<Configure>', self._on_resize)
    
    def _on_resize(self, event):
        """窗口大小改变时重绘"""
        self.width = event.width
        self.height = event.height
        if self.grid_input:
            self.draw_frame(self.grid_input)
    
    def draw_frame(self, grid: GridInput, result: OptimizationResult = None):
        """绘制框架"""
        self.grid_input = grid
        self.delete('all')
        
        if not grid.x_spans or not grid.z_heights:
            return
        
        # 计算缩放比例
        total_width = sum(grid.x_spans)
        total_height = sum(grid.z_heights)
        
        draw_width = self.width - 2 * self.margin
        draw_height = self.height - 2 * self.margin
        
        scale = min(draw_width / total_width, draw_height / total_height) * 0.9
        
        # 偏移量（居中）
        offset_x = self.margin + (draw_width - total_width * scale) / 2
        offset_y = self.height - self.margin - (draw_height - total_height * scale) / 2
        
        def to_screen(x_mm, z_mm):
            """坐标转换: 结构坐标 → 屏幕坐标"""
            sx = offset_x + x_mm * scale
            sy = offset_y - z_mm * scale  # Y轴翻转
            return sx, sy
        
        # 绘制网格线（辅助）
        self._draw_grid(grid, to_screen, scale)
        
        # 绘制构件
        self._draw_columns(grid, to_screen)
        self._draw_beams(grid, to_screen)
        self._draw_nodes(grid, to_screen)
        self._draw_supports(grid, to_screen)
        
        # 绘制标注
        self._draw_dimensions(grid, to_screen, scale)
        
        # 绘制荷载
        self._draw_loads(grid, to_screen, scale)
        
        # 图例
        self._draw_legend()
    
    def _draw_grid(self, grid: GridInput, to_screen, scale):
        """绘制辅助网格"""
        # 浅色虚线网格
        for i in range(grid.num_spans + 1):
            x = sum(grid.x_spans[:i])
            sx, sy_bottom = to_screen(x, 0)
            _, sy_top = to_screen(x, sum(grid.z_heights))
            self.create_line(sx, sy_bottom, sx, sy_top, 
                           fill='#e0e0e0', dash=(2, 2))
        
        for j in range(grid.num_stories + 1):
            z = sum(grid.z_heights[:j])
            sx_left, sy = to_screen(0, z)
            sx_right, _ = to_screen(sum(grid.x_spans), z)
            self.create_line(sx_left, sy, sx_right, sy,
                           fill='#e0e0e0', dash=(2, 2))
    
    def _draw_columns(self, grid: GridInput, to_screen):
        """绘制柱"""
        for i in range(grid.num_spans + 1):
            x = sum(grid.x_spans[:i])
            for j in range(grid.num_stories):
                z_bottom = sum(grid.z_heights[:j])
                z_top = z_bottom + grid.z_heights[j]
                
                sx1, sy1 = to_screen(x, z_bottom)
                sx2, sy2 = to_screen(x, z_top)
                
                self.create_line(sx1, sy1, sx2, sy2, 
                               fill='#2196F3', width=3, tags='column')
    
    def _draw_beams(self, grid: GridInput, to_screen):
        """绘制梁"""
        for j in range(grid.num_stories):
            z = sum(grid.z_heights[:j+1])
            for i in range(grid.num_spans):
                x_left = sum(grid.x_spans[:i])
                x_right = x_left + grid.x_spans[i]
                
                sx1, sy1 = to_screen(x_left, z)
                sx2, sy2 = to_screen(x_right, z)
                
                self.create_line(sx1, sy1, sx2, sy2,
                               fill='#4CAF50', width=2, tags='beam')
    
    def _draw_nodes(self, grid: GridInput, to_screen):
        """绘制节点"""
        node_id = 1
        for j in range(grid.num_stories + 1):
            z = sum(grid.z_heights[:j])
            for i in range(grid.num_spans + 1):
                x = sum(grid.x_spans[:i])
                sx, sy = to_screen(x, z)
                
                r = self.node_radius
                self.create_oval(sx-r, sy-r, sx+r, sy+r,
                               fill='#333', outline='#333', tags='node')
                
                # 节点编号（仅显示部分）
                if j == 0 or j == grid.num_stories or i == 0 or i == grid.num_spans:
                    self.create_text(sx+8, sy-8, text=str(node_id),
                                   font=('Arial', 7), fill='gray')
                node_id += 1
    
    def _draw_supports(self, grid: GridInput, to_screen):
        """绘制固定支座"""
        for i in range(grid.num_spans + 1):
            x = sum(grid.x_spans[:i])
            sx, sy = to_screen(x, 0)
            
            # 三角形
            size = 12
            self.create_polygon(
                sx, sy,
                sx - size, sy + size,
                sx + size, sy + size,
                fill='', outline='#333', width=2
            )
            # 底线
            self.create_line(sx - size - 3, sy + size + 2,
                           sx + size + 3, sy + size + 2,
                           fill='#333', width=2)
    
    def _draw_dimensions(self, grid: GridInput, to_screen, scale):
        """绘制尺寸标注"""
        # 跨度标注
        for i in range(grid.num_spans):
            x_left = sum(grid.x_spans[:i])
            x_mid = x_left + grid.x_spans[i] / 2
            sx, sy = to_screen(x_mid, -500)  # 底部偏移
            text = f"{grid.x_spans[i]/1000:.1f}m"
            self.create_text(sx, sy + 30, text=text, font=('Arial', 8))
        
        # 层高标注
        for j in range(min(3, grid.num_stories)):  # 只标注前3层
            z_bottom = sum(grid.z_heights[:j])
            z_mid = z_bottom + grid.z_heights[j] / 2
            sx, sy = to_screen(-500, z_mid)  # 左侧偏移
            text = f"{grid.z_heights[j]/1000:.1f}m"
            self.create_text(sx - 25, sy, text=text, font=('Arial', 8))
    
    def _draw_loads(self, grid: GridInput, to_screen, scale):
        """绘制荷载示意"""
        # 只在顶层梁上画荷载箭头
        z_top = sum(grid.z_heights)
        arrow_len = 15
        
        for i in range(grid.num_spans):
            x_left = sum(grid.x_spans[:i])
            x_right = x_left + grid.x_spans[i]
            
            # 每跨画3个箭头
            for k in range(3):
                x = x_left + grid.x_spans[i] * (k + 1) / 4
                sx, sy = to_screen(x, z_top)
                
                self.create_line(sx, sy - arrow_len, sx, sy - 3,
                               fill='#FF5722', width=1, arrow='last', arrowshape=(4, 5, 2))
        
        # 荷载数值标注
        q = grid.q_dead + grid.q_live
        sx, _ = to_screen(sum(grid.x_spans) / 2, z_top)
        self.create_text(sx, 20, text=f"q = {q:.0f} kN/m",
                       font=('Arial', 9), fill='#FF5722')
    
    def _draw_legend(self):
        """绘制图例"""
        x, y = 10, self.height - 60
        
        self.create_text(x, y, text="图例:", anchor='w', font=('SimHei', 8, 'bold'))
        
        # 柱
        self.create_line(x, y+15, x+20, y+15, fill='#2196F3', width=3)
        self.create_text(x+25, y+15, text="柱", anchor='w', font=('SimHei', 8))
        
        # 梁
        self.create_line(x+50, y+15, x+70, y+15, fill='#4CAF50', width=2)
        self.create_text(x+75, y+15, text="梁", anchor='w', font=('SimHei', 8))
        
        # 荷载
        self.create_line(x+100, y+5, x+100, y+15, fill='#FF5722', arrow='last')
        self.create_text(x+105, y+15, text="荷载", anchor='w', font=('SimHei', 8))


# =============================================================================
# 结果展示面板
# =============================================================================

class ResultPanel(ttk.LabelFrame):
    """结果展示面板"""
    
    def __init__(self, parent):
        super().__init__(parent, text="优化结果", padding=10)
        
        self.result: Optional[OptimizationResult] = None
        self.output_dir: Optional[Path] = None  # 输出目录
        self._create_widgets()
    
    def _create_widgets(self):
        """创建控件"""
        # 造价
        self.cost_var = tk.StringVar(value="--")
        ttk.Label(self, text="最优造价:", font=('SimHei', 10, 'bold')).pack(anchor='w')
        ttk.Label(self, textvariable=self.cost_var, 
                 font=('Arial', 14, 'bold'), foreground='#D32F2F').pack(anchor='w')
        
        ttk.Separator(self, orient='horizontal').pack(fill='x', pady=10)
        
        # 截面配置
        ttk.Label(self, text="截面配置:", font=('SimHei', 10, 'bold')).pack(anchor='w')
        
        self.section_frame = ttk.Frame(self)
        self.section_frame.pack(fill='x', pady=5)
        
        self.section_labels = {}
        # 更新为6个基因分组
        names = ['标准梁', '屋面梁', '底层柱', '标准角柱', '标准内柱', '顶层柱']
        for i, name in enumerate(names):
            frame = ttk.Frame(self.section_frame)
            frame.pack(fill='x')
            ttk.Label(frame, text=f"  {name}:", width=10).pack(side='left')
            lbl = ttk.Label(frame, text="--", foreground='#1565C0')
            lbl.pack(side='left')
            self.section_labels[name] = lbl
        
        ttk.Separator(self, orient='horizontal').pack(fill='x', pady=10)
        
        # 收敛信息
        ttk.Label(self, text="收敛信息:", font=('SimHei', 10, 'bold')).pack(anchor='w')
        self.gen_var = tk.StringVar(value="--")
        ttk.Label(self, textvariable=self.gen_var).pack(anchor='w')
        
        ttk.Separator(self, orient='horizontal').pack(fill='x', pady=10)
        
        # 操作按钮 - 第一行
        ttk.Label(self, text="查看图表:", font=('SimHei', 10, 'bold')).pack(anchor='w', pady=(0, 5))
        
        self.btn_frame1 = ttk.Frame(self)
        self.btn_frame1.pack(fill='x')
        
        ttk.Button(self.btn_frame1, text="内力图", 
                  command=self._show_frame_diagram).pack(side='left', padx=2)
        ttk.Button(self.btn_frame1, text="P-M曲线",
                  command=self._show_pm_curve).pack(side='left', padx=2)
        ttk.Button(self.btn_frame1, text="收敛曲线",
                  command=self._show_convergence).pack(side='left', padx=2)
        ttk.Button(self.btn_frame1, text="水平荷载",
                  command=self._show_seismic_diagram).pack(side='left', padx=2)
        
        # 操作按钮 - 第二行
        self.btn_frame2 = ttk.Frame(self)
        self.btn_frame2.pack(fill='x', pady=(5, 0))
        
        ttk.Button(self.btn_frame2, text="📋 模型验证",
                  command=self._run_validation).pack(side='left', padx=2)
        ttk.Button(self.btn_frame2, text="📄 打开计算书",
                  command=self._open_report).pack(side='left', padx=2)
        ttk.Button(self.btn_frame2, text="📁 打开输出目录",
                  command=self._open_output_dir).pack(side='left', padx=2)
        
        # 保存验证所需的数据
        self.grid_input = None
        self.model = None
    
    def update_result(self, result: OptimizationResult, db: SectionDatabase, output_dir: Path = None):
        """更新结果显示"""
        self.result = result
        self.output_dir = output_dir
        
        # 造价
        self.cost_var.set(f"¥{result.cost:,.0f}")
        
        # 截面
        names = ['标准梁', '屋面梁', '底层柱', '标准角柱', '标准内柱', '顶层柱']
        for i, name in enumerate(names):
            if i < len(result.genes):
                sec = db.get_by_index(result.genes[i])
                self.section_labels[name].config(text=f"{sec['b']}×{sec['h']} mm")
        
        # 收敛
        gen = len(result.convergence_history)  # 使用造价历史长度
        self.gen_var.set(f"迭代 {gen} 代")
    
    def _open_file(self, filename: str):
        """打开指定文件"""
        import os
        import subprocess
        
        if not self.output_dir:
            messagebox.showwarning("警告", "请先运行优化")
            return
        
        filepath = self.output_dir / filename
        if not filepath.exists():
            messagebox.showerror("错误", f"文件不存在:\n{filepath}")
            return
        
        # 使用系统默认程序打开
        try:
            os.startfile(str(filepath))
        except Exception as e:
            messagebox.showerror("打开失败", str(e))
    
    def _show_frame_diagram(self):
        """显示内力图"""
        self._open_file("框架内力图.png")
    
    def _show_pm_curve(self):
        """显示P-M曲线"""
        self._open_file("PM曲线图.png")
    
    def _show_convergence(self):
        """显示收敛曲线"""
        self._open_file("收敛曲线.png")
    
    def _show_seismic_diagram(self):
        """显示水平荷载效应图"""
        self._open_file("水平荷载效应图.png")
    
    def _open_report(self):
        """打开计算书"""
        self._open_file("设计计算书.docx")
    
    def _open_output_dir(self):
        """打开输出目录"""
        import os
        import subprocess
        
        if not self.output_dir:
            messagebox.showwarning("警告", "请先运行优化")
            return
        
        if not self.output_dir.exists():
            messagebox.showerror("错误", f"目录不存在:\n{self.output_dir}")
            return
        
        try:
            os.startfile(str(self.output_dir))
        except Exception as e:
            messagebox.showerror("打开失败", str(e))
    
    def _run_validation(self):
        """运行模型验证（完整版）"""
        if not self.result:
            messagebox.showwarning("警告", "请先运行优化")
            return
        
        if not self.grid_input or not self.model:
            messagebox.showwarning("警告", "验证数据不完整，请重新运行优化")
            return
        
        # 获取数据库引用
        db = None
        parent = self.master
        while parent:
            if hasattr(parent, 'db'):
                db = parent.db
                break
            parent = getattr(parent, 'master', None)
        
        try:
            from src.analysis.model_validator import validate_optimization_result
            
            # 运行完整验证（包括蒙特卡洛测试）
            validation_result = validate_optimization_result(
                grid=self.grid_input,
                model=self.model,
                forces=self.result.forces,
                db=db  # 传递db以启用蒙特卡洛测试
            )
            
            # 显示详细报告对话框
            if validation_result.all_passed:
                messagebox.showinfo("验证通过", validation_result.summary)
            else:
                messagebox.showwarning("验证警告", validation_result.summary)
                
        except Exception as e:
            import traceback
            traceback.print_exc()
            messagebox.showerror("验证失败", str(e))


# =============================================================================
# 主界面
# =============================================================================

class FrameOptimizerGUI(tk.Tk):
    """RC框架优化系统主界面"""
    
    def __init__(self):
        super().__init__()
        
        self.title("RC框架结构优化系统 v2.0 | GB 55001-2021")
        self.geometry("1100x650")
        self.minsize(900, 550)
        
        # 数据
        self.db = SectionDatabase()
        self.result: Optional[OptimizationResult] = None
        
        self._create_menu()
        self._create_toolbar()
        self._create_main_layout()
        
        # 初始化预览
        self._update_preview()
    
    def _create_menu(self):
        """创建菜单栏"""
        menubar = tk.Menu(self)
        
        # 文件菜单
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="保存参数...", command=self._save_params)
        file_menu.add_command(label="加载参数...", command=self._load_params)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.quit)
        menubar.add_cascade(label="文件", menu=file_menu)
        
        # 运行菜单
        run_menu = tk.Menu(menubar, tearoff=0)
        run_menu.add_command(label="运行优化", command=self._run_optimization)
        run_menu.add_command(label="生成报告", command=self._generate_report)
        menubar.add_cascade(label="运行", menu=run_menu)
        
        # 帮助菜单
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="关于", command=self._show_about)
        menubar.add_cascade(label="帮助", menu=help_menu)
        
        self.config(menu=menubar)
    
    def _create_toolbar(self):
        """创建工具栏"""
        toolbar = ttk.Frame(self)
        toolbar.pack(side='top', fill='x', padx=5, pady=5)
        
        ttk.Button(toolbar, text="▶ 运行优化", 
                  command=self._run_optimization).pack(side='left', padx=2)
        ttk.Button(toolbar, text="📄 生成报告",
                  command=self._generate_report).pack(side='left', padx=2)
        
        ttk.Separator(toolbar, orient='vertical').pack(side='left', fill='y', padx=10)
        
        # 并行加速开关
        self.parallel_var = tk.BooleanVar(value=True)  # 默认开启
        self.parallel_check = ttk.Checkbutton(
            toolbar, 
            text="⚡ 并行加速", 
            variable=self.parallel_var,
            command=self._on_parallel_toggle
        )
        self.parallel_check.pack(side='left', padx=5)
        
        # 线程数选择
        ttk.Label(toolbar, text="线程:").pack(side='left', padx=(5, 2))
        self.workers_var = tk.IntVar(value=6)
        self.workers_spin = ttk.Spinbox(
            toolbar, 
            from_=2, to=12, 
            textvariable=self.workers_var,
            width=3,
            state='readonly'
        )
        self.workers_spin.pack(side='left')
        
        ttk.Separator(toolbar, orient='vertical').pack(side='left', fill='y', padx=10)
        
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(toolbar, textvariable=self.status_var).pack(side='left')
        
        # 进度条
        self.progress = ttk.Progressbar(toolbar, mode='indeterminate', length=100)
        self.progress.pack(side='right', padx=5)
    
    def _on_parallel_toggle(self):
        """并行开关切换回调"""
        if self.parallel_var.get():
            self.workers_spin.config(state='readonly')
            self.status_var.set(f"已启用并行加速 ({self.workers_var.get()} 线程)")
        else:
            self.workers_spin.config(state='disabled')
            self.status_var.set("已禁用并行加速 (串行模式)")
    
    
    def _create_main_layout(self):
        """创建主布局"""
        main_frame = ttk.Frame(self)
        main_frame.pack(fill='both', expand=True, padx=5, pady=5)
        
        # 左侧: 参数面板
        self.param_panel = ParameterPanel(main_frame, on_update_callback=self._update_preview)
        self.param_panel.pack(side='left', fill='y', padx=(0, 5))
        
        # 中间: 预览画布
        canvas_frame = ttk.LabelFrame(main_frame, text="2D 框架预览", padding=5)
        canvas_frame.pack(side='left', fill='both', expand=True, padx=5)
        
        self.canvas = FrameCanvas(canvas_frame, width=500, height=400)
        self.canvas.pack(fill='both', expand=True)
        
        # 右侧: 结果面板
        self.result_panel = ResultPanel(main_frame)
        self.result_panel.pack(side='right', fill='y', padx=(5, 0))
    
    def _update_preview(self):
        """更新预览"""
        if self.param_panel.validate():
            grid = self.param_panel.get_grid_input()
            self.canvas.draw_frame(grid)
            self.status_var.set(f"预览: {grid.num_spans}跨 × {grid.num_stories}层")
    
    def _run_optimization(self):
        """运行优化（后台线程）"""
        if not self.param_panel.validate():
            return
        
        self.status_var.set("优化进行中...")
        self.progress.start()
        
        def run():
            try:
                from datetime import datetime
                from src.models.structure_model import StructureModel
                from src.utils.report_generator import (
                    generate_excel_report, generate_word_report,
                    plot_pm_diagrams, plot_frame_diagrams, plot_convergence,
                    plot_seismic_load_diagram
                )
                
                grid = self.param_panel.get_grid_input()
                
                # 读取并行设置
                use_parallel = self.parallel_var.get()
                n_workers = self.workers_var.get()
                
                optimizer = FrameOptimizer(grid, self.db)
                result = optimizer.run(
                    num_generations=100, 
                    sol_per_pop=50, 
                    random_seed=42,
                    parallel=use_parallel,
                    n_workers=n_workers
                )
                
                self.result = result
                
                # 创建输出目录
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_dir = Path(__file__).parent.parent.parent / "output" / f"run_{timestamp}"
                output_dir.mkdir(parents=True, exist_ok=True)
                self.output_dir = output_dir
                
                # 生成图表和报告
                self.after(0, lambda: self.status_var.set("生成报告中..."))
                
                model = StructureModel(self.db)
                model.build_from_grid(grid)
                model.set_sections_by_groups(result.genes)
                model.build_anastruct_model()
                model.analyze()
                
                # 生成图表
                plot_pm_diagrams(result, model, self.db, str(output_dir / "PM曲线图.png"))
                plot_frame_diagrams(result, model, grid, str(output_dir / "框架内力图.png"))
                plot_convergence(result.convergence_history, str(output_dir / "收敛曲线.png"))
                
                # 生成地震/水平荷载效应图 (如果有水平荷载)
                if (hasattr(grid, 'alpha_max') and grid.alpha_max > 0) or \
                   (hasattr(grid, 'w0') and grid.w0 > 0):
                    plot_seismic_load_diagram(grid, model, str(output_dir / "水平荷载效应图.png"))
                
                # 生成报告
                image_paths = {
                    'pm': str(output_dir / "PM曲线图.png"),
                    'frame': str(output_dir / "框架内力图.png"),
                    'conv': str(output_dir / "收敛曲线.png"),
                    'seismic': str(output_dir / "水平荷载效应图.png"),
                }
                generate_excel_report(result, model, self.db, str(output_dir / "优化结果.xlsx"))
                generate_word_report(result, model, self.db, grid, 
                                   str(output_dir / "设计计算书.docx"), image_paths)
                
                # 保存验证所需的数据（供验证按钮使用）
                self.result_panel.grid_input = grid
                self.result_panel.model = model
                
                # 更新UI（主线程）
                self.after(0, lambda: self._on_optimization_complete(result, output_dir))
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.after(0, lambda: messagebox.showerror("优化错误", str(e)))
                self.after(0, lambda: self.progress.stop())
        
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
    
    def _on_optimization_complete(self, result: OptimizationResult, output_dir: Path):
        """优化完成回调"""
        self.progress.stop()
        self.status_var.set(f"优化完成! 造价: ¥{result.cost:,.0f}")
        self.result_panel.update_result(result, self.db, output_dir)
        messagebox.showinfo("完成", f"优化完成!\n最优造价: ¥{result.cost:,.0f}\n\n"
                                   f"报告已保存到:\n{output_dir}")
    
    def _generate_report(self):
        """生成报告"""
        if not self.result:
            messagebox.showwarning("警告", "请先运行优化")
            return
        
        if hasattr(self, 'output_dir') and self.output_dir:
            messagebox.showinfo("提示", f"报告已生成到:\n{self.output_dir}")
        else:
            messagebox.showinfo("提示", "请重新运行优化以生成报告")
    
    def _save_params(self):
        """保存参数"""
        messagebox.showinfo("提示", "参数保存功能开发中")
    
    def _load_params(self):
        """加载参数"""
        messagebox.showinfo("提示", "参数加载功能开发中")
    
    def _show_about(self):
        """关于对话框"""
        messagebox.showinfo("关于", 
            "RC框架结构优化系统 v1.0\n\n"
            "基于遗传算法的钢筋混凝土框架\n"
            "截面优化设计系统\n\n"
            "© 2024")


# =============================================================================
# 入口
# =============================================================================

def main():
    """主入口"""
    app = FrameOptimizerGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
