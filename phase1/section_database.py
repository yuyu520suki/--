"""
截面数据库模块 - 混凝土矩形截面库
基于 GB 50010-2010 规范，步长 50mm
"""

class SectionDatabase:
    """混凝土矩形截面数据库 (200x300 → 500x800, 步长 50mm)"""
    
    # 材料单价 (元/m³ 或 元/kg)
    CONCRETE_PRICE = 500   # 元/m³ (C30)
    STEEL_PRICE = 5.5      # 元/kg (HRB400)
    FORMWORK_PRICE = 50    # 元/m²
    
    def __init__(self):
        self.sections = self._generate_all()
        
    def _generate_all(self) -> dict:
        """生成所有截面组合"""
        idx = 0
        sections = {}
        
        for b in range(200, 550, 50):    # 宽度: 200-500 mm
            for h in range(300, 850, 50): # 高度: 300-800 mm
                I_g = b * h**3 / 12  # 毛截面惯性矩 mm^4
                A = b * h            # 截面面积 mm^2
                
                sections[idx] = {
                    'b': b,
                    'h': h,
                    'A': A,
                    'I_g': I_g,
                    'W': b * h**2 / 6,  # 截面模量 mm^3
                    'cost_per_m': self._calc_cost(b, h),
                }
                idx += 1
                
        return sections
    
    def _calc_cost(self, b: float, h: float) -> float:
        """
        计算每米构件成本 (元/m)
        包含：混凝土 + 估算配筋 + 模板
        """
        # 混凝土体积 (m³/m)
        V_concrete = (b / 1000) * (h / 1000) * 1.0
        
        # 估算配筋量 (kg/m)，按配筋率 1.5% 估算
        rho_s = 0.015
        A_s = rho_s * b * h  # mm²
        # 钢筋密度 7850 kg/m³ → 7.85e-6 kg/mm³
        W_steel = A_s * 1000 * 7.85e-6  # kg/m
        
        # 模板面积 (m²/m) - 梁三面模板
        A_form = (b + 2 * h) / 1000 * 1.0
        
        cost = (V_concrete * self.CONCRETE_PRICE + 
                W_steel * self.STEEL_PRICE + 
                A_form * self.FORMWORK_PRICE)
        return round(cost, 2)
    
    def get_by_index(self, idx: int) -> dict:
        """根据索引获取截面（自动取模处理越界）"""
        return self.sections[idx % len(self.sections)]
    
    def get_Ieff(self, idx: int, member_type: str = 'beam') -> float:
        """
        获取有效惯性矩 (考虑开裂刚度折减)
        ACI 318: 梁取 0.35*Ig, 柱取 0.70*Ig
        """
        sec = self.get_by_index(idx)
        factor = 0.35 if member_type == 'beam' else 0.70
        return sec['I_g'] * factor
    
    def __len__(self):
        return len(self.sections)
    
    def __repr__(self):
        return f"SectionDatabase({len(self)} sections, 200x300 to 500x800 mm)"


# 测试代码
if __name__ == "__main__":
    db = SectionDatabase()
    print(f"截面数据库: {db}")
    print(f"总截面数: {len(db)}")
    
    # 显示部分截面
    print("\n前5个截面:")
    for i in range(5):
        sec = db.get_by_index(i)
        print(f"  索引 {i}: {sec['b']}x{sec['h']} mm, 成本={sec['cost_per_m']:.2f} 元/m")
    
    print("\n最后3个截面:")
    for i in range(len(db)-3, len(db)):
        sec = db.get_by_index(i)
        print(f"  索引 {i}: {sec['b']}x{sec['h']} mm, 成本={sec['cost_per_m']:.2f} 元/m")
    
    # 测试刚度折减
    print("\n刚度折减测试 (索引 30):")
    sec30 = db.get_by_index(30)
    print(f"  截面: {sec30['b']}x{sec30['h']} mm")
    print(f"  毛截面 Ig = {sec30['I_g']:.2e} mm^4")
    print(f"  梁 Ieff (0.35) = {db.get_Ieff(30, 'beam'):.2e} mm^4")
    print(f"  柱 Ieff (0.70) = {db.get_Ieff(30, 'column'):.2e} mm^4")
