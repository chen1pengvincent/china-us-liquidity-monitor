# -*- coding: utf-8 -*-
"""
数据管道 v2：Tushare（指数，主源）+ FRED（美国宏观，唯一源）+ 腾讯（兜底）
- 中国指数：tushare index_monthly 全历史 + index_daily 当月累计（MTD）
- 美股指数：tushare index_global 日频聚合月线（2010-10 起）+ FRED NASDAQCOM 回填 2005-2010
- 宏观：FRED FEDFUNDS / WALCL / DGS10 / DTWEXBGS
输出：data/panel_monthly.csv
"""
import sys, json, urllib.request, warnings, time
from pathlib import Path
warnings.filterwarnings("ignore")
import pandas as pd
import numpy as np

OUT = Path(__file__).parent / "data"
OUT.mkdir(exist_ok=True)

# ---------------- Tushare ----------------
import tushare as ts

def get_token():
    p = Path.home() / ".tushare_token"
    if p.exists():
        return p.read_text().strip()
    import os
    return os.environ.get("TUSHARE_TOKEN", "")

ts.set_token(get_token())
PRO = ts.pro_api()

def ts_monthly_cn(ts_code):
    """中国指数：月线的全历史 + 当月 MTD（index_daily 最后一根）"""
    m = PRO.index_monthly(ts_code=ts_code, start_date="19900101",
                          end_date=pd.Timestamp.today().strftime("%Y%m%d"))
    m["date"] = pd.to_datetime(m["trade_date"], format="%Y%m%d")
    s = m.set_index("date")["close"].sort_index()
    s.index = s.index.to_period("M").to_timestamp("M")
    # 当月 MTD
    cur = pd.Timestamp.today().strftime("%Y%m01")
    today = pd.Timestamp.today().strftime("%Y%m%d")
    d = PRO.index_daily(ts_code=ts_code, start_date=cur, end_date=today)
    if len(d):
        last_close = float(d.sort_values("trade_date")["close"].iloc[-1])
        mth = pd.Timestamp.today().to_period("M").to_timestamp("M")
        if mth not in s.index:
            s = pd.concat([s, pd.Series({mth: last_close})])
    return s[~s.index.duplicated(keep="last")]

def ts_monthly_global(ts_code):
    """全球指数（IXIC/SPX）：index_global 日频按年分段拉取（防 4000 行上限），聚合月线"""
    frames = []
    for y0 in range(2010, pd.Timestamp.today().year + 1, 3):
        y1 = min(y0 + 2, pd.Timestamp.today().year)
        for attempt in range(3):
            try:
                g = PRO.index_global(ts_code=ts_code,
                                     start_date=f"{y0}0101", end_date=f"{y1}1231")
                frames.append(g)
                break
            except Exception:
                time.sleep(3 * (attempt + 1))
        time.sleep(0.4)  # 限速：每分钟 200 次
    g = pd.concat(frames).drop_duplicates("trade_date")
    g["date"] = pd.to_datetime(g["trade_date"], format="%Y%m%d")
    s = g.set_index("date")["close"].sort_index().resample("ME").last()
    s.index = s.index.to_period("M").to_timestamp("M")
    return s[~s.index.duplicated(keep="last")]

# ---------------- FRED ----------------
def fred_csv(series, start="2005-01-01"):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}&cosd={start}"
    df = pd.read_csv(url)
    df.columns = ["date", series]
    df[series] = pd.to_numeric(df[series].replace(".", np.nan))
    df["date"] = pd.to_datetime(df["date"])
    s = df.set_index("date")[series]
    s.index = s.index.to_period("M").to_timestamp("M")
    return s.resample("ME").last()

# ---------------- 腾讯兜底 ----------------
def tx_kline(symbol, n=640):
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={symbol},month,,,{n},qfq"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        j = json.loads(r.read().decode("utf-8"))
    rows = j["data"][symbol]["month"]
    df = pd.DataFrame(rows, columns=["date", "open", "close", "high", "low", "vol"])
    df["date"] = pd.to_datetime(df["date"])
    s = pd.to_numeric(df.set_index("date")["close"])
    s.index = s.index.to_period("M").to_timestamp("M")
    return s[~s.index.duplicated(keep="last")]

# ---------------- 主流程 ----------------
series_list, src_log = {}, []

print("== Tushare 主源 ==")
# 中国指数
for code, name, fb in [("000001.SH", "上证指数", "sh000001"),
                       ("000300.SH", "沪深300", "sh000300"),
                       ("000852.SH", "中证1000", "sh000852")]:
    try:
        s = ts_monthly_cn(code)
        series_list[name] = s.rename(name)
        src_log.append(f"{name}: tushare {s.index.min().date()} -> {s.index.max().date()} n={len(s)}")
    except Exception as e:
        s = tx_kline(fb)
        series_list[name] = s.rename(name)
        src_log.append(f"{name}: 腾讯兜底({e}) {s.index.min().date()} -> {s.index.max().date()}")

# 美股指数（tushare index_global）
fred_nas = fred_csv("NASDAQCOM", "2005-01-01")
for code, name in [("IXIC", "纳斯达克综指"), ("SPX", "标普500")]:
    s = ts_monthly_global(code)
    if code == "IXIC":
        back = fred_nas.loc[: "2010-09-30"].dropna()
        s = pd.concat([back, s]).sort_index()
        s = s[~s.index.duplicated(keep="last")]
    series_list[name] = s.rename(name)
    src_log.append(f"{name}: tushare+FRED回填 {s.index.min().date()} -> {s.index.max().date()} n={len(s)}")

print("\n".join(src_log))

# 拼接校验：IXIC 与 FRED NASDAQCOM 重叠期差异
both = pd.concat([fred_nas, series_list["纳斯达克综指"]], axis=1).dropna()
rel = ((both.iloc[:, 0] - both.iloc[:, 1]).abs() / both.iloc[:, 0])
print(f"[校验] IXIC×FRED 重叠 {len(both)} 个月, 最大相对差 {rel.max():.4%}")

print("== FRED 宏观 ==")
for sid, name in [("FEDFUNDS", "联邦基金利率"), ("WALCL", "美联储总资产"),
                  ("DGS10", "美债10Y"), ("DTWEXBGS", "广义美元指数")]:
    s = fred_csv(sid)
    series_list[name] = s.rename(name)
    print(f"{sid}: {s.dropna().index.min().date()} -> {s.dropna().index.max().date()} n={s.notna().sum()}")

panel = pd.concat(series_list.values(), axis=1).sort_index()
panel = panel.loc[panel.index >= "2005-12-31"]
panel.to_csv(OUT / "panel_monthly.csv", encoding="utf-8-sig")
(OUT / "sources.log").write_text("\n".join(src_log), encoding="utf-8")
print("\npanel:", panel.shape, panel.index.min().date(), "->", panel.index.max().date())
print(panel.tail(4).to_string())
