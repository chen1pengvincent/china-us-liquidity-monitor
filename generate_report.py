# -*- coding: utf-8 -*-
"""生成自包含 HTML 研究报告"""
import json, base64, warnings, argparse
from pathlib import Path
import pandas as pd
import numpy as np
warnings.filterwarnings("ignore")

BASE = Path(__file__).parent
AP = argparse.ArgumentParser(description="生成自包含 HTML 研究报告")
AP.add_argument("--stats", default=str(BASE / "stats.json"))
AP.add_argument("--charts", default=str(BASE / "charts"))
AP.add_argument("--panel", default=str(BASE / "data" / "panel_monthly.csv"))
AP.add_argument("--out", default=str(BASE / "中美流动性与五大指数研究报告.html"))
AP.add_argument("--banner", default="")
A = AP.parse_args()

S = json.loads(Path(A.stats).read_text(encoding="utf-8"))
panel = pd.read_csv(A.panel, index_col=0, parse_dates=True)
panel.index = pd.to_datetime(panel.index)

def img64(name):
    return base64.b64encode((Path(A.charts) / name).read_bytes()).decode()

def pct(x, d=1):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x*100:+.{d}f}%"

def fnum(x, d=2):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.{d}f}"

IDX = ["纳斯达克综指", "标普500", "上证指数", "沪深300", "中证1000"]
ST = {1: "宽松", 0: "中性", -1: "收紧"}

# ---- 周期表 ----
def cycle_rows(records, idx_order):
    rows = ""
    for r in records:
        cls = {"宽松": "lo", "中性": "mid", "收紧": "hi"}[ST[r["立场"]]]
        tds = "".join(
            f"<td class='num'>{pct(next((x['区间收益'] for x in records if x['周期']==r['周期'] and x['指数']==i), None))}</td>"
            for i in idx_order)
        rows += f"<tr><td>{r['周期']}</td><td class='{cls}'>{ST[r['立场']]}</td><td class='num'>{r['月数']}</td>{tds}</tr>"
    return rows

us_rows = cycle_rows(S["us_cycle"], IDX)
cn_rows = cycle_rows(S["cn_cycle"], ["上证指数", "沪深300", "中证1000"])

# ---- 附加指标表（周期×指数：年化/回撤/胜率 简表） ----
def ann_table(records, idx_order, title):
    head = "".join(f"<th>{i}</th>" for i in idx_order)
    rows = ""
    seen = set()
    for r in records:
        if r["周期"] in seen: continue
        seen.add(r["周期"])
        tds = ""
        for i in idx_order:
            x = next((z for z in records if z["周期"] == r["周期"] and z["指数"] == i), None)
            tds += f"<td class='num'>{pct(x['年化']) if x else 'n/a'}</td>" if x else "<td class='num'>n/a</td>"
        rows += f"<tr><td>{r['周期']}</td>{tds}</tr>"
    return f"<h4>{title}</h4><table class='mini'><tr><th>周期</th>{head}</tr>{rows}</table>"

us_ann = ann_table(S["us_cycle"], IDX, "美国周期 × 指数：年化收益")
cn_ann = ann_table(S["cn_cycle"], ["上证指数", "沪深300", "中证1000"], "中国周期 × 指数：年化收益")

# ---- 网格表（含样本量） ----
def grid_table(metric_key, title):
    head = "".join(f"<th>中国:{c}</th>" for c in ["收紧", "中性", "宽松"])
    rows = ""
    for u in ["收紧", "中性", "宽松"]:
        tds = ""
        for c in ["收紧", "中性", "宽松"]:
            key = f"{u}|{c}"
            cells = []
            for idx in IDX:
                v = S[metric_key][idx].get(key)
                n = S["grid_n"][idx].get(key, 0)
                cells.append(f"{fnum(v,1) if v is not None else '—'}<span class='n'>({n})</span>")
            tds += "<td class='num'>" + "<br>".join(cells) + "</td>"
        rows += f"<tr><td><b>美国:{u}</b></td>{tds}</tr>"
    legend = "<div class='note'>每格数值顺序：纳斯达克 / 标普500 / 上证 / 沪深300 / 中证1000；括号内为月样本数。" \
             "灰格（—）表示该组合在历史上未出现或样本不足。</div>"
    return f"<h4>{title}</h4><table class='grid'><tr><th></th>{head}</tr>{rows}</table>{legend}"

grid_mean_tbl = grid_table("grid_mean", "组合矩阵①：月均收益率（%）")

# ---- 相关性表 ----
LV = list(S["corr"]["纳斯达克综指"].keys())
def corr_table():
    head = "".join(f"<th>{v}</th>" for v in LV)
    rows = ""
    for idx in IDX:
        tds = ""
        for v in LV:
            r, p = S["corr"][idx][v]
            star = "*" if p < 0.05 else ""
            tds += f"<td class='num'>{fnum(r,2)}{star}</td>"
        rows += f"<tr><td>{idx}</td>{tds}</tr>"
    return f"<table class='mini'><tr><th>指数</th>{head}</tr>{rows}</table>"

corr_tbl = corr_table()
cross_rows = "".join(
    f"<tr><td>{k}</td><td class='num'>{fnum(v[0],2)}</td><td class='num'>{'p<0.05' if v[1]<0.05 else f'p={v[1]:.2f}'}</td></tr>"
    for k, v in S["cross"].items())

# ---- 2026-09 单月表现 ----
last2 = panel.loc["2026-08-31":"2026-09-30", IDX].dropna(how="all")
sep_ret = (last2.loc["2026-09-30"] / last2.loc["2026-08-31"] - 1)
sep_tbl = "".join(f"<tr><td>{i}</td><td class='num'>{pct(sep_ret[i])}</td></tr>" for i in IDX)

banner_html = (f'<div class="card" style="background:#fef3c7;border:1px solid #f59e0b;'
               f'color:#92400e;font-weight:600">{A.banner}</div>') if A.banner else ""

HTML = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>中美流动性政策与主要指数传导关系研究报告 · 2026-09</title>
<style>
:root {{ --ink:#1a2332; --mut:#5b6779; --bg:#f5f6f8; --card:#ffffff; --line:#e3e7ee;
  --red:#c0392b; --grn:#1e8449; --amb:#b9770e; --blu:#1f4e8c; }}
* {{ box-sizing:border-box; }}
body {{ font-family:-apple-system,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  margin:0; background:var(--bg); color:var(--ink); line-height:1.75; }}
.wrap {{ max-width:1080px; margin:0 auto; padding:32px 22px 80px; }}
h1 {{ font-size:26px; margin:0 0 4px; }}
h2 {{ font-size:20px; border-left:4px solid var(--blu); padding-left:10px; margin-top:48px; }}
h3 {{ font-size:16px; margin-top:28px; color:var(--blu); }}
h4 {{ font-size:14px; margin:22px 0 8px; color:var(--mut); }}
.sub {{ color:var(--mut); font-size:13px; margin-bottom:24px; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:10px;
  padding:20px 24px; margin:16px 0; }}
.exec {{ background:linear-gradient(135deg,#10233f,#1f4e8c); color:#fff; border:none; }}
.exec h2 {{ color:#fff; border-left-color:#ffd166; }}
.exec .kpi {{ display:flex; flex-wrap:wrap; gap:12px; margin:14px 0; }}
.exec .kpi div {{ background:rgba(255,255,255,.10); border:1px solid rgba(255,255,255,.25);
  border-radius:8px; padding:10px 14px; min-width:150px; }}
.exec .kpi b {{ display:block; font-size:20px; }}
.exec .kpi span {{ font-size:12px; opacity:.85; }}
table {{ border-collapse:collapse; width:100%; font-size:13px; background:#fff; }}
th,td {{ border:1px solid var(--line); padding:6px 9px; text-align:left; vertical-align:middle; }}
th {{ background:#eef2f7; font-weight:600; white-space:nowrap; }}
td.num,th.num {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
tr:nth-child(even) td {{ background:#fafbfd; }}
.mini td,.mini th {{ padding:4px 8px; font-size:12.5px; }}
.grid td {{ font-size:12px; line-height:1.5; }}
span.n {{ color:var(--mut); font-size:10.5px; }}
td.lo {{ color:var(--grn); font-weight:600; }} td.mid {{ color:var(--amb); font-weight:600; }} td.hi {{ color:var(--red); font-weight:600; }}
img {{ max-width:100%; border:1px solid var(--line); border-radius:8px; margin:10px 0; }}
.note {{ font-size:12px; color:var(--mut); margin:6px 0 14px; }}
ul,ol {{ padding-left:22px; }}
li {{ margin:5px 0; }}
a {{ color:var(--blu); word-break:break-all; }}
.src {{ font-size:12px; color:var(--mut); }}
.badge {{ display:inline-block; padding:1px 9px; border-radius:99px; font-size:12px; font-weight:600; }}
.b-tight {{ background:#fdecea; color:var(--red); }} .b-ease {{ background:#e9f7ef; color:var(--grn); }}
.b-neu {{ background:#fef5e7; color:var(--amb); }}
.disc {{ font-size:12px; color:var(--mut); border-top:1px dashed var(--line); margin-top:48px; padding-top:16px; }}
</style></head><body><div class="wrap">

<h1>中美流动性政策 × 五大指数：传导机制、历史回测与监测框架</h1>
<div class="sub">报告生成：{pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")} ｜ 数据截至：{panel.index.max().strftime("%Y-%m")}（未完结月份为最新交易日） ｜ 覆盖标的：纳斯达克综指、标普500、上证指数、沪深300、中证1000</div>
{banner_html}

<div class="card exec">
<h2 style="margin-top:0">执行摘要</h2>
<p><b>当前中美流动性处于罕见的背离组合：</b>美联储于 2026-09-16 加息 25bp 至 <b>3.75%–4.00%</b>（三年多来首次加息，通胀回升，PCE 预期 3.7%），但缩表（QT）已于 2025-12-01 结束，当前为"全额再投资 + 准备金管理购买（RMP）"的<b>资产负债表中性</b>状态；中国人民银行 2026 年全年维持"<b>适度宽松</b>"货币政策表述（2024 年 12 月由"稳健"转向以来未变），一季度 M2 同比 +8.5%、社融存量 +7.9%、贷款利率约 3.1%。</p>
<div class="kpi">
<div><span>美联储政策利率</span><b>3.75–4.00%</b><span>2026-09 重启加息</span></div>
<div><span>美联储资产负债表</span><b>≈6.75万亿美元</b><span>QT已结束·中性维护</span></div>
<div><span>中国货币政策基调</span><b>适度宽松</b><span>2024-12定调·延续至今</span></div>
<div><span>中美组合状态</span><b>美紧 · 中宽</b><span>无干净的长期历史样本</span></div>
</div>
<p><b>四个核心发现：</b></p>
<ol>
<li><b>美国流动性主导美股，但作用在"周期级别"而非"月度级别"。</b>零利率+QE 周期纳斯达克年化 +16%~+52%；激进加息周期（从首次加息月算）纳指区间 +16% 但期间最大回撤 -15.5%（若从 2021 年末高点算则约 -35%，见对抗式审查）。同期月频相关性普遍不显著（|r|&lt;0.15）——月度择时不可用，周期定位可用。</li>
<li><b>中国政策立场是 A 股的关键区分变量：</b>"美宽×中宽"格（n=36，覆盖 2014-11~2015-11、2019H2、2024-10~2025-11）沪深300 月均 +1.65%、中证1000 月均 +2.7%；而中国收紧的三列中，A 股月均收益均不高于 +0.4%——<b>外部宽松无法替代内部宽松</b>。</li>
<li><b>中美股市联动性大幅脱钩。</b>标普500×沪深300 月收益相关系数从 2010–2020 年的 <b>0.62</b> 降至 2021–2026 年的 <b>0.17</b>——外部流动性通过情绪与资金传导至 A 股的通道已明显弱化，中国内部政策成为主导变量。</li>
<li><b>对当前的含义：</b>对 A 股，"中宽"是顺风、"美紧"主要经由汇率与风险偏好边际传导（2026-09 当月上证 -2.5%、沪深300 -4.0%，同期纳指 +2.6%）；对美股，重启加息构成估值压制，但历史（R7/R8）证明强劲盈利叙事可阶段性对冲。</li>
</ol>
<p style="font-size:12.5px;opacity:.85">本报告不构成投资建议。所有政策状态与数据均标注来源；历史回测存在多重方法论局限（见第七章对抗式审查）。</p>
</div>

<h2>第一章 · 当前状态核实（截至 {pd.Timestamp.now().strftime("%Y-%m-%d")}）</h2>
<div class="card">
<h3>美国：重启加息 + 资产负债表中性</h3>
<table>
<tr><th>项目</th><th>当前状态</th><th>关键事实</th></tr>
<tr><td>联邦基金利率目标区间</td><td class="num"><b>3.75% – 4.00%</b></td><td>2026-09-16 FOMC 加息 25bp（12-0 全票通过），三年多来首次加息；2026-07 会议已有 3 名委员 dissent 要求加息</td></tr>
<tr><td>通胀背景</td><td class="num">PCE 预期 3.7%（2026）</td><td>9 月 SEP 将 2026 年 PCE 从 3.6% 上调至 3.7%、核心 3.4%；声明称"通胀仍然偏高"，主因能源等供给冲击</td></tr>
<tr><td>资产负债表</td><td><span class="badge b-neu">QT已结束·中性维护</span></td><td>证券 runoff 于 <b>2025-12-01</b> 停止（2022-06 以来累计缩减逾 2.2 万亿美元，9万亿→6.5万亿）；当前国债本金全额续作、机构债本金转投国库券，按需购买短债维持充足准备金（RMP），9/15–10/14 再投资购买约 156 亿美元、额外 RMP 为零</td></tr>
<tr><td>点阵图路径</td><td class="num">2026 年末中值 4.125%</td><td>9 月 SEP：12 人认为年内再加息至 4.125% 中值（即年内或还有 1 次 25bp），2027 年末 4.1%、长期 3.1%</td></tr>
</table>
<div class="src">来源：美联储 FOMC 声明与实施说明（2026-09-16）、7 月会议纪要（2026-08-19）、9 月经济预测摘要；缩表状态另经纽约联储 RMP 安排交叉核对。</div>

<h3>中国："适度宽松"延续第二年</h3>
<table>
<tr><th>时间</th><th>事件</th><th>表述/数据</th></tr>
<tr><td>2026-01</td><td>潘功胜行长表态</td><td>继续实施好<b>适度宽松</b>的货币政策；"今年降准降息还有一定的空间"</td></tr>
<tr><td>2026-03</td><td>两会经济主题记者会</td><td>灵活高效运用降准降息等多种工具；保持流动性充裕</td></tr>
<tr><td>2026-03</td><td>货币政策委员会 Q1 例会</td><td>"货币政策保持适度宽松…要继续实施适度宽松的货币政策"</td></tr>
<tr><td>2026-05</td><td>Q1 货币政策执行报告</td><td>继续实施适度宽松；M2 同比 +8.5%、社融存量 +7.9%、新发放企业贷款与个人房贷利率均约 3.1%；一季度 GDP +5%</td></tr>
<tr><td>2026-08</td><td>央行 2026 下半年工作会议</td><td>继续实施适度宽松的货币政策，<b>加大逆周期调节力度</b></td></tr>
</table>
<div class="src">来源：中国人民银行官网《2026年第一季度中国货币政策执行报告》、人民网/新华社 2026-03-06 报道、武汉市金融局转载央行例会通稿（2026-04-01）、2026-08 央行下半年工作会议报道。</div>
<div class="note">判定：中国处于<b>明确宽松周期</b>（"适度宽松"为 2011 年以来首次改变的官方基调，自 2024-12 中央经济工作会议定调后延续至今未变）。</div>
</div>

<h2>第二章 · 流动性判断标准（方法论）</h2>
<div class="card">
<p>用户提出的两项标准均成立，本报告采纳并补充操作化细节：</p>
<h3>美国流动性（双支柱）</h3>
<table>
<tr><th>支柱</th><th>指标</th><th>判定规则</th></tr>
<tr><td>① 价格型</td><td>联邦基金利率目标区间（FOMC 决议）</td><td>方向（加息/降息/按兵不动）+ 水平（限制性 vs 中性 vs 宽松，对照 SEP 长期值 3.1%）</td></tr>
<tr><td>② 数量型</td><td>美联储资产负债表（WALCL，每周四 H.4.1）</td><td>扩表（QE/购买）→ 宽松；runoff（QT）→ 收紧；全额续作+RMP → 中性维护</td></tr>
</table>
<h3>中国流动性（以央行表态为主，政策取向与信用信号为辅）</h3>
<table>
<tr><th>层级</th><th>指标</th><th>说明</th></tr>
<tr><td>① 表态（最高权重）</td><td>中央经济工作会议定调、货币政策执行报告、货政委员会例会、行长讲话</td><td>"适度宽松"=宽松；"稳健"=中性；"稳健中性/管住货币供给总闸门"=偏紧。用户确认的标准</td></tr>
<tr><td>② 政策取向</td><td>降准/降息（OMO、MLF、LPR）动作与方向</td><td>动作本身及节奏（如 2024-09-24 组合拳 = 强宽松信号）</td></tr>
<tr><td>③ 信用信号</td><td>社融存量增速、M2 同比、M1-M2 剪刀差、DR007 与 7 天逆回购利率偏离</td><td>验证"宽货币"是否转化为"宽信用"</td></tr>
</table>
<h3>两个补充原则</h3>
<ul>
<li><b>预期差原则：</b>资产价格反应的是"决议 vs 市场预期"的差，而非决议本身。同样降息 25bp，低于预期的宽松路径仍可能引发下跌（2024-12 与 2025 年多次出现）。监测时应同步跟踪 CME FedWatch 隐含概率。</li>
<li><b>资产负债表"目的区分"原则：</b>购买短债维持准备金（RMP）≠ QE。2025-12 后的购买以利率控制为目标，宽松含义远弱于 2020 年 QE（压低长期利率）。判定宽松与否要看对期限溢价与金融条件的影响，而非购买行为本身。</li>
</ul>
</div>

<h2>第三章 · 历史政策周期回测（2010–2026）</h2>
<div class="card">
<div class="note">周期划分为本报告基于已核实政策事件的事后划分（FOMC 决议日期、央行官方文件），非实时可交易信号。立场：宽松=+1 / 中性=0 / 收紧=-1。数据说明（管道 v2，Tushare+FRED）：标普500 自 2010-01 起（Tushare 全球指数，与 FRED 官方标普序列在 121 个重叠月份上差异为 0.0000%）；中证1000 自 2005-01 起（Tushare 回溯计算，此前版本受发布日限制仅 2014-10 起）；未完结月份以日线累计至最新交易日；纳斯达克 2005-2010 段由 FRED NASDAQCOM 回填（与 Tushare 重叠期最大相对差 0.0015%）。</div>
<img src="data:image/png;base64,{img64('fig1_indices.png')}" alt="指数走势">
<h3>美联储政策周期 × 五大指数：区间收益</h3>
<table>
<tr><th>美联储周期</th><th>立场</th><th>月数</th><th class='num'>纳斯达克</th><th class='num'>标普500</th><th class='num'>上证</th><th class='num'>沪深300</th><th class='num'>中证1000</th></tr>
{us_rows}
</table>
{us_ann}
<img src="data:image/png;base64,{img64('fig2_cycles.png')}" alt="周期收益">
<h3>中国政策周期 × 中国指数：区间收益</h3>
<table>
<tr><th>中国周期</th><th>立场</th><th>月数</th><th class='num'>上证指数</th><th class='num'>沪深300</th><th class='num'>中证1000</th></tr>
{cn_rows}
</table>
{cn_ann}
<h3>解读</h3>
<ul>
<li><b>美股对"价格型宽松"最敏感的是纳斯达克：</b>R5（零利率+无限QE）纳指区间 +101.8%（年化 +52.4%）；同周期标普 +76.7%——成长/久期资产的折现率弹性大于价值股。</li>
<li><b>"加息但盈利强"并非必跌：</b>R7、R8 期间美股均为正收益（AI/盈利叙事对冲），但过程波动极大（纳指 R7 最大回撤 -15.5%，且若按周期前高点计算达约 -35%，见第七章）。</li>
<li><b>A 股与中国政策取向的关系在 2024-09 后质变：</b>C9（适度宽松，2024-09~2026-09 共 25 个月）上证区间 +16.5%、沪深300 +10.5%、中证1000 +32.6%，显著强于 C8 渐进宽松时期（32 个月上证 -15.4%）——<b>表态的力度本身成为定价变量</b>。但 2026 年 2–6 月见顶后中证1000 已自峰值回撤 -14.1%（其 C9 最大回撤 -19.7% 恰发生在 2026-07 美联储转鹰当月），外部收紧对弹性品种的边际压制清晰可见。</li>
<li><b>双紧组合历史上极少出现：</b>美国收紧与中国收紧的重叠仅 2017Q4 约 3 个月，样本不足以统计推断——当前"美紧中宽"同样是历史上少有的组合（另见第四章矩阵）。</li>
</ul>
</div>

<h2>第四章 · 中美流动性组合矩阵（2010-01 ~ 2026-09）</h2>
<div class="card">
<p>将 200 个月按"美国立场 × 中国立场"分类，计算各指数月均收益：</p>
{grid_mean_tbl}
<img src="data:image/png;base64,{img64('fig3_grid.png')}" alt="组合矩阵">
<h3>解读（注意小样本）</h3>
<ul>
<li>美股矩阵高度单调：<b>美国宽松行（下行）几乎全部为正，收紧行（上行）分化</b>——印证美股由美国自身流动性主导，中国立场对美股几乎无增量信息。</li>
<li>A 股矩阵中信息量最大的是"中国列"：<b>中国宽松列（右列）在美宽时最强（n=36：上证 +1.6%、中证1000 +2.7%/月）</b>；中国收紧时（左列）A 股月均收益全为负或接近零，即使美国宽松。</li>
<li>2026-09（美重启加息、中适度宽松）对应矩阵中的"美紧×中宽"格（<b>n=50</b>，主要为 2018-01~2019-07 与 2022-04~2024-08，叠加贸易战与地产下行，需与其他冲击区分）：上证与沪深300 月均约 -0.1%、中证1000 月均 -0.7%——<b>外部收紧会削弱但不会逆转内部宽松行情，且对高弹性品种拖累更大</b>。</li>
</ul>
</div>

<h2>第五章 · 长期相关性检验（月度频率，2010–2026）</h2>
<div class="card">
<h3>指数月收益 vs 流动性指标同期变化（Pearson，* = p&lt;0.05）</h3>
{corr_tbl}
<div class="note">多重检验警告：5 指数 × 4 变量 = 20 次检验，5% 显著水平下期望出现 1 个假阳性；且未对序列自相关校正。结论以方向与量级为主，不以单颗星为准。</div>
<h3>跨市场相关（月收益）</h3>
<table><tr><th>组合</th><th class='num'>相关系数</th><th class='num'>显著性</th></tr>{cross_rows}</table>
<img src="data:image/png;base64,{img64('fig4_corr.png')}" alt="相关性">
<img src="data:image/png;base64,{img64('fig5_rolling.png')}" alt="滚动相关">
<h3>三个诚实的结论</h3>
<ol>
<li><b>月频上，流动性指标与指数收益的相关性弱且不稳健</b>（多数 |r|&lt;0.2）。流动性→股市的传导是"状态依赖 + 周期级别"的：同样的缩表，在准备金充裕期（2017-2019）冲击有限，在准备金稀缺边缘（2025 年货币市场压力）冲击被放大。</li>
<li><b>中美联动显著但持续衰减：</b>滚动 36 个月相关在 2015、2020 年两次冲上 0.6+，2021 年后趋势性回落——与 A 股投资者结构变化、资本账户管理、以及两地产业叙事分化一致。</li>
<li><b>使用建议：</b>该相关性矩阵<b>不适合月度择时</b>；适合用作"当前处于何种流动性组合、历史上该组合下谁胜率高"的定位工具。</li>
</ol>
</div>

<h2>第六章 · 监测框架（可每月更新）</h2>
<div class="card">
<h3>仪表盘 A：美国流动性（更新频率与来源）</h3>
<table>
<tr><th>指标</th><th>频率/日期</th><th>来源</th><th>当前读数（2026-09）</th><th>状态灯</th></tr>
<tr><td>联邦基金利率目标区间</td><td>FOMC 每年 8 次（2026 年内剩余：预计 10–11 月、12 月会议）</td><td>federalreserve.gov 声明</td><td class="num">3.75–4.00%（9/16 加息 25bp）</td><td><span class="badge b-tight">收紧</span></td></tr>
<tr><td>点阵图/SEP 路径</td><td>季末会议（3/6/9/12 月）</td><td>SEP</td><td class="num">2026 年末中值 4.125%</td><td><span class="badge b-tight">偏鹰</span></td></tr>
<tr><td>SOMA 证券持仓 / WALCL</td><td>每周四 H.4.1</td><td>纽约联储</td><td class="num">总资产 ≈6.75 万亿美元</td><td><span class="badge b-neu">中性维护</span></td></tr>
<tr><td>RMP 月度购买计划</td><td>每月中旬公布次月安排</td><td>纽约联储</td><td class="num">再投资 ~156 亿/月，额外 RMP=0</td><td><span class="badge b-neu">观察</span></td></tr>
<tr><td>SOFR–IORB 利差</td><td>每日</td><td>纽约联储</td><td colspan="2">2025 年 9 月起曾走阔（流动性趋紧信号）→ 触发 QT 结束；继续走阔 = 提前扩表信号</td></tr>
<tr><td>市场预期（CME FedWatch）</td><td>实时</td><td>CME</td><td colspan="2">决议前对照隐含概率，量化"预期差"</td></tr>
</table>
<h3>仪表盘 B：中国流动性</h3>
<table>
<tr><th>指标</th><th>频率/日期</th><th>来源</th><th>当前读数（2026-09）</th><th>状态灯</th></tr>
<tr><td>货币政策基调表述</td><td>季度（货政报告/例会）+ 年度（中央经济工作会议，通常 12 月）</td><td>pbc.gov.cn</td><td>"适度宽松"（2024-12 定调，2026 全程延续，8 月会议要求"加大逆周期调节力度"）</td><td><span class="badge b-ease">宽松</span></td></tr>
<tr><td>7 天逆回购利率（政策利率）</td><td>不定期</td><td>人民银行</td><td colspan="2">下调=宽松信号（2026 年内仍有降准降息空间——央行行长 1 月表述）</td></tr>
<tr><td>LPR（1 年/5 年）</td><td>每月 20 日</td><td>全国银行间同业拆借中心</td><td colspan="2">5 年期与房贷利率联动，观察降幅与节奏</td></tr>
<tr><td>社融存量 / M2 同比</td><td>每月中旬</td><td>人民银行</td><td class="num">+7.9% / +8.5%（2026-03）</td><td><span class="badge b-ease">宽信用</span></td></tr>
<tr><td>DR007 与政策利率偏离</td><td>每日</td><td>外汇交易中心</td><td colspan="2">持续低于政策利率 = 资金面充裕</td></tr>
<tr><td>M1–M2 剪刀差</td><td>每月</td><td>人民银行</td><td colspan="2">收窄转正 = 资金活化，权益顺风加强</td></tr>
</table>
<h3>更新触发器（事件驱动）</h3>
<ul>
<li><b>FOMC 决议日（每年 8 次）：</b>更新利率灯；比对决议与 FedWatch 预期差；读取声明措辞变化（本次新增"will deliver price stability"式硬措辞即鹰派信号）。</li>
<li><b>季度货政报告与例会（约 2/5/8/11 月）：</b>检查"适度宽松"表述是否变化——<b>这是 A 股最重要的单一文本信号</b>；关注"闸门""不搞大水漫灌"等紧缩词回潮。</li>
<li><b>降准/降息/国债买卖公告：</b>动作确认宽松落地节奏。</li>
<li><b>每年 12 月中央经济工作会议：</b>次年基调定调（2024-12 的"适度宽松"使 C9 成为 A 股历史上最强的政策驱动周期之一）。</li>
<li><b>组合判定规则：</b>美灯×中灯 → 对照第四章矩阵定位历史基线，再结合样本量打折使用。</li>
</ul>
<h3>2026-09 当月市场反应（加息决议后至月末）</h3>
<table><tr><th>指数</th><th class='num'>2026-09 月收益</th></tr>{sep_tbl}</table>
<div class="note">读法：重启加息当月 A 股回撤、美股上行——与第四章"美紧×中宽"格的历史基线方向一致（A 股 -0.1%~-0.7%/月），但单月不构成统计意义。</div>
</div>

<h2>第七章 · 对抗式审查</h2>
<div class="card">
<ol>
<li><b>信源冲突已处理：</b>某自媒体（B 级信源）称"2026 年 7 月重启被动缩表、沃什推行更多缩表"，与美联储 2026-09-16 官方实施说明（国债本金全额续作、机构债转投国库券、按需购短债维持充足准备金）及 7 月会议纪要直接矛盾。<b>本报告采用美联储一手文件为准。</b>残余风险：若后续 H.4.1 显示证券持仓持续净下降，需重估"资产负债表中性"判定。</li>
<li><b>数据源切换（2026-09-28 管道 v2）：</b>指数行情已由腾讯非官方接口切换至 Tushare Pro（专业 API），并完成三组交叉验证：上证/沪深300 与腾讯留档一致；标普500 与 FRED 重叠 121 个月差异 0.0000%；纳斯达克拼接处重叠 261 个月最大相对差 0.0015%。切换修复了原有两个缺口：标普500 现覆盖 2010-01 起（R1/R2 周期可算）、中证1000 现覆盖 2005-01 起（C1–C2 周期可算）。残余缺口：FEDFUNDS 滞后约 1 个月（2026-09 用目标中值 3.875 补丁）；Tushare 月线月末才更新，当月值为 MTD 盘中累计，月末会微调。</li>
<li><b>区间收益对起止月份敏感：</b>全部边界按自然月处理。例：R7（2022-04 起）纳指 +16.3% 的起点是 2022 年 4 月末（当月已大跌 13%），若从 2022-01 计算则约 -25%；同期最大回撤 -15.5% 也低于盘中实际（2021-11 高点至 2022-12 低点约 -35%）。<b>所有周期数字都应配合最大回撤与胜率一起读。</b></li>
<li><b>小样本：</b>R4 仅 7 个月、R6（Taper）仅 4 个月、R11 仅 1 个月；"双紧"格仅 3 个月（2017Q4），不足以下结论。样本相对充足的格子是"双宽"（n=36）与"美紧中宽"（n=50）——但前者横跨 2014-15、2019、2024-25 三轮环境，后者主要由 2018 与 2022-2024 构成、混杂贸易战与地产危机，<b>都不能干净地归因于流动性</b>。</li>
<li><b>前视偏差：</b>周期与立场标签由事后完整的政策路径划定，回测不含"当时能否识别转折点"的成本。实际可交易信号会滞后 1–3 个月，收益将系统性低于表中数字。</li>
<li><b>相关≠因果 + 多重检验：</b>月频相关性弱且多数不显著；20 次检验未校正；流动性变量与指数收益同受增长/通胀预期驱动，存在共同因子混淆。</li>
<li><b>结构事件混杂：</b>2015 年 A 股异常波动、2018 贸易战、2020 疫情、2022 俄乌与通胀冲击、2024-09 中国政策转向、2026 年中东局势与供给型通胀——每个周期都叠加非流动性主导的事件，单一归因不成立。</li>
<li><b>立场分类的主观性：</b>"中性"与"宽松/收紧"的边界存在判断空间（如 R2 首次加息但资产负债表仍扩张、C5"松中带稳"）。更换分类会改变表格数字；本报告分类已尽量依据官方措辞与决议事实，并保留全部边界月份供复核（见数据包）。</li>
<li><b>汇率通道未建模：</b>"美紧中宽"下美元走强与人民币资产相对吸引力上升两种力量未在指数收益中分离；2026 年人民币升至 6.91 附近已部分反映该组合。</li>
<li><b>数据口径：</b>中国指数为腾讯月线收盘价（指数无需复权）；FEDFUNDS 为月度均值而非目标区间中值（2026-09 用中值 3.875 补丁）；美联储总资产为周度月末值。</li>
</ol>
</div>

<div class="disc">
<p><b>免责声明：</b>本报告基于公开信息与历史数据编制，仅供研究参考，不构成任何证券投资建议或收益承诺。历史表现不代表未来。数据来源：Tushare Pro（指数行情，用户 token）、FRED/圣路易斯联储（美国宏观序列）、美联储/中国人民银行官方文件及公开报道（详见各章标注）。图表与回测代码、完整数据见随附 Excel 数据包。</p>
<p>分析窗口：2010-01 ~ {panel.index.max().strftime("%Y-%m")}（月度）｜ 指数：纳斯达克综指、标普500、上证指数、沪深300、中证1000</p>
</div>

</div></body></html>"""

out = Path(A.out)
out.write_text(HTML, encoding="utf-8")
print("saved:", out, f"{out.stat().st_size/1024:.0f} KB")
