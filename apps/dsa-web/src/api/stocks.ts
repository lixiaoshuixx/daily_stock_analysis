import apiClient from './index';

export type ExtractFromImageResponse = {
  codes: string[];
  rawText?: string;
};

export type StockNamesResponse = {
  names: Record<string, string>;
};

export const stocksApi = {
  /**
   * Batch get stock names for codes (e.g. for watchlist dropdown display).
   */
  async getNames(codes: string[]): Promise<Record<string, string>> {
    if (!codes.length) return {};
    const params = new URLSearchParams({ codes: codes.join(',') });
    const response = await apiClient.get<StockNamesResponse>(
      `/api/v1/stocks/names?${params.toString()}`
    );
    return response.data?.names ?? {};
  },

  async extractFromImage(file: File): Promise<ExtractFromImageResponse> {
    const formData = new FormData();
    formData.append('file', file);

    const headers: { [key: string]: string | undefined } = { 'Content-Type': undefined };
    const response = await apiClient.post(
      '/api/v1/stocks/extract-from-image',
      formData,
      {
        headers,
        timeout: 60000, // Vision API can be slow; 60s
      },
    );

    const data = response.data as { codes?: string[]; raw_text?: string };
    return {
      codes: data.codes ?? [],
      rawText: data.raw_text,
    };
  },
};
