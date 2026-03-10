import type React from 'react';
import { useState, useEffect, useCallback, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { restructuringApi } from '../api/restructuring';
import { stocksApi } from '../api/stocks';
import { systemConfigApi } from '../api/systemConfig';
import { Card, Button } from '../components/common';

// Module-level cache so names survive route switches; keyed by code -> name
let watchlistNamesCache: Record<string, string> = {};
import type {
  RestructuringAnalysisOut,
  RestructuringAnalysisListItem,
  RestructuringGroundTruthOut,
  TimelineNodeOut,
} from '../types/restructuring';

/** Format ISO8601 to YYYY-MM-DD HH:mm for display */
function formatPrepareDate(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    const h = String(d.getHours()).padStart(2, '0');
    const min = String(d.getMinutes()).padStart(2, '0');
    return `${y}-${m}-${day} ${h}:${min}`;
  } catch {
    return iso;
  }
}

// ============ Analysis result display ============

const ResultCard: React.FC<{
  result: RestructuringAnalysisOut | null;
  isLoading: boolean;
}> = ({ result, isLoading }) => {
  if (isLoading) {
    return (
      <Card variant="bordered" padding="md" className="flex flex-col items-center justify-center min-h-[200px]">
        <div className="w-8 h-8 border-2 border-cyan/20 border-t-cyan rounded-full animate-spin" />
        <p className="mt-3 text-sm text-secondary">分析中…</p>
      </Card>
    );
  }
  if (!result) {
    return (
      <Card variant="bordered" padding="md">
        <p className="text-sm text-muted text-center py-6">输入股票代码并点击「运行分析」查看结果</p>
      </Card>
    );
  }
  return (
    <Card variant="gradient" padding="md" className="animate-fade-in">
      <div className="mb-3 flex items-center justify-between">
        <span className="label-uppercase">分析结果</span>
        <span className="text-xs font-mono text-cyan">{result.code} {result.name || ''}</span>
      </div>
      {result.summary && (
        <div className="mb-4">
          <p className="text-xs text-secondary mb-1">摘要</p>
          <p className="text-sm text-white leading-relaxed">{result.summary}</p>
        </div>
      )}
      {result.pathDescription && (
        <div className="mb-4">
          <p className="text-xs text-secondary mb-1">路径描述</p>
          <p className="text-sm text-white whitespace-pre-wrap leading-relaxed">{result.pathDescription}</p>
        </div>
      )}
      {result.timeline && result.timeline.length > 0 && (
        <div>
          <p className="text-xs text-secondary mb-2">时间线</p>
          <ul className="space-y-2">
            {result.timeline.map((node: TimelineNodeOut, idx: number) => (
              <li key={node.id ?? idx} className="flex gap-2 text-sm border-b border-white/5 pb-2 last:border-0">
                <span className="text-muted font-mono shrink-0 w-24">{node.eventDate || '--'}</span>
                <span className={node.verifiedByUser ? 'text-cyan' : 'text-secondary'}>
                  {node.description || node.eventType || '--'}
                  {node.verifiedByUser && <span className="ml-1 text-cyan/80">(已核实)</span>}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {result.createdAt && (
        <p className="mt-3 text-xs text-muted">分析时间：{result.createdAt}</p>
      )}
    </Card>
  );
};

// ============ Main page ============

const RestructuringPage: React.FC = () => {
  const location = useLocation();
  const [stockCode, setStockCode] = useState('');
  const [watchlistCodes, setWatchlistCodes] = useState<string[]>([]);
  const [watchlistNames, setWatchlistNames] = useState<Record<string, string>>(() => ({ ...watchlistNamesCache }));
  const [isLoadingWatchlist, setIsLoadingWatchlist] = useState(false);
  const watchlistEffectIdRef = useRef(0);
  const [useLlm, setUseLlm] = useState(true);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);
  const [isPreparing, setIsPreparing] = useState(false);
  const [prepareMessage, setPrepareMessage] = useState<string | null>(null);
  const [prepareError, setPrepareError] = useState<string | null>(null);
  const [preparedAt, setPreparedAt] = useState<string | null>(null);
  const [isLoadingPrepareInfo, setIsLoadingPrepareInfo] = useState(false);

  const [currentResult, setCurrentResult] = useState<RestructuringAnalysisOut | null>(null);
  const [isLoadingResult, setIsLoadingResult] = useState(false);

  const [historyList, setHistoryList] = useState<RestructuringAnalysisListItem[]>([]);
  const [historyFilter, setHistoryFilter] = useState('');
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);

  const [groundTruthList, setGroundTruthList] = useState<RestructuringGroundTruthOut[]>([]);
  const [gtFilter, setGtFilter] = useState('');
  const [isLoadingGt, setIsLoadingGt] = useState(false);

  const [gtForm, setGtForm] = useState({ code: '', content: '', eventDate: '', source: '' });
  const [isAddingGt, setIsAddingGt] = useState(false);
  const [gtAddError, setGtAddError] = useState<string | null>(null);

  const fetchHistory = useCallback(async (codeFilter?: string) => {
    setIsLoadingHistory(true);
    try {
      const items = await restructuringApi.getHistory({
        code: codeFilter?.trim() || undefined,
        limit: 50,
      });
      setHistoryList(items);
    } catch (err) {
      console.error('Failed to fetch restructuring history:', err);
    } finally {
      setIsLoadingHistory(false);
    }
  }, []);

  const fetchGroundTruth = useCallback(async (codeFilter?: string) => {
    setIsLoadingGt(true);
    try {
      const items = await restructuringApi.getGroundTruth({
        code: codeFilter?.trim() || undefined,
        limit: 200,
      });
      setGroundTruthList(items);
    } catch (err) {
      console.error('Failed to fetch ground truth:', err);
    } finally {
      setIsLoadingGt(false);
    }
  }, []);

  const fetchPrepareInfo = useCallback(async (code: string) => {
    if (!code.trim()) return;
    setIsLoadingPrepareInfo(true);
    try {
      const info = await restructuringApi.getPrepareInfo(code);
      setPreparedAt(info.preparedAt ?? null);
    } catch (err) {
      console.error('Failed to fetch prepare info:', err);
      setPreparedAt(null);
    } finally {
      setIsLoadingPrepareInfo(false);
    }
  }, []);

  // When selected stock changes: filter history and ground truth by that stock, sync form and filters, fetch prepare info
  useEffect(() => {
    const code = stockCode.trim().toUpperCase();
    if (code) {
      setHistoryFilter(code);
      setGtFilter(code);
      setGtForm((prev) => ({ ...prev, code }));
      fetchHistory(code);
      fetchGroundTruth(code);
      fetchPrepareInfo(code);
    } else {
      setHistoryFilter('');
      setGtFilter('');
      fetchHistory();
      fetchGroundTruth();
      setPreparedAt(null);
    }
  }, [stockCode, fetchHistory, fetchGroundTruth, fetchPrepareInfo]);

  // Load watchlist (STOCK_LIST) and names when entering this page; cache names so they persist across route switches
  useEffect(() => {
    if (location.pathname !== '/restructuring') return;
    const effectId = ++watchlistEffectIdRef.current;
    let cancelled = false;
    setIsLoadingWatchlist(true);
    systemConfigApi
      .getConfig(false)
      .then((res) => {
        if (cancelled) return;
        const item = res.items?.find((i) => i.key === 'STOCK_LIST');
        const raw = (item?.value ?? '').trim();
        const codes = raw
          ? raw.split(/[,，\s]+/).map((c) => c.trim().toUpperCase()).filter(Boolean)
          : [];
        setWatchlistCodes(codes);
        // Prime from cache so dropdown shows names immediately after route switch
        const fromCache: Record<string, string> = {};
        codes.forEach((c) => {
          if (watchlistNamesCache[c]) fromCache[c] = watchlistNamesCache[c];
        });
        if (Object.keys(fromCache).length > 0) setWatchlistNames((prev) => ({ ...prev, ...fromCache }));
        if (codes.length > 0) {
          stocksApi.getNames(codes).then((names) => {
            if (cancelled || effectId !== watchlistEffectIdRef.current) return;
            Object.assign(watchlistNamesCache, names);
            setWatchlistNames(names);
          }).catch(() => {
            if (!cancelled) setWatchlistNames((prev) => ({ ...prev }));
          });
        } else {
          setWatchlistNames({});
        }
      })
      .catch(() => {
        if (!cancelled) setWatchlistCodes([]);
      })
      .finally(() => {
        if (!cancelled) setIsLoadingWatchlist(false);
      });
    return () => {
      cancelled = true;
    };
  }, [location.pathname]);

  const handleAnalyze = async () => {
    const code = stockCode.trim().toUpperCase();
    if (!code) {
      setAnalyzeError('请输入股票代码');
      return;
    }
    setAnalyzeError(null);
    setIsAnalyzing(true);
    setCurrentResult(null);
    try {
      const res = await restructuringApi.analyze({ code, useLlm });
      if (res.success && res.result) {
        setCurrentResult(res.result);
        fetchHistory(code);
      } else {
        setAnalyzeError('分析未返回结果');
      }
    } catch (err) {
      setAnalyzeError(err instanceof Error ? err.message : '分析失败');
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handlePrepare = async () => {
    const code = stockCode.trim().toUpperCase();
    if (!code) {
      setPrepareError('请输入股票代码');
      return;
    }
    setPrepareError(null);
    setPrepareMessage(null);
    setIsPreparing(true);
    try {
      const res = await restructuringApi.prepare({ code });
      if (res.success) {
        setPrepareMessage(res.message ?? '上下文已更新');
        setPreparedAt(res.preparedAt ?? null);
        setTimeout(() => setPrepareMessage(null), 4000);
      } else {
        setPrepareError(res.error ?? '数据准备失败');
      }
    } catch (err) {
      setPrepareError(err instanceof Error ? err.message : '数据准备失败');
    } finally {
      setIsPreparing(false);
    }
  };

  const handleLoadResult = async (analysisId: number) => {
    setIsLoadingResult(true);
    try {
      const result = await restructuringApi.getResult(analysisId);
      setCurrentResult(result ?? null);
    } catch (err) {
      console.error('Failed to load result:', err);
    } finally {
      setIsLoadingResult(false);
    }
  };

  const handleAddGroundTruth = async (e: React.FormEvent) => {
    e.preventDefault();
    const code = gtForm.code.trim().toUpperCase();
    const content = gtForm.content.trim();
    if (!code || !content) {
      setGtAddError('股票代码和内容必填');
      return;
    }
    setGtAddError(null);
    setIsAddingGt(true);
    try {
      await restructuringApi.addGroundTruth({
        code,
        content,
        eventDate: gtForm.eventDate.trim() || undefined,
        source: gtForm.source.trim() || undefined,
      });
      setGtForm((prev) => ({ ...prev, content: '', eventDate: '', source: '' }));
      fetchGroundTruth(stockCode.trim() || undefined);
    } catch (err) {
      setGtAddError(err instanceof Error ? err.message : '添加失败');
    } finally {
      setIsAddingGt(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header: input area */}
      <header className="flex-shrink-0 px-4 py-3 border-b border-white/5">
        <div className="max-w-4xl space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            {watchlistCodes.length > 0 && (
              <select
                value={watchlistCodes.includes(stockCode) ? stockCode : ''}
                onChange={(e) => {
                  const v = e.target.value;
                  if (v) {
                    setStockCode(v);
                    setGtForm((prev) => ({ ...prev, code: v }));
                  }
                }}
                disabled={isAnalyzing || isLoadingWatchlist}
                className="input-terminal w-40 text-sm py-2 pr-8 appearance-none bg-elevated border border-white/10 rounded-lg text-secondary focus:border-cyan/40 focus:outline-none disabled:opacity-50"
              >
                <option value="">从自选股选择</option>
                {watchlistCodes.map((code) => {
                  const name = (watchlistNames[code] ?? '').trim();
                  return (
                    <option key={code} value={code}>
                      {name ? `${name} (${code})` : code}
                    </option>
                  );
                })}
              </select>
            )}
            <input
              type="text"
              value={stockCode}
              onChange={(e) => setStockCode(e.target.value.toUpperCase())}
              placeholder="股票代码，如 600519"
              disabled={isAnalyzing}
              className="input-terminal w-32"
            />
            <label className="flex items-center gap-1.5 text-xs text-secondary cursor-pointer">
              <input
                type="checkbox"
                checked={useLlm}
                onChange={(e) => setUseLlm(e.target.checked)}
                disabled={isAnalyzing}
                className="rounded border-white/20"
              />
              使用 AI 生成路径与时间线
            </label>
            <Button
              onClick={handleAnalyze}
              disabled={isAnalyzing || isPreparing}
              isLoading={isAnalyzing}
            >
              {isAnalyzing ? '分析中…' : '运行分析'}
            </Button>
            <Button
              variant="secondary"
              onClick={handlePrepare}
              disabled={isAnalyzing || isPreparing}
              isLoading={isPreparing}
            >
              {isPreparing ? '准备中…' : '仅数据准备'}
            </Button>
            {stockCode.trim() && (
              <span className="text-xs text-muted">
                {isLoadingPrepareInfo ? (
                  '数据准备时间…'
                ) : preparedAt ? (
                  <>最新数据准备：{formatPrepareDate(preparedAt)}</>
                ) : (
                  '暂无数据准备'
                )}
              </span>
            )}
          </div>
          {analyzeError && <p className="text-xs text-red-400">{analyzeError}</p>}
          {prepareMessage && <p className="text-xs text-cyan">{prepareMessage}</p>}
          {prepareError && <p className="text-xs text-red-400">{prepareError}</p>}

          {/* Add ground truth form */}
          <form onSubmit={handleAddGroundTruth} className="flex flex-wrap items-end gap-2 p-3 rounded-xl bg-elevated border border-white/5">
            <span className="text-xs text-secondary w-full mb-1">录入真实消息 / 时间点</span>
            <p className="text-[11px] text-muted w-full mb-2">
              分析时会从数据源自动检索重组相关资讯（重组类型、交易对手、标的资产、预案/过会等进展）并参与路径梳理；您也可在此补充自己掌握的消息与时间点。
            </p>
            <input
              type="text"
              value={gtForm.code}
              onChange={(e) => setGtForm((p) => ({ ...p, code: e.target.value.toUpperCase() }))}
              placeholder="代码"
              className="input-terminal w-24 text-sm"
            />
            <input
              type="text"
              value={gtForm.content}
              onChange={(e) => setGtForm((p) => ({ ...p, content: e.target.value }))}
              placeholder="内容（必填）"
              className="input-terminal flex-1 min-w-[160px] text-sm"
            />
            <input
              type="text"
              value={gtForm.eventDate}
              onChange={(e) => setGtForm((p) => ({ ...p, eventDate: e.target.value }))}
              placeholder="日期 YYYY-MM-DD"
              className="input-terminal w-28 text-sm"
            />
            <input
              type="text"
              value={gtForm.source}
              onChange={(e) => setGtForm((p) => ({ ...p, source: e.target.value }))}
              placeholder="来源"
              className="input-terminal w-24 text-sm"
            />
            <Button type="submit" variant="secondary" disabled={isAddingGt} isLoading={isAddingGt}>
              添加
            </Button>
            {gtAddError && <p className="text-xs text-red-400 w-full">{gtAddError}</p>}
          </form>
        </div>
      </header>

      {/* Main content */}
      <main className="flex-1 overflow-auto p-4 space-y-6">
        <section>
          <h2 className="text-sm font-medium text-secondary mb-2">本次分析结果</h2>
          <ResultCard result={currentResult} isLoading={(isAnalyzing && !currentResult) || isLoadingResult} />
        </section>

        <section>
          <div className="flex items-center gap-2 mb-2">
            <h2 className="text-sm font-medium text-secondary">分析历史</h2>
            <input
              type="text"
              value={historyFilter}
              onChange={(e) => setHistoryFilter(e.target.value)}
              placeholder="按代码筛选"
              className="input-terminal w-28 text-xs py-1.5"
            />
            <button
              type="button"
              onClick={() => fetchHistory(historyFilter)}
              disabled={isLoadingHistory}
              className="text-xs text-cyan hover:underline disabled:opacity-50"
            >
              刷新
            </button>
          </div>
          {isLoadingHistory ? (
            <div className="flex justify-center py-6">
              <div className="w-6 h-6 border-2 border-cyan/20 border-t-cyan rounded-full animate-spin" />
            </div>
          ) : historyList.length === 0 ? (
            <Card padding="md">
              <p className="text-xs text-muted text-center py-4">暂无分析记录</p>
            </Card>
          ) : (
            <div className="rounded-xl border border-white/5 overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-elevated text-left">
                    <th className="px-3 py-2 text-xs text-secondary uppercase">代码</th>
                    <th className="px-3 py-2 text-xs text-secondary uppercase">摘要</th>
                    <th className="px-3 py-2 text-xs text-secondary uppercase">时间</th>
                    <th className="px-3 py-2 text-xs text-secondary uppercase w-20">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {historyList.map((item) => (
                    <tr key={item.id} className="border-t border-white/5 hover:bg-hover">
                      <td className="px-3 py-2 font-mono text-cyan text-xs">{item.code}</td>
                      <td className="px-3 py-2 text-xs text-white truncate max-w-[280px]" title={item.summary || ''}>
                        {item.summary || '--'}
                      </td>
                      <td className="px-3 py-2 text-xs text-muted">{item.createdAt || '--'}</td>
                      <td className="px-3 py-2">
                        <button
                          type="button"
                          onClick={() => handleLoadResult(item.id)}
                          className="text-xs text-cyan hover:underline"
                        >
                          查看
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section>
          <div className="flex items-center gap-2 mb-2">
            <h2 className="text-sm font-medium text-secondary">已录入真实信息</h2>
            <input
              type="text"
              value={gtFilter}
              onChange={(e) => setGtFilter(e.target.value)}
              placeholder="按代码筛选"
              className="input-terminal w-28 text-xs py-1.5"
            />
            <button
              type="button"
              onClick={() => fetchGroundTruth(gtFilter)}
              disabled={isLoadingGt}
              className="text-xs text-cyan hover:underline disabled:opacity-50"
            >
              刷新
            </button>
          </div>
          {isLoadingGt ? (
            <div className="flex justify-center py-6">
              <div className="w-6 h-6 border-2 border-cyan/20 border-t-cyan rounded-full animate-spin" />
            </div>
          ) : groundTruthList.length === 0 ? (
            <Card padding="md">
              <p className="text-xs text-muted text-center py-4">暂无录入，可在上方表单添加</p>
            </Card>
          ) : (
            <div className="rounded-xl border border-white/5 overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-elevated text-left">
                    <th className="px-3 py-2 text-xs text-secondary uppercase">代码</th>
                    <th className="px-3 py-2 text-xs text-secondary uppercase">内容</th>
                    <th className="px-3 py-2 text-xs text-secondary uppercase">日期</th>
                    <th className="px-3 py-2 text-xs text-secondary uppercase">来源</th>
                  </tr>
                </thead>
                <tbody>
                  {groundTruthList.map((item) => (
                    <tr key={item.id} className="border-t border-white/5 hover:bg-hover">
                      <td className="px-3 py-2 font-mono text-cyan text-xs">{item.code}</td>
                      <td className="px-3 py-2 text-xs text-white">{item.content}</td>
                      <td className="px-3 py-2 text-xs text-muted">{item.eventDate || '--'}</td>
                      <td className="px-3 py-2 text-xs text-muted">{item.source || '--'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </main>
    </div>
  );
};

export default RestructuringPage;
