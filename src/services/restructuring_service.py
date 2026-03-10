# -*- coding: utf-8 -*-
"""
Restructuring (reorganization) analysis service.

Two modules:
- Data preparation: announcement directory -> LLM filter (primary model) -> fetch full text -> strip legal noise;
  plus general info (search intel, user ground truth, recent summary). Output: context text and optional report file.
- Restructuring analysis: call LLM on the context to infer path summary and timeline nodes. Uses
  LITELLM_RESTRUCTURING_MODEL when set (for long context), otherwise primary model (LITELLM_MODEL).

Run analysis for a stock code: run data prep, then optionally analysis LLM, save result. Load previous
analyses and user ground truth so next run can use them.
"""

import json
import logging
import re
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import pandas as pd

from src.config import get_config
from src.storage import get_db

logger = logging.getLogger(__name__)

# Max announcements to send to LLM for filtering (directory size)
ANNOUNCEMENT_DIRECTORY_MAX_ROWS = 150
# Request timeout and delay for cninfo fetch (seconds)
ANNOUNCEMENT_FETCH_TIMEOUT = 15
ANNOUNCEMENT_FETCH_DELAY = 1.0


def _export_announcement_directory(code: str, df: pd.DataFrame, days_label: str = "2year") -> None:
    """Export full announcement directory to reports/{code}_announcements_{days_label}.txt."""
    try:
        reports_dir = Path("reports")
        reports_dir.mkdir(parents=True, exist_ok=True)
        out_file = reports_dir / f"{code}_announcements_{days_label}.txt"
        col_date = "公告时间" if "公告时间" in df.columns else df.columns[1]
        col_title = "公告标题" if "公告标题" in df.columns else df.columns[2]
        col_link = "公告链接" if "公告链接" in df.columns else (df.columns[3] if len(df.columns) > 3 else None)
        lines = ["序号\t公告日期\t公告标题\t公告链接"]
        for i in range(len(df)):
            row = df.iloc[i]
            d = str(row.get(col_date, ""))[:10]
            t = str(row.get(col_title, ""))
            link = str(row.get(col_link, "")) if col_link else ""
            lines.append(f"{i}\t{d}\t{t}\t{link}")
        out_file.write_text("\n".join(lines), encoding="utf-8")
        logger.info("Announcement directory exported to %s (%d items)", out_file, len(df))
    except Exception as e:
        logger.debug("Could not export announcement directory: %s", e)


def _get_announcement_list(code: str, days: int = 730) -> Optional[pd.DataFrame]:
    """Get A-share announcement directory from CNINFO (last N days). Returns None for non-A-share."""
    code = (code or "").strip()
    if not code.isdigit() or len(code) > 6:
        return None
    try:
        from data_provider.base import DataFetcherManager
        manager = DataFetcherManager()
        df = manager.get_stock_announcements(code, days=days)
        if df is not None and not df.empty:
            return df
    except Exception as e:
        logger.warning("Get announcement list failed: %s", e)
    return None


def _llm_filter_restructuring_announcements(
    code: str, name: str, df: pd.DataFrame
) -> List[int]:
    """
    Send announcement directory to LLM; return list of row indices (0-based) that are restructuring-related.
    """
    # Build directory text: one line per row with index, date, title
    col_date = "公告时间" if "公告时间" in df.columns else df.columns[1]
    col_title = "公告标题" if "公告标题" in df.columns else df.columns[2]
    lines = []
    n = min(len(df), ANNOUNCEMENT_DIRECTORY_MAX_ROWS)
    for i in range(n):
        row = df.iloc[i]
        d = str(row.get(col_date, ""))[:10]
        t = str(row.get(col_title, ""))[:120]
        lines.append(f"{i}\t{d}\t{t}")
    directory_text = "\n".join(lines)

    prompt = f"""你正在为股票 {name}({code}) 做重组相关公告筛选。请按以下步骤执行，且 (2)(3)(4)(5)(6)(7) 六类必须逐一筛查、全部纳入，不要遗漏：

(1) 在互联网上搜索「{name} ({code}) 重组」、「{name} 股权变动」、「{name} 资产注入」相关的最新新闻、深度分析报告和市场传闻，获取背景信息（可结合你已有知识）。

(2) 仔细审阅下列公告目录（来自 {code}_announcements_2year.txt，格式：序号\\t公告日期\\t公告标题），筛选出涉及「权益变动」、「协议转让」、「股份过户」、「受让方」、「转让方」等直接股权变动的公告序号。

(3) 筛选出涉及「重大合同」「重大项目」「订单落地」「签署合同」「项目中标」「项目成交」「自愿性披露」「预中选」等可能暗示业务重大调整或资产质量变化的公告序号。只要标题中出现上述任一关键词，其序号必须列入输出。

(4) 筛选出涉及「股份回购」「减持股份」及回购相关全链条的公告序号，包括但不限于：回购进展、回购报告书、回购方案、提议回购、首次回购、前十大股东（与回购事项相关的）。只要标题中出现上述任一关键词，其序号必须列入输出。

(5) 筛选出涉及「对外投资」「子公司设立」「设立子公司」「授信」「综合授信」「资本运作」「融资」「业务调整」「经营范围变更」「战略」等授信与资本运作保障、业务调整相关的公告序号。只要标题中出现上述任一关键词，其序号必须列入输出。

(6) 筛选出涉及「权益分派」「利润分配」「资本公积转增」「转增股本」「预案」「关联交易」「日常关联交易」「董事会决议」「会议决议」等权益分派与股本扩张、关联交易及战略审议相关的公告序号。只要标题中出现上述任一关键词，其序号必须列入输出。

(7) 筛选出涉及「公司章程修订」「治理制度修订」「变更注册资本」「董事会/监事会换届」等治理层面可能配合重组动作的公告序号。

(8) 将 (2)(3)(4)(5)(6)(7) 筛选出的所有序号去重合并，并简要说明每组序号与重组的潜在关联。

【输出格式】
第一行：仅输出筛选出的公告序号，用英文逗号分隔；若没有任何相关公告则输出：无。
示例：2,5,8,12,16,19,23
自第二行起：可简要说明每组序号与重组的潜在关联（可选）。

公告目录：
{directory_text}

请按上述格式回复，第一行为序号："""

    try:
        from src.analyzer import GeminiAnalyzer
        analyzer = GeminiAnalyzer()
        if not analyzer.is_available():
            return []
        response = analyzer._call_litellm(prompt, {"temperature": 0.1, "max_tokens": 1024})
        if not response:
            return []
        text = response.strip().split("\n")[0].strip()
        if "无" in text or not text:
            return []
        indices = []
        for part in text.replace("，", ",").split(","):
            part = part.strip()
            if part.isdigit():
                idx = int(part)
                if 0 <= idx < n:
                    indices.append(idx)
        return list(dict.fromkeys(indices))
    except Exception as e:
        logger.warning("LLM filter restructuring announcements failed: %s", e)
        return []


def _extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract plain text from PDF bytes. Returns empty string on failure."""
    if not pdf_bytes or pdf_bytes[:5] != b"%PDF-":
        return ""
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        parts = []
        for page in doc:
            parts.append(page.get_text())
        doc.close()
        text = "\n".join(parts).strip()
        text = re.sub(r"\s+", " ", text)
        if len(text) > 12000:
            text = text[:12000] + "..."
        return text or ""
    except Exception as e:
        logger.debug("PDF text extraction failed: %s", e)
        return ""


def _pdf_url_from_cninfo_detail(detail_url: str) -> Optional[str]:
    """
    Get static PDF URL from cninfo detail page URL.
    Detail URL format: ...?announcementId=1224902197&...&announcementTime=2025-12-27
    PDF URL format: https://static.cninfo.com.cn/finalpage/2025-12-27/1224902197.PDF
    """
    try:
        parsed = urlparse(detail_url)
        qs = parse_qs(parsed.query)
        aid = (qs.get("announcementId") or [None])[0]
        time_str = (qs.get("announcementTime") or [None])[0]
        if aid and time_str:
            return f"https://static.cninfo.com.cn/finalpage/{time_str}/{aid}.PDF"
    except Exception:
        pass
    return None


def _fetch_announcement_content(url: str) -> str:
    """
    Fetch announcement content from cninfo: detail page (HTML) or static PDF.
    When the detail page is a PDF placeholder, downloads the PDF and extracts text.
    Returns empty string on failure.
    """
    if not url or "cninfo.com.cn" not in url:
        return ""
    try:
        import requests
        from fake_useragent import UserAgent
        ua = UserAgent()
        headers = {"User-Agent": ua.random}
        resp = requests.get(url, headers=headers, timeout=ANNOUNCEMENT_FETCH_TIMEOUT)
        resp.raise_for_status()
        body = resp.content
        content_type = (resp.headers.get("Content-Type") or "").lower()

        # Direct PDF response: extract text
        if "application/pdf" in content_type or body[:5] == b"%PDF-":
            text = _extract_text_from_pdf(body)
            if text:
                return text
            return ""

        # HTML response
        resp.encoding = resp.apparent_encoding or "utf-8"
        html = resp.text
        text = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", html, flags=re.I)
        text = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", text, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

        # If page is PDF placeholder (little useful text, or "下载PDF" / template), try static PDF
        pdf_url = None
        is_placeholder = (
            len(text) < 300
            or "下载PDF" in html
            or "不支持在线预览" in text
            or ("{{" in text and "巨潮" in text)
        )
        if is_placeholder:
            # Try to find PDF link in HTML
            match = re.search(
                r"https?://static\.cninfo\.com\.cn/finalpage/[^\s\"']+\.PDF",
                html,
                re.I,
            )
            if match:
                pdf_url = match.group(0)
            if not pdf_url:
                pdf_url = _pdf_url_from_cninfo_detail(url)
        if pdf_url:
            pdf_resp = requests.get(pdf_url, headers=headers, timeout=ANNOUNCEMENT_FETCH_TIMEOUT)
            if pdf_resp.status_code == 200 and pdf_resp.content[:5] == b"%PDF-":
                pdf_text = _extract_text_from_pdf(pdf_resp.content)
                if pdf_text:
                    return pdf_text

        if len(text) > 12000:
            text = text[:12000] + "..."
        return text or ""
    except Exception as e:
        logger.debug("Fetch announcement content failed %s: %s", url[:60], e)
        return ""


def _strip_legal_noise(text: str) -> str:
    """
    Remove redundant legal boilerplate from announcement text to reduce token noise for LLM.
    - Repeated identity: 统一社会信用代码, full 注册地址/通讯地址 (keep once per entity if needed, here we strip).
    - Compliance boilerplate: 不触及要约收购, 不存在违反《证券法》等.
    - Contact/procedural: 登记电话, 传真, 门牌号, 具体地址.
    """
    if not text or len(text) < 100:
        return text
    # Work on lines to avoid breaking structure; then rejoin
    lines = text.split("\n")
    out = []
    for line in lines:
        s = line.strip()
        if not s:
            out.append(line)
            continue
        # Remove lines that are purely 统一社会信用代码 + code
        if re.search(r"统一社会信用代码\s*[：:]\s*[0-9A-Z]{18}", s) and len(s) < 60:
            continue
        # Remove lines that are purely 注册地址/通讯地址 + long detail (keep short ones)
        if re.match(r"^(注册地|通讯地址|住所)[址及]*\s*[：:]\s*", s) and len(s) > 40:
            out.append(re.sub(r"((注册地|通讯地址|住所)[址及]*\s*[：:])\s*.+", r"\1[已省略]", s))
            continue
        # Remove compliance boilerplate sentences (within line)
        s = re.sub(r"本次(权益变动|转让|交易|协议转让).*?不触及要约收购[^。]*。?", "", s)
        s = re.sub(r"不存在违反\s*《[^》]+》\s*.*?情形[^。]*。?", "", s)
        s = re.sub(r"不构成\s*要约收购[^。]*。?", "", s)
        s = re.sub(r"符合\s*《[^》]+》\s*.*?规定[^。]*。?", "", s)
        # Remove contact/procedural lines: 登记电话, 传真, 门牌号
        if re.search(r"登记(电话|方式|时间|地点)\s*[：:]", s) and len(s) > 30:
            continue
        if re.search(r"传真\s*[：:]\s*[0-9\-]+", s) and len(s) < 80:
            continue
        if re.search(r"门牌号|具体门牌|传真号码", s) and len(s) < 100:
            continue
        # Remove lines that are only ID number (18 digits)
        if re.match(r"^\d{18}$", re.sub(r"\s", "", s)):
            continue
        s = re.sub(r"\s+", " ", s).strip()
        if s:
            out.append(s)
    result = "\n".join(out)
    # Collapse multiple blank lines
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def _gather_announcement_context(code: str, name: str, days: int = 730) -> str:
    """
    Data preparation module: announcement list -> LLM filter (primary model) -> fetch full content
    -> strip legal noise -> merge. Returns a single section text to be inserted into restructuring context.
    """
    df = _get_announcement_list(code, days=days)
    if df is None or df.empty:
        return ""

    _export_announcement_directory(code, df, days_label="2year")

    indices = _llm_filter_restructuring_announcements(code, name, df)
    # Force-include announcements whose title matches major project/order keywords (must list)
    col_title = "公告标题" if "公告标题" in df.columns else df.columns[2]
    n = min(len(df), ANNOUNCEMENT_DIRECTORY_MAX_ROWS)
    _must_include_keywords = (
        "重大合同",
        "重大项目",
        "订单落地",
        "项目中标",
        "项目成交",
        "自愿性披露",
        "预中选",
        "签署合同",
        "对外投资",
        "子公司",
        "授信",
        "资本运作",
        "业务调整",
        "经营范围",
        "融资",
        "股份回购",
        "回购进展",
        "回购报告书",
        "回购方案",
        "提议回购",
        "前十大股东",
        "权益分派",
        "利润分配",
        "资本公积转增",
        "转增股本",
        "预案",
        "关联交易",
        "董事会决议",
        "会议决议",
        "变更注册资本",
        "章程",
    )
    # Scan full directory for keyword match so that rows beyond ANNOUNCEMENT_DIRECTORY_MAX_ROWS are still included
    for i in range(len(df)):
        t = str(df.iloc[i].get(col_title, ""))
        if any(k in t for k in _must_include_keywords):
            indices.append(i)
    indices = list(dict.fromkeys(indices))

    if not indices:
        return ""

    col_date = "公告时间" if "公告时间" in df.columns else df.columns[1]
    col_title = "公告标题" if "公告标题" in df.columns else df.columns[2]
    col_link = "公告链接" if "公告链接" in df.columns else (df.columns[3] if len(df.columns) > 3 else None)

    parts = ["## 公告目录中识别出的重组相关公告（全文/摘要）\n"]
    for i in indices:
        if i >= len(df):
            continue
        row = df.iloc[i]
        d = str(row.get(col_date, ""))[:10]
        t = str(row.get(col_title, ""))
        link = str(row.get(col_link, "")) if col_link else ""
        parts.append(f"### [{d}] {t}")
        parts.append(f"链接: {link}")
        raw = _fetch_announcement_content(link) if link else ""
        content = _strip_legal_noise(raw) if raw else ""
        if content:
            parts.append(content)
        else:
            parts.append("（正文获取失败，请通过链接查看）")
        parts.append("")
        time.sleep(ANNOUNCEMENT_FETCH_DELAY)

    return "\n".join(parts)


def _gather_context(code: str, name: Optional[str]) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Gather context for restructuring: announcement info (directory + LLM filter + fetch full text)
    and general info (search, ground truth, recent summary). Both are merged and sent together
    to the LLM for path/timeline analysis.
    Returns (context_text, timeline_suggestions from ground truth).
    """
    db = get_db()
    timeline_from_truth: List[Dict[str, Any]] = []
    display_name = name or code

    # --- 一、重组相关公告信息（公告目录筛选 + 正文抓取）---
    announcement_parts: List[str] = []
    use_announcements = getattr(get_config(), "restructuring_use_announcements", True)
    if use_announcements and code.strip().isdigit() and len(code.strip()) <= 6:
        try:
            ann_ctx = _gather_announcement_context(code, display_name, days=730)
            if ann_ctx:
                announcement_parts.append(ann_ctx)
        except Exception as e:
            logger.warning("Gather announcement context failed: %s", e)
    announcement_section = "\n".join(announcement_parts) if announcement_parts else "（暂无：未启用公告或筛选无结果）"

    # --- 二、通用信息（检索资讯、用户录入、历史摘要）---
    general_parts: List[str] = []

    # 2.1 Data-source retrieval: search for restructuring-related info
    try:
        from src.search_service import get_search_service
        search_svc = get_search_service()
        if getattr(search_svc, "is_available", False):
            response = search_svc.search_restructuring_intel(
                stock_code=code,
                stock_name=display_name,
                max_results=10,
                search_days=30,
            )
            if response.success and response.results:
                general_parts.append("### 数据源检索到的重组相关资讯\n")
                general_parts.append(response.to_context(max_results=10))
                general_parts.append("")
        else:
            logger.debug("Search service not available, skip restructuring intel search")
    except Exception as e:
        logger.warning("Restructuring intel search failed: %s", e)

    # 2.2 User ground truth
    truths = db.get_restructuring_ground_truth(code=code, limit=50)
    if truths:
        general_parts.append("### 用户提供的真实消息与时间点\n")
        for t in truths:
            general_parts.append(f"- {t['content']}")
            if t.get("event_date"):
                general_parts.append(f"  时间: {t['event_date']}")
            if t.get("source"):
                general_parts.append(f"  来源: {t['source']}")
            timeline_from_truth.append({
                "event_type": "user_fact",
                "event_date": t.get("event_date"),
                "description": t["content"],
                "source": t.get("source") or "user",
                "verified_by_user": True,
            })
        general_parts.append("")

    # 2.3 Recent analysis history summary
    try:
        from src.storage import AnalysisHistory
        from sqlalchemy import select, desc
        with db.get_session() as session:
            row = session.execute(
                select(AnalysisHistory)
                .where(AnalysisHistory.code == code)
                .order_by(desc(AnalysisHistory.created_at))
                .limit(1)
            ).scalar_one_or_none()
            if row and getattr(row, "analysis_summary", None):
                general_parts.append("### 最近一次综合分析摘要\n")
                general_parts.append(row.analysis_summary[:2000] if row.analysis_summary else "")
                general_parts.append("")
    except Exception as e:
        logger.debug("Could not load analysis_history for context: %s", e)

    general_section = "\n".join(general_parts) if general_parts else "（暂无检索结果、用户消息或历史摘要）"

    # Merge: 公告信息 + 通用信息，一起发给大模型
    context_text = (
        "一、重组相关公告信息（来自公告目录筛选与正文抓取）\n\n"
        f"{announcement_section}\n\n"
        "二、通用信息（检索资讯、用户录入、历史摘要）\n\n"
        f"{general_section}"
    )
    return context_text, timeline_from_truth


def _call_llm_for_path(code: str, name: str, context_text: str) -> Tuple[Optional[str], Optional[str], List[Dict[str, Any]]]:
    """
    Restructuring analysis module: call LLM to generate path summary and timeline nodes.
    Uses LITELLM_RESTRUCTURING_MODEL when set (for long context), otherwise primary model.
    Returns (summary, path_description, timeline_nodes).
    """
    config = get_config()
    has_llm = bool(config.litellm_model) or bool(
        getattr(config, "openai_api_keys", None)
        or getattr(config, "anthropic_api_keys", None)
    )
    if not has_llm:
        return None, None, []

    # Prefer restructuring-specific model (larger context) when configured
    model_override = getattr(config, "litellm_restructuring_model", "") or ""

    prompt = f"""你是一位A股并购重组分析助手。请根据下面关于股票 {name}({code}) 的已知信息，梳理其重组的路径与关键时间节点。

已知信息分为两部分，请综合以下全部信息一起分析：
- 一、重组相关公告信息：来自近两年公告目录经模型筛选后的重组相关公告（标题、日期、链接及可用的正文/摘要），请优先从中提炼重组类型、交易对手方、标的资产、筹划/预案/过会/核准等进展与日期。
- 二、通用信息：数据源检索到的重组相关资讯、用户录入的真实消息与时间点、最近一次综合分析摘要。

请将上述公告信息与通用信息结合，补全 path_description 与 timeline。

已知信息：
{context_text}

请按以下要求输出（严格使用JSON，不要其他说明）：
{{
  "summary": "一段话概括该股重组路径与当前阶段（50-200字）。若信息不足无法描绘详细路径，必须在 summary 中明确写出：目前缺乏哪些具体信息（如：重组类型、交易对手方、标的资产、以及筹划/预案/股东大会/监管审批等环节的进展），并提示用户可在本系统「录入真实信息」中补充上述内容后再重新分析。",
  "path_description": "分步骤描述重组路径与重要节点（可多段）；若信息不足则简要说明已掌握的点与缺失环节。",
  "timeline": [
    {{ "event_type": "事件类型如：筹划公告/预案/过会/核准/实施", "event_date": "YYYY-MM-DD或null", "description": "简短描述" }}
  ]
}}
若信息不足以推断时间节点，timeline 可为空数组；若有明确日期请填入 event_date。只输出一个JSON块。"""

    try:
        from src.analyzer import GeminiAnalyzer
        analyzer = GeminiAnalyzer()
        if not analyzer.is_available():
            return None, None, []
        response = analyzer._call_litellm(
            prompt,
            {"temperature": 0.3, "max_tokens": 4096},
            model_override=model_override if model_override else None,
        )
        if not response:
            return None, None, []

        # Parse JSON from response (allow markdown code block)
        text = response.strip()
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if m:
            text = m.group(1).strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Fallback: treat whole response as summary
            return text[:2000], None, []
        summary = data.get("summary") or ""
        path_desc = data.get("path_description") or ""
        timeline = data.get("timeline") or []
        nodes = []
        for t in timeline:
            ed = t.get("event_date")
            if isinstance(ed, str) and ed:
                try:
                    ed = datetime.strptime(ed[:10], "%Y-%m-%d").date()
                except Exception:
                    ed = None
            else:
                ed = None
            nodes.append({
                "event_type": t.get("event_type") or "unknown",
                "event_date": ed,
                "description": t.get("description") or "",
                "source": "llm",
                "verified_by_user": False,
            })
        return summary, path_desc, nodes
    except Exception as e:
        logger.warning("LLM restructuring analysis failed: %s", e)
        return None, None, []


def run_restructuring_analysis(
    code: str,
    name: Optional[str] = None,
    use_llm: bool = True,
    keep_latest_only: bool = False,
) -> Dict[str, Any]:
    """
    Run one restructuring analysis for the given stock code.
    Loads ground truth and prior context, optionally calls LLM, saves result and returns it.
    If keep_latest_only is True, prunes history for this code to only the new record.
    """
    code = (code or "").strip().upper()
    if not code:
        return {"success": False, "error": "stock code required"}

    db = get_db()
    if not name:
        try:
            from data_provider.base import DataFetcherManager
            name = DataFetcherManager().get_stock_name(code) or code
        except Exception:
            name = code

    context_text, timeline_from_truth = _gather_context(code, name)

    # Dump context sent to LLM to reports/ for inspection
    try:
        reports_dir = Path("reports")
        reports_dir.mkdir(parents=True, exist_ok=True)
        out_file = reports_dir / f"{code}_restructuring_context.txt"
        out_file.write_text(context_text, encoding="utf-8")
        logger.info("Restructuring context written to %s (%d chars)", out_file, len(context_text))
    except Exception as e:
        logger.debug("Could not write restructuring context to file: %s", e)

    summary = None
    path_description = None
    timeline_nodes: List[Dict[str, Any]] = list(timeline_from_truth)

    if use_llm:
        summary, path_description, llm_nodes = _call_llm_for_path(code, name, context_text)
        if llm_nodes:
            timeline_nodes = timeline_nodes + llm_nodes
    if not summary and len(context_text) > 400:
        summary = f"已录入信息汇总：{context_text[:500]}..."
    if not summary:
        summary = f"{name}({code}) 暂无重组路径分析结果，请先添加真实消息与时间点后再分析。"

    analysis_id = db.save_restructuring_analysis(
        code=code,
        name=name,
        summary=summary,
        path_description=path_description,
        raw_context=context_text[:10000],
        timeline_nodes=timeline_nodes,
    )
    if keep_latest_only:
        try:
            deleted = db.prune_restructuring_analyses_for_code(code, keep_per_code=1)
            if deleted:
                logger.info("Restructuring history: kept only latest for %s, removed %d old record(s)", code, deleted)
        except Exception as e:
            logger.debug("Restructuring prune (keep latest only) failed (non-fatal): %s", e)
    else:
        try:
            deleted = db.prune_restructuring_analyses_keep_latest_per_code(keep_per_code=10)
            if deleted:
                logger.info("Restructuring history pruned: %d old record(s) removed for %s", deleted, code)
        except Exception as e:
            logger.debug("Restructuring prune failed (non-fatal): %s", e)
    result = db.get_restructuring_analysis_with_timeline(analysis_id)
    return {"success": True, "analysis_id": analysis_id, "result": result}


def run_restructuring_data_prep_only(
    code: str,
    name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Data preparation only: gather context (announcement filter + fetch + strip noise + general info)
    and write to reports/{code}_restructuring_context.txt. No path analysis LLM, no DB save.
    Returns {"success": True, "message": "上下文已更新"} or {"success": False, "error": "..."}.
    """
    code = (code or "").strip().upper()
    if not code:
        return {"success": False, "error": "stock code required"}

    if not name:
        try:
            from data_provider.base import DataFetcherManager
            name = DataFetcherManager().get_stock_name(code) or code
        except Exception:
            name = code

    try:
        context_text, _ = _gather_context(code, name)
        reports_dir = Path("reports")
        reports_dir.mkdir(parents=True, exist_ok=True)
        out_file = reports_dir / f"{code}_restructuring_context.txt"
        out_file.write_text(context_text, encoding="utf-8")
        logger.info("Restructuring context written to %s (%d chars)", out_file, len(context_text))
        prepared_at = datetime.now().isoformat()
        return {"success": True, "message": "上下文已更新", "prepared_at": prepared_at}
    except Exception as e:
        logger.warning("Restructuring data prep failed: %s", e)
        return {"success": False, "error": str(e)}

