/**
 * 指标加载的容错与错误汇总。
 *
 * 指标计算是一次网络往返，失败可能只是瞬时的（后端重启、网关抖动）。
 * 之前失败后结果直接置空，图表就少一个副图，且没有任何重试；单条指标
 * 计算失败（接口返回 errors 而不是抛异常）更是完全静默——策略引用的
 * 指标会"莫名其妙"不出现。
 */

/** 失败后重试一次：第一次失败多为瞬时问题，重试能避免图表缺指标。 */
export async function withRetry<T>(
  loader: () => Promise<T>,
  attempts = 2,
  delayMs = 600,
): Promise<T> {
  let lastError: unknown
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      return await loader()
    } catch (error) {
      lastError = error
      if (attempt < attempts) {
        await new Promise((resolve) => setTimeout(resolve, delayMs))
      }
    }
  }
  throw lastError
}

/** 把接口返回的单条指标错误拼成可展示的文案；没有错误时返回 null。 */
export function indicatorErrorMessage(
  errors: { type: string; message: string }[],
): string | null {
  if (errors.length === 0) return null
  return errors.map((error) => `${error.type}: ${error.message}`).join('；')
}
