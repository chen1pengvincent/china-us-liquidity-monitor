# -*- coding: utf-8 -*-
"""政策周期回测 + 相关性分析"""
import sys, json, warnings, argparse
from pathlib import Path
warnings.filterwarnings("ignore")
import pandas as pd
import numpy as np
from scipy import stats

BASE = Path(__file__).parent
DATA = BASE / "data"

AP = argparse.ArgumentParser(description="政策周期回测 + 相关性分析")
AP.add_argument("--panel", default=str(DATA / "panel_monthly.csv"))
AP.add_argument("--stats", default=str(BASE / "stats.json"))
AP.add_argument("--charts", default=str(BASE / "charts"))
AP.add_argument("--xlsx", default=str(DATA / "流动性与指数回测数据.xlsx"))
AP.add_argument("--no-patch", action="store_true",
                help="演示/测试模式：不写入 2026-09 联邦基金利率人工补丁")
A = AP.parse_args()
CH = Path(A.charts); CH.mkdir(parents=True, exist_ok=True)

# ---------- 载入 ----------
p = pd.read_csv(A.panel, index_col=0, parse_dates=True)
p.index = pd.to_datetime(p.index).to_period("M").to_timestamp("M")
p = p.sort_index()

# 已核实的利率路径补丁：2026-09 加息后月中值 3.875（区间3.75-4.00，2026-09-17生效）
if not A.no_patch:
    p.loc["2026-09-30", "联邦基金利率"] = 3.875
p["联邦基金利率"] = p["联邦基金利率"].ffill()

IDX_US = ["纳斯达克综指", "标普500"]
IDX_CN = ["上证指数", "沪深300", "中证1000"]
LIQ = ["联邦基金利率", "美联储总资产", "美债10Y", "广义美元指数"]

# ---------- 政策周期定义 ----------
US_REGIMES = [  # (起点, 终点(含), 名称, 立场: 1宽松 0中性 -1收紧)
    ("2010-01", "2015-11", "R1 零利率+QE", 1),
    ("2015-12", "2017-09", "R2 首次加息(BS仍扩张)", 0),
    ("2017-10", "2019-07", "R3 加息收尾+缩表QT", -1),
    ("2019-08", "2020-02", "R4 预防式降息+停QT", 1),
    ("2020-03", "2021-11", "R5 零利率+无限QE", 1),
    ("2021-12", "2022-03", "R6 Taper", 0),
    ("2022-04", "2023-07", "R7 激进加息+QT", -1),
    ("2023-08", "2024-09", "R8 高利率平台+QT", -1),
    ("2024-10", "2025-11", "R9 降息周期+QT收尾", 1),
    ("2025-12", "2026-08", "R10 暂停降息+缩表结束", 0),
    ("2026-09", "2026-09", "R11 重启加息", -1),
]
CN_REGIMES = [
    ("2010-01", "2011-12", "C1 退出刺激(收紧)", -1),
    ("2012-01", "2014-10", "C2 稳健(中性,2013钱荒偏紧)", 0),
    ("2014-11", "2015-12", "C3 降息降准宽松", 1),
    ("2016-01", "2017-12", "C4 金融去杠杆(收紧)", -1),
    ("2018-01", "2019-12", "C5 转向宽松", 1),
    ("2020-01", "2020-04", "C6 疫情应急宽松", 1),
    ("2020-05", "2021-12", "C7 边际收紧+地产三道红线", -1),
    ("2022-01", "2024-08", "C8 渐进宽松", 1),
    ("2024-09", "2026-09", "C9 适度宽松(强宽松)", 1),
]

def stamp(s): return pd.Period(s, freq="M").to_timestamp("M")
def stance_map(regimes):
    m = {}
    for a, b, name, s in regimes:
        for per in pd.period_range(a, b, freq="M"):
            m[per] = (name, s)
    return m
us_map, cn_map = stance_map(US_REGIMES), stance_map(CN_REGIMES)

ret = p[[c for c in IDX_US + IDX_CN + LIQ if c in p]].pct_change()
ret["美联储总资产"] = p["美联储总资产"].pct_change()
ret["联邦基金利率"] = p["联邦基金利率"].diff()

# ---------- 1) 周期回测 ----------
def cycle_table(regimes, idx_list, map_):
    rows = []
    for a, b, name, s in regimes:
        pa, pb = stamp(a), stamp(b)
        sub = p.loc[pa:pb, idx_list]
        r = sub.iloc[-1] / sub.iloc[0] - 1
        n = len(sub)
        for col in idx_list:
            if sub[col].notna().sum() < max(3, int(n * 0.75)):
                rows.append({"周期": name, "立场": s, "指数": col, "月数": n,
                             "区间收益": np.nan, "年化": np.nan, "最大回撤": np.nan, "月胜率": np.nan})
                continue
            ser = sub[col].dropna()
            total = ser.iloc[-1] / ser.iloc[0] - 1
            yrs = (ser.index[-1] - ser.index[0]).days / 365.25
            ann = (1 + total) ** (1 / yrs) - 1 if yrs > 0 else np.nan
            peak = ser.cummax()
            mdd = ((ser - peak) / peak).min()
            mret = ser.pct_change().dropna()
            rows.append({"周期": name, "立场": s, "指数": col, "月数": n,
                         "区间收益": total, "年化": ann, "最大回撤": mdd, "月胜率": (mret > 0).mean()})
    return pd.DataFrame(rows)

us_cycle = cycle_table(US_REGIMES, IDX_US + IDX_CN, us_map)
cn_cycle = cycle_table(CN_REGIMES, IDX_CN, cn_map)

# ---------- 2) 中美立场 3×3 网格 ----------
df = pd.DataFrame(index=p.index)
for col in IDX_US + IDX_CN:
    df[col + "_r"] = p[col].pct_change()
df["us_stance"] = [us_map.get(per, (None, np.nan))[1] for per in p.index.to_period("M")]
df["cn_stance"] = [cn_map.get(per, (None, np.nan))[1] for per in p.index.to_period("M")]
df = df.loc["2010-01-31":]

ST_LBL = {-1: "收紧", 0: "中性", 1: "宽松"}
grid = {}
for idx in IDX_US + IDX_CN:
    g_mean, g_win, g_n = {}, {}, {}
    sub = df.dropna(subset=[idx + "_r", "us_stance", "cn_stance"])
    for u in [-1, 0, 1]:
        for c in [-1, 0, 1]:
            cell = sub[(sub.us_stance == u) & (sub.cn_stance == c)][idx + "_r"]
            g_mean[(ST_LBL[u], ST_LBL[c])] = cell.mean() * 100 if len(cell) else np.nan
            g_win[(ST_LBL[u], ST_LBL[c])] = (cell > 0).mean() * 100 if len(cell) else np.nan
            g_n[(ST_LBL[u], ST_LBL[c])] = len(cell)
    grid[idx] = {"mean": g_mean, "win": g_win, "n": g_n}

# ---------- 3) 相关性 ----------
LVARS = {"Δ联邦基金利率(pp)": "联邦基金利率", "Δlog(美联储总资产)": "美联储总资产",
         "Δ美债10Y(pp)": "美债10Y", "Δ广义美元指数": "广义美元指数"}
d = p.loc["2010-01-31":].copy()
for out, src in LVARS.items():
    if src == "联邦基金利率":
        d[out] = p[src].diff()
    elif src == "美联储总资产":
        d[out] = np.log(p[src]).diff()
    else:
        d[out] = p[src].diff()
cor = {}
for idx in IDX_US + IDX_CN:
    cor[idx] = {}
    for v in LVARS:
        sub = d[[idx, v]].dropna()
        if len(sub) < 24:
            cor[idx][v] = (np.nan, np.nan, len(sub)); continue
        r, pv = stats.pearsonr(sub[idx], sub[v])
        cor[idx][v] = (r, pv, len(sub))
# 交叉市场相关（全期 & 分阶段）
cross = {}
for pname, s0, s1 in [("2010-2020", "2010-01-31", "2020-12-31"), ("2021-2026", "2021-01-31", "2026-09-30"),
             ("全期", "2010-01-31", "2026-09-30")]:
    for cu, cc in [("纳斯达克综指", "上证指数"), ("纳斯达克综指", "中证1000"),
                   ("标普500", "沪深300"), ("纳斯达克综指", "沪深300")]:
        sub = p.loc[s0:s1, [cu, cc]].dropna()
        cross[f"{cu}×{cc}|{pname}"] = stats.pearsonr(sub[cu].pct_change().dropna(),
                                                  sub[cc].pct_change().reindex(
                                                      sub[cu].pct_change().dropna().index).dropna())

# ---------- 4) 保存 Excel ----------
xlsx = Path(A.xlsx)
with pd.ExcelWriter(xlsx, engine="openpyxl") as w:
    p.to_excel(w, sheet_name="月度数据")
    us_cycle.to_excel(w, sheet_name="美联储周期回测", index=False)
    cn_cycle.to_excel(w, sheet_name="中国政策周期回测", index=False)
    gdf = pd.DataFrame({idx: pd.Series(grid[idx]["mean"]) for idx in grid})
    gdf.to_excel(w, sheet_name="中美立场网格_月均收益%")
    cdf = pd.DataFrame({idx: pd.Series({v: cor[idx][v][0] for v in LVARS}) for idx in cor})
    cdf.to_excel(w, sheet_name="相关性_同期")
    df[[c + "_r" for c in IDX_US + IDX_CN]].join(d[list(LVARS)]).to_excel(w, sheet_name="月度收益率")

# ---------- 5) 图表 ----------
sys.path.insert(0, str(Path(sys.executable).parent.parent.parent))
from daimon_runtime import setup_plot
import matplotlib.pyplot as plt
setup_plot()

colors = {"纳斯达克综指": "#7c3aed", "标普500": "#2563eb", "上证指数": "#dc2626",
          "沪深300": "#ea580c", "中证1000": "#ca8a04"}

# fig1 指数走势 + 政策背景
fig, axes = plt.subplots(2, 1, figsize=(13, 8), sharex=True,
                         gridspec_kw={"height_ratios": [3, 2]})
ax = axes[0]
for c in IDX_US:
    s = p[c].dropna(); ax.plot(s.index, s / s.iloc[0], label=c, color=colors[c], lw=1.4)
ax.set_yscale("log"); ax.legend(loc="upper left", fontsize=9); ax.grid(alpha=0.3)
ax.set_title("五大指数归一化走势（实线=美股，左轴；虚线=中国指数，右轴；对数刻度，起点=1）", fontsize=12)
ax2 = ax.twinx()
for c in IDX_CN:
    s = p[c].dropna(); ax2.plot(s.index, s / s.iloc[0], label=c, color=colors[c], lw=1.2, ls="--")
ax2.set_yscale("log"); ax2.legend(loc="lower right", fontsize=9)
b = axes[1]
b.plot(p.index, p["联邦基金利率"], color="#1e293b", lw=1.5, label="联邦基金利率(%)")
b.set_ylabel("利率 %", fontsize=9)
b3 = b.twinx()
b3.plot(p.index, p["美联储总资产"] / 1e6, color="#059669", lw=1.2, alpha=0.8)
b3.set_ylabel("美联储总资产(万亿美元)", fontsize=9)
b.legend(loc="upper left", fontsize=9); b.grid(alpha=0.3)
b.set_title("背景：联邦基金利率 与 美联储资产负债表", fontsize=11)
fig.tight_layout(); fig.savefig(CH / "fig1_indices.png", bbox_inches="tight", dpi=110); plt.close(fig)

# fig2 美国周期 × 各指数 区间收益
order = [r[2] for r in US_REGIMES]
pv = us_cycle.pivot(index="周期", columns="指数", values="区间收益") * 100
pv = pv.reindex([o for o in order if o in pv.index])
fig, ax = plt.subplots(figsize=(13, 6))
xpos = np.arange(len(pv))
for i, c in enumerate(IDX_US + IDX_CN):
    ax.bar(xpos + (i - 2) * 0.16, pv[c], width=0.15, label=c, color=colors[c])
ax.set_xticks(xpos); ax.set_xticklabels([o.split(" ")[0] for o in pv.index], fontsize=9)
ax.set_ylabel("区间收益率 %"); ax.legend(ncol=5, fontsize=9); ax.grid(alpha=0.3, axis="y")
ax.set_title("美联储政策周期内各指数区间收益（%）", fontsize=12)
fig.tight_layout(); fig.savefig(CH / "fig2_cycles.png", bbox_inches="tight", dpi=110); plt.close(fig)

# fig3 3×3 网格 heatmap（月均收益）
fig, axes = plt.subplots(1, 5, figsize=(17, 3.8))
for ax, idx in zip(axes, IDX_US + IDX_CN):
    M = pd.DataFrame(np.nan, index=["收紧", "中性", "宽松"], columns=["收紧", "中性", "宽松"])
    for (u, c), v in grid[idx]["mean"].items():
        M.loc[u, c] = v
    im = ax.imshow(M.values, cmap="RdYlGn", vmin=-4, vmax=4, aspect="auto")
    ax.set_xticks(range(3)); ax.set_xticklabels(M.columns, fontsize=9)
    ax.set_yticks(range(3)); ax.set_yticklabels(M.index, fontsize=9)
    ax.set_xlabel("中国立场", fontsize=9); ax.set_ylabel("美国立场", fontsize=9)
    ax.set_title(idx, fontsize=11)
    for i in range(3):
        for j in range(3):
            v = M.values[i, j]
            if not np.isnan(v):
                ax.text(j, i, f"{v:.1f}", ha="center", va="center", fontsize=10,
                        color="black")
fig.suptitle("月均收益（%）矩阵：美国立场 × 中国立场（2010-01 ~ 2026-09）", fontsize=13)
fig.tight_layout(); fig.savefig(CH / "fig3_grid.png", bbox_inches="tight", dpi=110); plt.close(fig)

# fig4 相关性
Mc = pd.DataFrame({idx: [cor[idx][v][0] for v in LVARS] for idx in IDX_US + IDX_CN},
                  index=list(LVARS)).T
fig, ax = plt.subplots(figsize=(10, 4.6))
im = ax.imshow(Mc.values, cmap="RdBu_r", vmin=-0.6, vmax=0.6, aspect="auto")
ax.set_xticks(range(len(Mc.columns))); ax.set_xticklabels(Mc.columns, fontsize=8.5, rotation=12)
ax.set_yticks(range(len(Mc.index))); ax.set_yticklabels(Mc.index, fontsize=10)
for i in range(Mc.shape[0]):
    for j in range(Mc.shape[1]):
        r, pv_, n_ = cor[Mc.index[i]][Mc.columns[j]]
        star = "*" if pv_ < 0.05 else ""
        ax.text(j, i, f"{r:.2f}{star}" if not np.isnan(r) else "n/a", ha="center", va="center", fontsize=9.5)
fig.colorbar(im, ax=ax, shrink=0.8)
ax.set_title("月度收益率 与 流动性指标同期变化的 Pearson 相关（* = p<0.05）", fontsize=12)
fig.tight_layout(); fig.savefig(CH / "fig4_corr.png", bbox_inches="tight", dpi=110); plt.close(fig)

# fig5 滚动36月相关 + 背景
roll = {}
for cu, cc in [("纳斯达克综指", "沪深300")]:
    a = p[cu].pct_change(); b_ = p[cc].pct_change()
    roll[cu + "×" + cc] = a.rolling(36).corr(b_)
fig, axes = plt.subplots(2, 1, figsize=(13, 7), sharex=True,
                         gridspec_kw={"height_ratios": [2, 3]})
axes[0].plot(p.index, p["联邦基金利率"], lw=1.4, color="#1e293b")
axes[0].set_ylabel("联邦基金利率 %", fontsize=9); axes[0].grid(alpha=0.3)
axes[0].set_title("背景：联邦基金利率", fontsize=11)
for k, v in roll.items():
    axes[1].plot(v.index, v, lw=1.3, label=f"滚动36月相关 {k}")
axes[1].axhline(0, color="gray", lw=0.8)
axes[1].legend(fontsize=10); axes[1].grid(alpha=0.3)
axes[1].set_title("纳斯达克 与 沪深300 滚动36个月收益相关性", fontsize=12)
fig.tight_layout(); fig.savefig(CH / "fig5_rolling.png", bbox_inches="tight", dpi=110); plt.close(fig)

# ---------- 输出 JSON 摘要 ----------
out = {
    "us_cycle": us_cycle.to_dict("records"),
    "cn_cycle": cn_cycle.to_dict("records"),
    "grid_mean": {k: {f"{a}|{b}": v for (a, b), v in d_["mean"].items()} for k, d_ in grid.items()},
    "grid_win": {k: {f"{a}|{b}": v for (a, b), v in d_["win"].items()} for k, d_ in grid.items()},
    "grid_n": {k: {f"{a}|{b}": v for (a, b), v in d_["n"].items()} for k, d_ in grid.items()},
    "corr": {k: {v: [cor[k][v][0], cor[k][v][1]] for v in LVARS} for k in cor},
    "cross": {k: [v[0], v[1]] for k, v in cross.items()},
    "last": {c: (None if p[c].dropna().empty else float(p[c].dropna().iloc[-1])) for c in p.columns},
}
Path(A.stats).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

print("== 美联储周期回测（节选）==")
print(us_cycle[us_cycle["指数"].isin(IDX_US + ["沪深300"])].to_string(
    formatters={"区间收益": "{:+.1%}".format, "年化": lambda x: f"{x:+.1%}" if pd.notna(x) else "n/a",
                "最大回撤": "{:.1%}".format, "月胜率": lambda x: f"{x:.0%}" if pd.notna(x) else "n/a"}))
print("\n== 网格：沪深300 月均收益 ==", {k: round(v, 2) for k, v in grid["沪深300"]["mean"].items()})
print("\n== 相关性（纳指）==", {v: (round(cor["纳斯达克综指"][v][0], 2), round(cor["纳斯达克综指"][v][1], 3)) for v in LVARS})
print("\ncross:", {k: (round(v[0], 2), round(v[1], 3)) for k, v in cross.items()})
print("\nsaved:", xlsx)
