import { beforeEach, describe, expect, it } from 'vitest'
import { useAppStore } from './useAppStore.ts'
import type { ConditionTemplate } from '../core/types.ts'

function template(id: string, name = id): ConditionTemplate {
  return {
    id, name, logic: 'AND', conditionGroups: [],
    primaryTimeframeId: '1d', secondaryTimeframeIds: [],
    createdAt: 1, updatedAt: 1, enabled: true,
  }
}

/** 换账号登录前后，store 里属于账号的切片 */
function accountSlices() {
  const { templates, templatesLoaded, activeTemplateId, templateSignals } = useAppStore.getState()
  return { templates, templatesLoaded, activeTemplateId, templateSignals }
}

describe('模板列表以服务端为权威来源', () => {
  beforeEach(() => {
    useAppStore.setState({
      templates: [], templatesLoaded: false, activeTemplateId: null, templateSignals: {},
    })
  })

  it('setTemplates 整体替换，换账号后上一个账号的模板不会残留', () => {
    // 账号 A 的会话
    useAppStore.getState().setTemplates([template('tpl_a', 'A 的策略')])
    useAppStore.getState().setActiveTemplateId('tpl_a')
    expect(useAppStore.getState().templates.map((t) => t.id)).toEqual(['tpl_a'])

    // 账号 B 登录后服务端只返回自己的（这里是空列表）
    useAppStore.getState().setTemplates([])

    expect(useAppStore.getState().templates).toEqual([])
  })

  it('替换后把已不在列表里的选中项与信号一起清掉', () => {
    useAppStore.getState().setTemplates([template('tpl_a'), template('tpl_b')])
    useAppStore.getState().setActiveTemplateId('tpl_a')
    useAppStore.setState({ templateSignals: { tpl_a: { state: 'ready' } as never, tpl_b: { state: 'idle' } as never } })

    useAppStore.getState().setTemplates([template('tpl_b')])

    const { templates, activeTemplateId, templateSignals } = accountSlices()
    expect(templates.map((t) => t.id)).toEqual(['tpl_b'])
    // tpl_a 已经不属于这个账号了：选中它会导致编辑按钮打到一个不存在的策略上
    expect(activeTemplateId).toBeNull()
    expect(Object.keys(templateSignals)).toEqual(['tpl_b'])
  })

  it('选中的模板还在列表里时不动选中态（列表刷新不能把用户选好的策略清掉）', () => {
    useAppStore.getState().setTemplates([template('tpl_a'), template('tpl_b')])
    useAppStore.getState().setActiveTemplateId('tpl_b')

    useAppStore.getState().setTemplates([template('tpl_b', 'B 改名了')])

    expect(useAppStore.getState().activeTemplateId).toBe('tpl_b')
    expect(useAppStore.getState().templates[0]!.name).toBe('B 改名了')
  })

  it('resetWorkspace 清空账号级切片并把 templatesLoaded 复位（换账号后必须重新拉）', () => {
    useAppStore.getState().setTemplates([template('tpl_a')])
    useAppStore.getState().setActiveTemplateId('tpl_a')
    useAppStore.setState({ templateSignals: { tpl_a: { state: 'ready' } as never } })
    expect(useAppStore.getState().templatesLoaded).toBe(true)

    useAppStore.getState().resetWorkspace()

    expect(accountSlices()).toEqual({
      templates: [], templatesLoaded: false, activeTemplateId: null, templateSignals: {},
    })
  })
})
