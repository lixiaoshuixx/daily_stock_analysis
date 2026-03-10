import apiClient from './index';
import { toCamelCase } from './utils';
import type {
  RestructuringAnalyzeResponse,
  RestructuringAnalysisListItem,
  RestructuringAnalysisOut,
  RestructuringGroundTruthOut,
} from '../types/restructuring';

export const restructuringApi = {
  /**
   * Data preparation only: build context and write to reports/. No path analysis LLM.
   * Uses long timeout (5 min): LLM filter + many announcement fetches with delay.
   */
  prepare: async (params: {
    code: string;
    name?: string;
  }): Promise<{ success: boolean; message?: string; error?: string; preparedAt?: string | null }> => {
    const body: Record<string, unknown> = { code: params.code.trim() };
    if (params.name != null && params.name !== '') body.name = params.name;
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/restructuring/prepare', body, {
      timeout: 300000, // 5 min: directory + LLM filter + many fetches
    });
    return toCamelCase<{ success: boolean; message?: string; error?: string; preparedAt?: string | null }>(
      response.data
    );
  },

  /**
   * Get latest data preparation time for a stock (from reports/{code}_restructuring_context.txt).
   */
  getPrepareInfo: async (code: string): Promise<{ preparedAt: string | null }> => {
    const response = await apiClient.get<Record<string, unknown>>('/api/v1/restructuring/prepare-info', {
      params: { code: code.trim() },
    });
    const data = toCamelCase<{ preparedAt: string | null }>(response.data);
    return { preparedAt: data?.preparedAt ?? null };
  },

  /**
   * Run restructuring analysis for a stock.
   * Uses long timeout (5 min): data prep + optional path LLM.
   * When keepLatestOnly is true, older analyses for this stock are deleted so only the new one remains.
   */
  analyze: async (params: {
    code: string;
    name?: string;
    useLlm?: boolean;
    keepLatestOnly?: boolean;
  }): Promise<RestructuringAnalyzeResponse> => {
    const body: Record<string, unknown> = { code: params.code.trim() };
    if (params.name != null) body.name = params.name;
    if (params.useLlm != null) body.use_llm = params.useLlm;
    if (params.keepLatestOnly != null) body.keep_latest_only = params.keepLatestOnly;
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/restructuring/analyze', body, {
      timeout: 300000, // 5 min: data prep + path analysis LLM
    });
    return toCamelCase<RestructuringAnalyzeResponse>(response.data);
  },

  /**
   * List restructuring analyses (optional filter by code)
   */
  getHistory: async (params?: { code?: string; limit?: number }): Promise<RestructuringAnalysisListItem[]> => {
    const query: Record<string, string | number> = {};
    if (params?.code) query.code = params.code;
    if (params?.limit != null) query.limit = params.limit;
    const response = await apiClient.get<unknown[]>('/api/v1/restructuring/history', { params: query });
    return (Array.isArray(response.data) ? response.data : []).map((item) =>
      toCamelCase<RestructuringAnalysisListItem>(item as Record<string, unknown>)
    );
  },

  /**
   * Get one analysis with timeline by id
   */
  getResult: async (analysisId: number): Promise<RestructuringAnalysisOut | null> => {
    try {
      const response = await apiClient.get<Record<string, unknown>>(
        `/api/v1/restructuring/result/${analysisId}`
      );
      return toCamelCase<RestructuringAnalysisOut>(response.data);
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { status?: number } };
        if (axiosErr.response?.status === 404) return null;
      }
      throw err;
    }
  },

  /**
   * Add a ground-truth message/time point
   */
  addGroundTruth: async (params: {
    code: string;
    content: string;
    eventDate?: string | null;
    source?: string | null;
  }): Promise<{ id: number; code: string }> => {
    const body: Record<string, unknown> = {
      code: params.code.trim(),
      content: params.content.trim(),
    };
    if (params.eventDate != null && params.eventDate !== '') body.event_date = params.eventDate;
    if (params.source != null && params.source !== '') body.source = params.source;
    const response = await apiClient.post<Record<string, unknown>>('/api/v1/restructuring/ground-truth', body);
    return toCamelCase<{ id: number; code: string }>(response.data);
  },

  /**
   * List ground-truth entries (optional filter by code)
   */
  getGroundTruth: async (params?: { code?: string; limit?: number }): Promise<RestructuringGroundTruthOut[]> => {
    const query: Record<string, string | number> = {};
    if (params?.code) query.code = params.code;
    if (params?.limit != null) query.limit = params.limit;
    const response = await apiClient.get<unknown[]>('/api/v1/restructuring/ground-truth', { params: query });
    return (Array.isArray(response.data) ? response.data : []).map((item) =>
      toCamelCase<RestructuringGroundTruthOut>(item as Record<string, unknown>)
    );
  },
};
