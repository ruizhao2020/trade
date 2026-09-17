import { api } from './client.ts'

export interface PublicIndicatorPolicy {
  id: number
  indicator_type: string
  display_name: string
  public_visible: boolean
  show_parameters: boolean
  show_details: boolean
  show_markers: boolean
  sort_order: number
}

export interface PublicIndicatorFeaturePolicy {
  id: number
  indicator_type: string
  feature_code: string
  display_name: string
  public_visible: boolean
  show_details: boolean
  sort_order: number
}

export interface PublicSiteConfig {
  surface: 'public'
  authentication: false
  modules: ['indicators']
  indicators: PublicIndicatorPolicy[]
  indicator_features: PublicIndicatorFeaturePolicy[]
}

export const fetchPublicSiteConfig = () => api.get<PublicSiteConfig>('/site/config')
