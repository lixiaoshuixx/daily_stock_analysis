# 分析模块发送给大模型的信息说明

本文档说明：在调用大模型（LLM）之前，分析流水线会准备哪些信息，以及最终发送给模型的内容是什么。

---

## 一、调用大模型前，系统会给你（分析模块）什么信息？

在 `pipeline.analyze_stock()` 中，**在调用 `analyzer.analyze()` 之前**，系统已经准备好以下数据，并封装成 **`enhanced_context`** 和 **`news_context`** 两个对象：

### 1. 基础分析上下文 `context`（来自 `db.get_analysis_context(code)`）

| 字段 | 来源 | 含义 |
|------|------|------|
| `code` | 股票代码 | 如 600519、000001 |
| `date` | 当日 | 分析日期（ISO 格式） |
| `today` | 数据库最近一日 | 当日 K 线：open, high, low, close, volume, amount, pct_chg, ma5, ma10, ma20, volume_ratio, data_source |
| `yesterday` | 数据库前一日 | 昨日 K 线（同上结构） |
| `volume_change_ratio` | 计算 | 今日成交量 / 昨日成交量 |
| `price_change_ratio` | 计算 | 今日相对昨日涨跌幅（%） |
| `ma_status` | 计算 | 均线形态：多头/空头/缠绕 |

若没有历史数据，`context` 可能为 `data_missing: True`，且 `today`/`yesterday` 为空或占位。

### 2. 增强上下文 `_enhance_context()` 在 context 上追加的内容

| 追加字段 | 含义 |
|----------|------|
| `stock_name` | 股票中文名称（来自实时行情或参数） |
| `realtime` | **实时行情**：name, price, change_pct, volume_ratio, volume_ratio_desc, turnover_rate, pe_ratio, pb_ratio, total_mv, circ_mv, change_60d, source |
| `chip` | **筹码分布**：profit_ratio, avg_cost, concentration_90, concentration_70, chip_status |
| `trend_analysis` | **趋势分析结果**：trend_status, ma_alignment, trend_strength, bias_ma5, bias_ma10, volume_status, volume_trend, buy_signal, signal_score, signal_reasons, risk_factors |
| `today`（可能被覆盖） | 若有实时行情 + 趋势 MA，会用实时 OHLC + 趋势分析的 ma5/ma10/ma20 覆盖，便于盘中分析 |
| `ma_status` / `price_change_ratio` / `volume_change_ratio` | 基于实时价与昨日收盘等重算（若适用） |
| `is_index_etf` | 是否为指数/ETF（用于约束分析口径） |

### 3. 新闻上下文 `news_context`

- 来自 **搜索服务**（Tavily/SerpAPI/Brave/Bocha 等）对「股票代码 + 股票名称」的近期新闻检索结果。
- 字符串形式，通常包含标题、摘要、来源、链接等；若无结果则为空，分析模块仍会照常调用大模型。

因此，**在发给大模型之前，分析模块已经拿到的信息**包括：

- 股票代码、名称、分析日期  
- 今日/昨日 K 线及量价变化、均线、均线形态  
- 实时行情（价、量比、换手、PE/PB、市值、60 日涨跌幅等）  
- 筹码分布（获利比例、成本、集中度、筹码状态）  
- 趋势分析预判（趋势状态、均线排列、乖离率、量能、系统信号与理由）  
- 新闻舆情字符串（若有）  
- 是否指数/ETF、是否数据缺失  

这些全部体现在 **`enhanced_context` + `news_context`** 中，并作为 `analyzer.analyze(enhanced_context, news_context)` 的入参。

---

## 二、实际发送给大模型（Mother/LLM）的内容是什么？

分析器 **不会** 把上面的字典原样发给 API，而是用 **`_format_prompt(context, name, news_context)`** 把 `enhanced_context` 和 `news_context` 转成一段**纯文本 prompt**，再通过 LiteLLM 以 **单轮对话**（系统提示 + 用户 prompt）的形式发给大模型。

### 1. 发送形态

- **接口**：LiteLLM `completion(model=..., messages=[{role: "user", content: prompt}])`（系统提示在别处配置或拼在 prompt 中）。
- **内容**：一条长文本 = **格式化后的“决策仪表盘分析请求”**，结构如下。

### 2. Prompt 结构（发给模型的内容）

| 区块 | 内容 |
|------|------|
| **股票基础信息** | 股票代码、股票名称、分析日期 |
| **技术面数据** | 今日行情表：收盘/开盘/最高/最低、涨跌幅、成交量、成交额；均线系统表：MA5/MA10/MA20 数值、均线形态 |
| **实时行情增强** | 当前价、量比（含解读）、换手率、市盈率、市净率、总市值、流通市值、60 日涨跌幅 |
| **筹码分布** | 获利比例、平均成本、90%/70% 筹码集中度、筹码状态及健康标准说明 |
| **趋势分析预判** | 趋势状态、均线排列、趋势强度、乖离率(MA5/MA10)、量能状态、系统信号与评分、买入理由与风险因素列表 |
| **量价变化** | 成交量较昨日倍数、价格较昨日涨跌幅 |
| **舆情情报** | 若有 `news_context`：近 7 日新闻搜索结果全文（风险/利好/业绩等）；若无：说明未搜到新闻，以技术面为主 |
| **数据缺失警告** | 若 `context.data_missing` 为真：提醒忽略 N/A、严禁编造数据 |
| **分析任务与约束** | 指数/ETF 时的特殊约束（若有）；要求输出正确股票名称、决策仪表盘 JSON、核心结论、持仓建议、狙击点位、检查清单等 |

也就是说：**发给大模型的就是这一段格式化后的 prompt 文本**，里面已经包含了上面所有“会给分析模块的信息”的**人类可读版**（表格 + 列表 + 说明），而不是原始 JSON。

### 3. 总结对应关系

- **“在发送给大模型前，分析模块会得到什么？”**  
  → 得到 **`enhanced_context`**（含基础 context + 实时行情 + 筹码 + 趋势分析）和 **`news_context`**（新闻字符串）。

- **“应该把什么发给大模型？”**  
  → 当前实现是：**不直接发原始 context**，而是用 **`_format_prompt()` 生成的整段决策仪表盘分析请求文本**（含技术面、筹码、趋势、舆情、任务与约束）发给大模型；大模型只需根据这段 prompt 生成决策仪表盘 JSON。

若要修改“发给模型的内容”，只需在 **`src/analyzer.py`** 的 **`_format_prompt()`** 中增删或改写上述区块即可。

---

## 三、常规分析 vs 重组专项检索

### 常规分析（决策仪表盘）里的检索

**常规分析**（`pipeline.analyze_stock`）使用的多维度情报是 **`search_comprehensive_intel()`**，当前维度为：

| 维度 | 关键词示例（A 股） |
|------|-------------------|
| 最新消息 | 股票名 代码 最新 新闻 重大 事件 |
| 机构分析 | 股票名 研报 目标价 评级 深度分析 |
| 风险排查 | 股票名 减持 处罚 违规 诉讼 利空 风险 |
| 业绩预期 | 股票名 业绩预告 财报 营收 净利润 同比增长 |
| 行业分析 | 股票名 所在行业 竞争对手 市场份额 行业前景 |

**没有**单独以「重组」为目标的检索。重组相关资讯可能偶尔出现在「最新消息」或「风险排查」里，但不是定向检索。

### 重组专项检索（仅重组分析时使用）

系统**有**专门的重组检索接口 **`search_restructuring_intel()`**（`src/search_service.py`）：

- **用途**：为「重组路径与时间节点分析」提供数据源。
- **检索词**（A 股）：`股票名 代码 重组 资产重组 预案 筹划 过会 证监会 标的资产 交易对手 发行股份 资产置换`。
- **调用时机**：仅在执行**重组分析**时调用：
  - 命令行：`python main.py --restructuring --stocks 600519`
  - API：`POST /api/v1/restructuring/analyze`
- **流程**：`restructuring_service._gather_context()` → `search_svc.search_restructuring_intel()`，结果写入「数据源检索到的重组相关资讯」，再与用户录入的真实消息、历史摘要一起交给重组分析的 LLM。

因此：**常规的每日/单次决策仪表盘分析不会做重组定向检索**；只有跑重组分析时才会检索并利用重组相关资讯。若希望在常规分析里也带上一维「重组」情报，需要在 `search_comprehensive_intel` 的 `search_dimensions` 中增加重组维度，并在 `format_intel_report` 的展示顺序中加入该维度。
