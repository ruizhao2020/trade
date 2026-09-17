import { api } from './client.ts'

export interface ContentTemplate {
  id: string
  name: string
  description: string
  sections: string[]
  enabled: boolean
  built_in: boolean
  editable: boolean
}

export interface ArticleFact {
  label: string
  value: string
  source: string
  timeframe: string
}

export interface ArticleSection {
  code: string
  title: string
  timeframe: string
  facts: ArticleFact[]
  paragraphs: string[]
}

export interface ArticleChartSpec {
  id: string
  title: string
  symbol: string
  symbol_name: string
  timeframe: '1d' | '30m' | '5m'
  kline_limit: number
  indicators: { type: string; params: Record<string, number> }[]
  chan_features: string[]
  aspect_ratio?: '16:9'
}

export interface ArticleDraft {
  id: number
  template_id: string
  title: string
  symbol: string
  symbol_name: string
  market: string
  as_of: string
  timeframes: string[]
  structured_data: { summary?: string; sections?: ArticleSection[]; generator?: string }
  chart_specs: ArticleChartSpec[]
  standard_markdown: string
  platform_variants: Record<'wechat' | 'zhihu' | 'xueqiu', string>
  status: 'draft' | 'reviewed' | 'rejected'
  created_at: string
}

export const fetchContentTemplates = () => api.get<ContentTemplate[]>('/content/templates')
export const createContentTemplate = (values: { name: string; description: string; sections: string[] }) => api.post<ContentTemplate>('/content/templates', values)
export const updateContentTemplate = (id: string, values: { name?: string; description?: string; sections?: string[]; enabled?: boolean }) => api.put<ContentTemplate>(`/content/templates/${id}`, values)
export const deleteContentTemplate = (id: string) => api.delete(`/content/templates/${id}`)
export const fetchArticleDrafts = () => api.get<ArticleDraft[]>('/content/drafts', { limit: '30' })
export const generateArticleDraft = (values: { template_id: string; symbol: string; symbol_name: string; market: string; timeframes: string[]; kline_limit: number }) => api.post<ArticleDraft>('/content/generate', values)
export const updateArticleStatus = (id: number, status: ArticleDraft['status']) => api.put<ArticleDraft>(`/content/drafts/${id}/status`, { status })
export const updateArticleContent = (id: number, values: { standard_markdown?: string; platform_variants?: Record<string, string> }) => api.put<ArticleDraft>(`/content/drafts/${id}`, values)
