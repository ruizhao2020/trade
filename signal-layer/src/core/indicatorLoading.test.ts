import { describe, expect, it, vi } from 'vitest'
import { indicatorErrorMessage, withRetry } from './indicatorLoading.ts'

describe('指标加载容错', () => {
  it('瞬时失败会重试一次，第二次成功后返回结果', async () => {
    const loader = vi.fn()
      .mockRejectedValueOnce(new Error('网络抖动'))
      .mockResolvedValueOnce(['macd'])

    await expect(withRetry(loader, 2, 0)).resolves.toEqual(['macd'])
    expect(loader).toHaveBeenCalledTimes(2)
  })

  it('一直失败时抛出最后一次错误', async () => {
    const loader = vi.fn().mockRejectedValue(new Error('后端不可用'))

    await expect(withRetry(loader, 2, 0)).rejects.toThrow('后端不可用')
    expect(loader).toHaveBeenCalledTimes(2)
  })

  it('汇总单条指标计算错误，没有错误时返回 null', () => {
    expect(indicatorErrorMessage([])).toBeNull()
    expect(indicatorErrorMessage([
      { type: 'macd', message: '参数非法' },
      { type: 'ma', message: '样本不足' },
    ])).toBe('macd: 参数非法；ma: 样本不足')
  })
})
