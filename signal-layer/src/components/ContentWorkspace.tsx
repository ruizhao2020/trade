import { useCallback, useEffect, useState } from 'react'
import { fetchChanAnalysis } from '../api/chan.ts'
import { calculateIndicators } from '../api/indicator.ts'
import { fetchKlines } from '../api/kline.ts'
import {
  createContentTemplate, deleteContentTemplate, fetchArticleDrafts, fetchContentTemplates,
  generateArticleDraft, updateArticleContent, updateArticleStatus, updateContentTemplate,
} from '../api/content.ts'
import type { ArticleChartSpec, ArticleDraft, ContentTemplate } from '../api/content.ts'
import { Chart } from '../chart/Chart.tsx'
import type { ChanAnalysis, ChanRenderOptions, IndicatorResult, RawKline } from '../core/types.ts'
import { SymbolSelector } from './SymbolSelector.tsx'

const PLATFORM_LABELS = { standard: '标准稿', wechat: '公众号', zhihu: '知乎', xueqiu: '雪球' } as const
const SECTION_OPTIONS = [
  ['summary', '行情概览'], ['trend', '趋势与均线'], ['momentum', '动量指标'],
  ['volume', '成交量'], ['structure', '结构分析'], ['risk', '风险观察'],
] as const
type PreviewPlatform = keyof typeof PLATFORM_LABELS

function ArticleChartCard({ spec }: { spec: ArticleChartSpec }) {
  const [klines, setKlines] = useState<RawKline[]>([])
  const [analysis, setAnalysis] = useState<ChanAnalysis | null>(null)
  const [indicators, setIndicators] = useState<IndicatorResult[]>([])
  const [loading, setLoading] = useState(true)
  const [snapshotRequest, setSnapshotRequest] = useState(0)

  useEffect(() => {
    let cancelled = false
    Promise.all([
      fetchKlines(spec.symbol, spec.timeframe, spec.kline_limit),
      fetchChanAnalysis(spec.symbol, spec.timeframe, spec.kline_limit),
      spec.indicators.length
        ? calculateIndicators(spec.symbol, spec.timeframe, spec.indicators, spec.kline_limit)
        : Promise.resolve([]),
    ]).then(([bars, chan, results]) => {
      if (!cancelled) {
        setKlines(bars.data as RawKline[])
        setAnalysis(chan)
        setIndicators(results)
        setLoading(false)
      }
    }).catch(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [spec])

  const chanOptions: ChanRenderOptions = {
    showFenxing: spec.chan_features.includes('fenxing'),
    showBi: spec.chan_features.includes('bi'),
    showDuan: spec.chan_features.includes('duan'),
    showZhongshu: spec.chan_features.includes('zhongshu'),
    showZhongshuAxis: true,
    showDivergences: spec.chan_features.includes('divergence'),
    showBuySellPoints: spec.chan_features.includes('buy_sell_points'),
    zsLevel: 'bi', biColor: '#e7c66b', duanColor: '#6c8cff', zhongshuColor: '#9b8cf2',
  }
  const downloadSnapshot = useCallback((dataUrl: string) => {
    const link = document.createElement('a')
    link.href = dataUrl
    link.download = `${spec.symbol}-${spec.timeframe}-${spec.id}.png`
    link.click()
  }, [spec])

  return (
    <section className="rounded-lg border border-[var(--border-primary)] bg-[var(--bg-secondary)] overflow-hidden">
      <div className="h-11 px-4 flex items-center gap-3 border-b border-[var(--border-primary)]">
        <div className="flex-1">
          <div className="text-[11px] font-medium">{spec.title}</div>
          <div className="text-[11px] text-[var(--text-muted)]">单指标图 · 16:9 · {spec.timeframe}</div>
        </div>
        <button type="button" onClick={() => setSnapshotRequest((value) => value + 1)} className="action-secondary">下载截图</button>
      </div>
      <div className="relative aspect-video min-h-[360px]">
        {loading ? (
          <div className="absolute inset-0 grid place-items-center text-[11px] text-[var(--text-muted)]">图表生成中…</div>
        ) : (
          <Chart
            klineData={klines}
            chanAnalysis={analysis ?? undefined}
            chanOptions={chanOptions}
            indicatorResults={indicators}
            snapshotRequestId={snapshotRequest}
            onSnapshot={downloadSnapshot}
          />
        )}
      </div>
    </section>
  )
}

function TemplateDialog({
  editing, name, description, sections, onName, onDescription, onToggleSection, onClose, onSave,
}: {
  editing: boolean
  name: string
  description: string
  sections: string[]
  onName: (value: string) => void
  onDescription: (value: string) => void
  onToggleSection: (value: string) => void
  onClose: () => void
  onSave: () => void
}) {
  return (
    <div className="fixed inset-0 z-50 bg-black/55 grid place-items-center p-5">
      <div className="w-[520px] rounded-xl border border-[var(--border-accent)] bg-[var(--bg-secondary)] shadow-2xl">
        <div className="h-12 px-5 flex items-center border-b border-[var(--border-primary)]">
          <div className="text-[13px] font-semibold">{editing ? '编辑文章模板' : '新建文章模板'}</div>
          <button type="button" onClick={onClose} className="ml-auto icon-button">×</button>
        </div>
        <div className="p-5 space-y-4">
          <label className="block text-[11px] text-[var(--text-muted)]">模板名称<input value={name} onChange={(event) => onName(event.target.value)} className="field mt-1 w-full" /></label>
          <label className="block text-[11px] text-[var(--text-muted)]">模板说明<textarea value={description} onChange={(event) => onDescription(event.target.value)} className="mt-1 w-full min-h-20 p-3 rounded-md border border-[var(--border-primary)] bg-[var(--bg-tertiary)] text-[11px] outline-none" /></label>
          <div>
            <div className="text-[11px] text-[var(--text-muted)] mb-2">文章区块</div>
            <div className="grid grid-cols-2 gap-2">
              {SECTION_OPTIONS.map(([code, label]) => (
                <label key={code} className="min-h-9 px-3 rounded-md border border-[var(--border-primary)] flex items-center gap-2 text-[11px] text-[var(--text-secondary)]">
                  <input type="checkbox" checked={sections.includes(code)} onChange={() => onToggleSection(code)} className="accent-[var(--accent)]" />{label}
                </label>
              ))}
            </div>
          </div>
          <div className="flex justify-end gap-2">
            <button type="button" onClick={onClose} className="action-secondary">取消</button>
            <button type="button" disabled={!name.trim() || !sections.length} onClick={onSave} className="action-primary">保存模板</button>
          </div>
        </div>
      </div>
    </div>
  )
}

export function ContentWorkspace() {
  const [templates, setTemplates] = useState<ContentTemplate[]>([])
  const [drafts, setDrafts] = useState<ArticleDraft[]>([])
  const [selected, setSelected] = useState<ArticleDraft | null>(null)
  const [templateId, setTemplateId] = useState('stock_technical_overview')
  const [market, setMarket] = useState('')
  const [symbol, setSymbol] = useState('')
  const [symbolName, setSymbolName] = useState('')
  const [timeframes, setTimeframes] = useState<string[]>(['1d'])
  const [platform, setPlatform] = useState<PreviewPlatform>('standard')
  const [standardText, setStandardText] = useState('')
  const [variants, setVariants] = useState<Record<string, string>>({})
  const [generating, setGenerating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [templateEditorOpen, setTemplateEditorOpen] = useState(false)
  const [editingTemplateId, setEditingTemplateId] = useState<string | null>(null)
  const [templateName, setTemplateName] = useState('')
  const [templateDescription, setTemplateDescription] = useState('')
  const [templateSections, setTemplateSections] = useState<string[]>(SECTION_OPTIONS.map(([code]) => code))

  const chooseDraft = (draft: ArticleDraft) => {
    setSelected(draft)
    setStandardText(draft.standard_markdown)
    setVariants(draft.platform_variants)
    setPlatform('standard')
  }
  useEffect(() => {
    Promise.all([fetchContentTemplates(), fetchArticleDrafts()]).then(([nextTemplates, nextDrafts]) => {
      setTemplates(nextTemplates)
      setDrafts(nextDrafts)
      if (nextDrafts[0]) chooseDraft(nextDrafts[0])
    }).catch((reason) => setError(reason instanceof Error ? reason.message : '内容数据加载失败'))
  }, [])

  const activeText = platform === 'standard' ? standardText : variants[platform] || ''
  const setActiveText = (value: string) => platform === 'standard'
    ? setStandardText(value)
    : setVariants((current) => ({ ...current, [platform]: value }))
  const toggleTimeframe = (timeframe: string) => setTimeframes((current) => current.includes(timeframe)
    ? current.filter((item) => item !== timeframe)
    : [...current, timeframe])
  const handleMarketChange = (nextMarket: string) => {
    setMarket(nextMarket)
  }
  const handleSymbolChange = (nextSymbol: string, nextName: string) => { setSymbol(nextSymbol); setSymbolName(nextName) }

  const openNewTemplate = () => {
    setEditingTemplateId(null); setTemplateName(''); setTemplateDescription('')
    setTemplateSections(SECTION_OPTIONS.map(([code]) => code)); setTemplateEditorOpen(true)
  }
  const openEditTemplate = () => {
    const item = templates.find((template) => template.id === templateId)
    if (!item?.editable) return
    setEditingTemplateId(item.id); setTemplateName(item.name); setTemplateDescription(item.description)
    setTemplateSections(item.sections); setTemplateEditorOpen(true)
  }
  const toggleTemplateSection = (section: string) => setTemplateSections((current) => current.includes(section)
    ? current.filter((item) => item !== section)
    : [...current, section])
  async function saveTemplate() {
    if (!templateName.trim() || !templateSections.length) return
    const values = { name: templateName.trim(), description: templateDescription.trim(), sections: templateSections }
    const next = editingTemplateId
      ? await updateContentTemplate(editingTemplateId, values)
      : await createContentTemplate(values)
    setTemplates((current) => editingTemplateId
      ? current.map((item) => item.id === next.id ? next : item)
      : [...current, next])
    setTemplateId(next.id); setTemplateEditorOpen(false)
  }
  async function removeTemplate() {
    const item = templates.find((template) => template.id === templateId)
    if (!item?.editable || !window.confirm(`确定删除模板“${item.name}”吗？`)) return
    await deleteContentTemplate(item.id)
    const next = templates.filter((template) => template.id !== item.id)
    setTemplates(next); setTemplateId(next[0]?.id || '')
  }
  async function generate() {
    if (!symbol || !symbolName || !timeframes.length) return
    setGenerating(true); setError('')
    try {
      const draft = await generateArticleDraft({ template_id: templateId, symbol, symbol_name: symbolName, market, timeframes, kline_limit: 300 })
      setDrafts((current) => [draft, ...current]); chooseDraft(draft)
    } catch (reason) { setError(reason instanceof Error ? reason.message : '生成失败') } finally { setGenerating(false) }
  }
  async function save() {
    if (!selected) return
    setSaving(true)
    try {
      const next = await updateArticleContent(selected.id, { standard_markdown: standardText, platform_variants: variants })
      setSelected(next); setDrafts((current) => current.map((item) => item.id === next.id ? next : item))
    } finally { setSaving(false) }
  }
  async function review() {
    if (!selected) return
    const next = await updateArticleStatus(selected.id, selected.status === 'reviewed' ? 'draft' : 'reviewed')
    setSelected(next); setDrafts((current) => current.map((item) => item.id === next.id ? next : item))
  }

  const selectedTemplate = templates.find((item) => item.id === templateId)
  return (
    <div className="flex-1 min-h-0 flex flex-col bg-[var(--bg-primary)]">
      <header className="h-16 px-6 flex items-center border-b border-[var(--border-primary)] bg-[var(--bg-secondary)]">
        <div><h1 className="text-[16px] font-semibold">内容研究</h1><p className="mt-1 text-[11px] text-[var(--text-muted)]">结构化分析、图表快照与多平台文章草稿</p></div>
        <div className="ml-auto text-[11px] text-[var(--text-muted)]">首版仅生成草稿，不自动发布</div>
      </header>
      {error && <div role="alert" className="mx-5 mt-4 px-3 py-2 rounded-md border border-[rgba(255,107,114,.25)] text-[11px] text-[var(--accent-red)]">{error}</div>}
      <div className="flex-1 min-h-0 grid grid-cols-[320px_minmax(0,1fr)] overflow-hidden">
        <aside className="border-r border-[var(--border-primary)] bg-[var(--bg-secondary)] overflow-y-auto">
          <div className="p-4 space-y-4 border-b border-[var(--border-primary)]">
            <div className="text-[11px] font-semibold">新建内容任务</div>
            <div>
              <label className="block text-[11px] text-[var(--text-muted)]">分析模板<select value={templateId} onChange={(event) => setTemplateId(event.target.value)} className="field mt-1 w-full">{templates.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
              <div className="mt-2 flex gap-2"><button type="button" onClick={openNewTemplate} className="action-secondary flex-1">新建模板</button><button type="button" disabled={!selectedTemplate?.editable} onClick={openEditTemplate} className="action-secondary flex-1 disabled:opacity-35">编辑</button><button type="button" disabled={!selectedTemplate?.editable} onClick={() => void removeTemplate()} className="icon-button disabled:opacity-35">×</button></div>
            </div>
            <div>
              <div className="text-[11px] text-[var(--text-muted)] mb-1.5">市场与标的</div>
              <div className="content-symbol-selector"><SymbolSelector market={market} symbol={symbol} symbolName={symbolName} onMarketChange={handleMarketChange} onSymbolChange={handleSymbolChange} /></div>
            </div>
            <div><div className="text-[11px] text-[var(--text-muted)] mb-2">分析周期</div><div className="flex gap-3">{['1d', '30m', '5m'].map((item) => <label key={item} className="inline-flex items-center gap-1 text-[11px] text-[var(--text-secondary)]"><input type="checkbox" checked={timeframes.includes(item)} onChange={() => toggleTimeframe(item)} className="accent-[var(--accent)]" />{item}</label>)}</div></div>
            <button type="button" disabled={generating || !templateId || !market || !symbol || !timeframes.length} onClick={() => void generate()} className="action-primary w-full">{generating ? '分析并生成中…' : '生成文章草稿'}</button>
          </div>
          <div className="p-3"><div className="px-1 mb-2 text-[11px] font-semibold text-[var(--text-muted)]">历史草稿</div>{drafts.map((draft) => <button type="button" key={draft.id} onClick={() => chooseDraft(draft)} className={`w-full p-2.5 rounded-md text-left ${selected?.id === draft.id ? 'bg-[rgba(108,140,255,.12)]' : 'hover:bg-[var(--bg-tertiary)]'}`}><div className="text-[11px] truncate">{draft.title}</div><div className="mt-1 text-[11px] text-[var(--text-muted)]">{new Date(draft.created_at).toLocaleString('zh-CN')} · {draft.status === 'reviewed' ? '已审核' : '草稿'}</div></button>)}</div>
        </aside>
        <main className="min-w-0 overflow-y-auto p-5">
          {selected ? <div className="max-w-6xl mx-auto space-y-4">
            <section className="rounded-lg border border-[var(--border-primary)] bg-[var(--bg-secondary)] overflow-hidden">
              <div className="h-12 px-4 flex items-center gap-2 border-b border-[var(--border-primary)]"><div className="flex-1"><div className="text-[12px] font-semibold">{selected.title}</div><div className="text-[11px] text-[var(--text-muted)]">数据截止 {new Date(selected.as_of).toLocaleString('zh-CN')} · 规则版本 {selected.structured_data.generator}</div></div><button type="button" onClick={() => void navigator.clipboard.writeText(activeText)} className="action-secondary">复制正文</button><button type="button" disabled={saving} onClick={() => void save()} className="action-secondary">{saving ? '保存中…' : '保存修改'}</button><button type="button" onClick={() => void review()} className="action-primary">{selected.status === 'reviewed' ? '取消审核' : '审核通过'}</button></div>
              <div className="px-4 pt-3 flex gap-1 border-b border-[var(--border-primary)]">{Object.entries(PLATFORM_LABELS).map(([key, label]) => <button type="button" key={key} onClick={() => setPlatform(key as PreviewPlatform)} className={`h-8 px-3 text-[11px] border-b-2 ${platform === key ? 'border-[var(--accent)] text-[var(--text-primary)]' : 'border-transparent text-[var(--text-muted)]'}`}>{label}</button>)}</div>
              <textarea value={activeText} onChange={(event) => setActiveText(event.target.value)} className="w-full min-h-[460px] p-5 bg-[var(--bg-primary)] text-[12px] leading-6 text-[var(--text-secondary)] outline-none resize-y font-mono" />
            </section>
            <section className="rounded-lg border border-[var(--border-primary)] bg-[var(--bg-secondary)] p-4"><div className="text-[11px] font-semibold mb-3">结构化事实</div><div className="grid grid-cols-1 lg:grid-cols-2 gap-3">{(selected.structured_data.sections || []).map((section) => <div key={section.code} className="p-3 rounded-md bg-[var(--bg-tertiary)]"><div className="text-[11px] font-medium">{section.title}</div>{section.facts.map((fact) => <div key={`${section.code}-${fact.label}`} className="mt-1 flex justify-between gap-3 text-[11px]"><span className="text-[var(--text-muted)]">{fact.label}</span><span className="font-mono">{fact.value}</span></div>)}</div>)}</div></section>
            {selected.chart_specs.map((spec) => <ArticleChartCard key={spec.id} spec={spec} />)}
          </div> : <div className="h-full grid place-items-center text-[11px] text-[var(--text-muted)]">创建任务或选择历史草稿后查看文章和图表</div>}
        </main>
      </div>
      {templateEditorOpen && <TemplateDialog editing={Boolean(editingTemplateId)} name={templateName} description={templateDescription} sections={templateSections} onName={setTemplateName} onDescription={setTemplateDescription} onToggleSection={toggleTemplateSection} onClose={() => setTemplateEditorOpen(false)} onSave={() => void saveTemplate()} />}
    </div>
  )
}
