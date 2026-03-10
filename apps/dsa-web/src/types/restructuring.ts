/**
 * Restructuring API type definitions
 * Mirrors api/v1/schemas/restructuring.py (camelCase after api client transform)
 */

export interface TimelineNodeOut {
  id?: number;
  eventType?: string;
  eventDate?: string | null;
  description?: string | null;
  source?: string | null;
  verifiedByUser?: boolean;
}

export interface RestructuringAnalysisOut {
  id: number;
  code: string;
  name?: string | null;
  summary?: string | null;
  pathDescription?: string | null;
  rawContext?: string | null;
  createdAt?: string | null;
  timeline: TimelineNodeOut[];
}

export interface RestructuringAnalyzeResponse {
  success: boolean;
  analysisId: number;
  result?: RestructuringAnalysisOut | null;
}

export interface RestructuringAnalysisListItem {
  id: number;
  code: string;
  name?: string | null;
  summary?: string | null;
  pathDescription?: string | null;
  createdAt?: string | null;
}

export interface RestructuringGroundTruthOut {
  id: number;
  code: string;
  content: string;
  eventDate?: string | null;
  source?: string | null;
  createdAt?: string | null;
}
