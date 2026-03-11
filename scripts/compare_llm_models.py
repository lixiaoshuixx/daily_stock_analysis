#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compare output quality and length across multiple LLM models using the same prompt.
Usage: from project root, run:
  .venv/bin/python scripts/compare_llm_models.py

Uses a short prompt to minimize cost. Requires at least one API key (e.g. GEMINI_API_KEY)
configured in .env so that gemini/* models can be called.
"""

import os
import sys
from typing import Any, Dict, List, Optional

# Project root
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Same short prompt for every model (stock analysis style, minimal tokens)
TEST_PROMPT = """请用 2～3 句话分析贵州茅台(600519)当前技术面应关注的重点，并给出操作建议（买入/持有/观望）。"""

# Models to try (gemini/* use GEMINI_API_KEY; adjust if you use OpenAI/Anthropic)
MODELS_TO_COMPARE = [
    "gemini/gemini-2.0-flash",
    "gemini/gemini-2.5-flash",
    "gemini/gemini-1.5-flash",
    "gemini/gemini-1.5-pro",
    "gemini/gemini-2.0-flash-exp",
    "gemini/gemini-3-flash-preview",
    "gemini/gemini-3.1-pro-preview",
]


def run_one(
    analyzer: Any,
    model: str,
    prompt: str,
    max_tokens: int = 512,
    temperature: float = 0.3,
) -> Dict[str, Any]:
    """Call one model and return result dict with text, length, error."""
    out: Dict[str, Any] = {
        "model": model,
        "success": False,
        "text": "",
        "length": 0,
        "error": None,
    }
    try:
        text = analyzer._call_litellm(
            prompt,
            {"temperature": temperature, "max_tokens": max_tokens},
            model_override=model,
        )
        if text and isinstance(text, str):
            out["success"] = True
            out["text"] = text.strip()
            out["length"] = len(text)
        else:
            out["error"] = "Empty response"
    except Exception as e:
        out["error"] = str(e)
    return out


def main() -> None:
    from src.config import get_config
    from src.analyzer import GeminiAnalyzer

    config = get_config()
    if not config.litellm_model and not getattr(config, "gemini_api_key", None) and not getattr(config, "gemini_api_keys", None):
        print("未配置 LITELLM_MODEL 或 GEMINI_API_KEY，无法对比模型。请在 .env 中配置后重试。")
        sys.exit(1)

    analyzer = GeminiAnalyzer()
    if not analyzer.is_available():
        print("Analyzer 不可用（无有效 API Key 或 LITELLM_MODEL）。")
        sys.exit(1)

    print("=" * 60)
    print("同一提示词多模型输出对比")
    print("提示词:", TEST_PROMPT[:80], "...")
    print("=" * 60)

    results: List[Dict[str, Any]] = []
    for model in MODELS_TO_COMPARE:
        short_name = model.split("/")[-1]
        print(f"\n正在调用: {short_name} ...", end=" ", flush=True)
        r = run_one(analyzer, model, TEST_PROMPT)
        results.append(r)
        if r["success"]:
            print(f"OK (输出 {r['length']} 字)")
        else:
            print(f"失败: {r['error']}")

    # Summary table
    print("\n" + "=" * 60)
    print("对比汇总")
    print("=" * 60)
    print(f"{'模型':<35} {'状态':<8} {'字数':<8} {'内容摘要'}")
    print("-" * 100)
    for r in results:
        name = r["model"].split("/")[-1]
        status = "OK" if r["success"] else "失败"
        length = str(r["length"]) if r["success"] else "-"
        preview = (r["text"][:48] + "…") if r["success"] and len(r["text"]) > 48 else (r["text"] or r.get("error", "")[:48])
        print(f"{name:<35} {status:<8} {length:<8} {preview}")

    # Full responses
    print("\n" + "=" * 60)
    print("各模型完整输出")
    print("=" * 60)
    for r in results:
        name = r["model"].split("/")[-1]
        print(f"\n--- {name} ---")
        if r["success"]:
            print(r["text"])
        else:
            print(f"(失败) {r.get('error')}")

    success_count = sum(1 for r in results if r["success"])
    print(f"\n完成: {success_count}/{len(results)} 个模型调用成功。")


if __name__ == "__main__":
    main()
