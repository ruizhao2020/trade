/**
 * ============================================================================
 * 标的列表 API
 * ============================================================================
 *
 * 封装后端 `GET /api/v1/symbols` 接口，用于品种搜索/下拉选择。
 *
 * 后端参数：
 *   market  : stock=股票 / futures=期货
 *   keyword : 可选，股票代码或名称模糊搜索
 *   limit   : 返回条数
 */

import { api } from './client'

/** 标的条目 */
export interface SymbolItem {
  symbol: string       // 前端使用的 symbol，如 "000001_sz" / "RB0"
  name: string         // 名称，如 "平安银行" / "螺纹钢连续"
  industry?: string    // 行业（仅股票）
  exchange?: string    // 交易所（仅期货）
  market: string       // "stock" / "futures"
}

/** 标的列表响应 */
export interface SymbolListResponse {
  market: string
  total: number        // 符合条件的总数（分页用）
  count: number        // 当前返回数量
  symbols: SymbolItem[]
}

/**
 * 查询品种列表。
 * @param market  market 类型：stock / futures
 * @param keyword 搜索关键字（仅 stock 支持）
 * @param limit   返回条数
 */
export async function fetchSymbols(
  market: string,
  keyword?: string,
  limit = 50,
): Promise<SymbolListResponse> {
  const params: Record<string, string> = { market, limit: String(limit) }
  if (keyword) params.keyword = keyword
  return api.get<SymbolListResponse>('/symbols', params)
}
