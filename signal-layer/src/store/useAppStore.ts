/**
 * SignalLayer 全局状态管理（Zustand）
 *
 * Zustand store 管理前端全部共享状态。组件通过 useAppStore(selector) 订阅所需状态切片。
 *
 * 状态分类:
 *   settings: 用户偏好（品种、周期、主题）
 *   templates: 条件模板列表（CRUD）
 *   templateSignals: 各模板的信号评估状态 {templateId: TemplateSignal}
 *   layers: 图层配置（可见性、透明度）
 *
 * 这个 store 是纯内存的、模块级单例：换账号登录不会重新创建它。
 * 所以凡是「属于某个账号」的切片（templates / activeTemplateId / templateSignals）
 * 必须在身份变化时用 resetWorkspace() 清掉，否则上一个账号的数据会留在界面上。
 */

import { create } from 'zustand'
import type { TemplateSignal, ConditionTemplate, AppSettings, LayerConfig } from '../core/types.ts'
import { DEFAULT_LAYER_CONFIGS, DEFAULT_SETTINGS, DEFAULT_TIMEFRAMES } from '../core/constants.ts'

interface AppState {
  settings: AppSettings
  templates: ConditionTemplate[]
  /** 模板列表是否已经从服务端取过一次（用它判断"要不要再拉"，不要用 length>0） */
  templatesLoaded: boolean
  activeTemplateId: string | null
  templateSignals: Record<string, TemplateSignal>
  layers: LayerConfig[]
  timeframes: typeof DEFAULT_TIMEFRAMES

  // 模板 CRUD
  addTemplate: (template: ConditionTemplate) => void
  updateTemplate: (id: string, updates: Partial<ConditionTemplate>) => void
  deleteTemplate: (id: string) => void
  /** 用服务端返回的完整列表替换本地列表（权威来源，会剔除已不属于当前账号的条目） */
  setTemplates: (templates: ConditionTemplate[]) => void
  setActiveTemplateId: (id: string | null) => void
  /** 身份变化（登录/退出/401）时清空账号级状态，避免跨账号残留 */
  resetWorkspace: () => void
  // 信号评估
  setTemplateSignal: (templateId: string, signal: TemplateSignal) => void
  // 图层操作
  toggleLayerVisibility: (timeframeId: string) => void
  setLayerOpacity: (timeframeId: string, opacity: number) => void
}

/** 初始化默认状态 */
const getInitialState = () => ({
  settings: {
    symbol: DEFAULT_SETTINGS.symbol,
    primaryTimeframe: DEFAULT_SETTINGS.primaryTimeframe,
    layers: DEFAULT_LAYER_CONFIGS,
    showVolume: DEFAULT_SETTINGS.showVolume,
    theme: DEFAULT_SETTINGS.theme as 'dark' | 'light',
  },
  templates: [],
  templatesLoaded: false,
  activeTemplateId: null,
  templateSignals: {},
  layers: DEFAULT_LAYER_CONFIGS,
  timeframes: DEFAULT_TIMEFRAMES,
})

export const useAppStore = create<AppState>((set) => ({
  ...getInitialState(),
  addTemplate: (template) => {
    console.log(`[SL:DATA] addTemplate`, { id: template.id, name: template.name })
    return set((s) => s.templates.some((item) => item.id === template.id)
      ? s
      : { templates: [...s.templates, template] })
  },
  updateTemplate: (id, updates) => {
    console.log(`[SL:DATA] updateTemplate`, { id, updates: Object.keys(updates) })
    return set((s) => ({
      templates: s.templates.map((t) => (t.id === id ? { ...t, ...updates, updatedAt: Date.now() } : t)),
    }))
  },
  /** 删除模板时自动清除 activeTemplateId 如果是正被删除的模板 */
  deleteTemplate: (id) => {
    console.log(`[SL:DATA] deleteTemplate`, { id })
    return set((s) => ({
      templates: s.templates.filter((t) => t.id !== id),
      activeTemplateId: s.activeTemplateId === id ? null : s.activeTemplateId,
      templateSignals: Object.fromEntries(Object.entries(s.templateSignals).filter(([templateId]) => templateId !== id)),
    }))
  },
  setTemplates: (templates) => {
    console.log(`[SL:DATA] setTemplates`, { count: templates.length })
    return set((s) => {
      const ids = new Set(templates.map((t) => t.id))
      return {
        templates,
        templatesLoaded: true,
        // 选中的模板如果已经不在列表里（换账号、被别处删除），选中态也要一起清掉
        activeTemplateId: s.activeTemplateId && !ids.has(s.activeTemplateId) ? null : s.activeTemplateId,
        templateSignals: Object.fromEntries(
          Object.entries(s.templateSignals).filter(([templateId]) => ids.has(templateId)),
        ),
      }
    })
  },
  setActiveTemplateId: (id) => {
    console.log(`[SL:SIGNAL] template selected:`, id)
    return set({ activeTemplateId: id })
  },
  resetWorkspace: () => {
    console.log(`[SL:DATA] resetWorkspace`)
    return set({ templates: [], templatesLoaded: false, activeTemplateId: null, templateSignals: {} })
  },
  setTemplateSignal: (templateId, signal) => set((s) => ({ templateSignals: { ...s.templateSignals, [templateId]: signal } })),
  toggleLayerVisibility: (timeframeId) => {
    console.log(`[SL:DATA] layer toggled`, { tf: timeframeId })
    return set((s) => ({ layers: s.layers.map((l) => (l.timeframeId === timeframeId ? { ...l, visible: !l.visible } : l)) }))
  },
  setLayerOpacity: (timeframeId, opacity) => set((s) => ({ layers: s.layers.map((l) => (l.timeframeId === timeframeId ? { ...l, opacity } : l)) })),
}))
