# -*- coding: utf-8 -*-
"""生成演示用虚拟面板数据（确定性线性变换，仅用于截图，不污染真实产物）。

变换规则（固定系数，无随机数，NaN 保持 NaN）：
  指数（上证指数、沪深300、中证1000、纳斯达克综指、标普500）: v' = v * 1.37 + 200
  联邦基金利率: v' = v * 0.8 + 1.2
  美联储总资产: v' = v * 0.9
  美债10Y:      v' = v * 0.9 + 0.3
  广义美元指数:  v' = v * 1.1
索引（日期）与列结构保持不变。
"""
from pathlib import Path
import pandas as pd

BASE = Path(__file__).parent
SRC = BASE / "data" / "panel_monthly.csv"
DST = BASE / "data" / "panel_demo.csv"

IDX_MAP = {
    "上证指数": (1.37, 200.0),
    "沪深300": (1.37, 200.0),
    "中证1000": (1.37, 200.0),
    "纳斯达克综指": (1.37, 200.0),
    "标普500": (1.37, 200.0),
}
LIQ_MAP = {
    "联邦基金利率": (0.8, 1.2),
    "美联储总资产": (0.9, 0.0),
    "美债10Y": (0.9, 0.3),
    "广义美元指数": (1.1, 0.0),
}

p = pd.read_csv(SRC, index_col=0, parse_dates=True)
out = p.copy()
for col, (a, b) in {**IDX_MAP, **LIQ_MAP}.items():
    if col not in out.columns:
        raise KeyError(f"列不存在: {col}")
    out[col] = p[col] * a + b  # NaN * a + b 仍为 NaN

out = out[p.columns]  # 保持列顺序
out.to_csv(DST, encoding="utf-8-sig")  # 保留原文件的 BOM
print("saved:", DST)
print("rows:", len(out), "cols:", list(out.columns))
print("demo 上证指数 2026-09:", out["上证指数"].iloc[-1],
      "| 真实:", p["上证指数"].iloc[-1])
