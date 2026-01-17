"""
截面数据库模块 - 混凝土矩形截面库
基于 GB 50010-2010 规范，步长 50mm
"""


# =============================================================================
# 材料强度设计值 (GB 50010-2010)
# =============================================================================

F_C = 14.3       # C30 混凝土轴心抗压强度设计值 (MPa)
F_Y = 360        # HRB400 钢筋抗拉强度设计值 (MPa)


class SectionDatabase:
    """混凝土矩形截面数据库 (200x300 → 500x800, 步长 50mm)"""
    
    # =========================================================================
    # 综合单价参数 (2024年市场参考价格，基于国标定额)
    # =========================================================================
    # 参考依据:
    # - 《建筑工程工程量清单计价标准》GB 50500-2024
    # - 各地工程造价信息网 (2024年11月)
    # - 岳阳市建筑材料信息价 (2024年11月)
    #
    # 综合单价 = 材料费 + 人工费 + 机械费 + 管理费 + 利润
    # =========================================================================
    
    # 混凝土综合单价 (元/m³)
    # - 材料: C30商品混凝土 ~400 元/m³
    # - 泵送: ~30 元/m³
    # - 浇筑振捣人工: ~80 元/m³
    # - 养护: ~20 元/m³
    # - 管理费+利润: ~70 元/m³
    # 合计: ~600 元/m³
    CONCRETE_PRICE = 600   # 元/m³
    
    # 钢筋综合单价 (元/kg)
    # - 材料: HRB400 ~3.5 元/kg
    # - 制作绑扎人工: ~1.5 元/kg
    # - 搭接损耗(3%): ~0.1 元/kg
    # - 管理费+利润: ~0.9 元/kg
    # 合计: ~6.0 元/kg
    STEEL_PRICE = 6.0      # 元/kg
    
    # 模板综合单价 (元/m²)
    # - 材料(周转摊销): ~30 元/m²
    # - 制作安装人工: ~40 元/m²
    # - 拆除清理人工: ~15 元/m²
    # - 管理费+利润: ~15 元/m²
    # 合计: ~100 元/m²
    FORMWORK_PRICE = 100   # 元/m²
    
    # 间接费用综合系数
    # 包含: 企业管理费、规费、利润、税金等
    # 根据《建设工程费用组成》约 1.35~1.45
    INDIRECT_FACTOR = 1.4
    
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
        计算每米构件综合造价 (元/m)
        
        包含:
        - 混凝土: 材料费 + 浇筑人工 + 机械
        - 钢筋: 材料费 + 制作绑扎人工
        - 模板: 材料摊销 + 制作安装拆除人工
        - 间接费: 管理费 + 规费 + 利润 + 税金
        """
        # 混凝土体积 (m³/m)
        V_concrete = (b / 1000) * (h / 1000) * 1.0
        
        # 估算配筋量 (kg/m)
        # 梁配筋率约 1.2%~2.0%, 柱约 1.0%~3.0%
        # 取平均 1.5%
        rho_s = 0.015
        A_s = rho_s * b * h  # mm²
        # 钢筋密度 7850 kg/m³ → 7.85e-6 kg/mm³
        W_steel = A_s * 1000 * 7.85e-6  # kg/m
        
        # 模板面积 (m²/m) - 梁三面模板
        A_form = (b + 2 * h) / 1000 * 1.0
        
        # 直接费 (材料 + 人工 + 机械)
        direct_cost = (V_concrete * self.CONCRETE_PRICE + 
                      W_steel * self.STEEL_PRICE + 
                      A_form * self.FORMWORK_PRICE)
        
        # 综合造价 = 直接费 × 间接费用系数
        cost = direct_cost * self.INDIRECT_FACTOR
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
    print(f"\n材料强度: C30 fc={F_C} MPa, HRB400 fy={F_Y} MPa")
    
    # 显示部分截面
    print("\n前5个截面:")
    for i in range(5):
        sec = db.get_by_index(i)
        print(f"  索引 {i}: {sec['b']}x{sec['h']} mm, 成本={sec['cost_per_m']:.2f} 元/m")
