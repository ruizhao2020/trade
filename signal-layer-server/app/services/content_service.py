from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content import ArticleDraft, ContentTemplate
from app.services.public_site_service import public_indicator_feature_map, public_indicator_map


def _number(value: float, digits: int = 2) -> str:
    return f"{value:,.{digits}f}"


def _fact(label: str, value: str, source: str, timeframe: str) -> dict[str, str]:
    return {"label": label, "value": value, "source": source, "timeframe": timeframe}


class ContentService:
    def __init__(self, data_service, chan_service, indicator_service):
        self._data = data_service
        self._chan = chan_service
        self._indicator = indicator_service

    async def generate(
        self,
        session: AsyncSession,
        *,
        user_id: int,
        template: ContentTemplate,
        symbol: str,
        symbol_name: str,
        market: str,
        timeframes: list[str],
        kline_limit: int,
    ) -> ArticleDraft:
        indicator_policies = await public_indicator_map(session)
        chan_features = await public_indicator_feature_map(session, "chan")
        sections: list[dict[str, Any]] = []
        chart_specs: list[dict[str, Any]] = []
        as_of = datetime.now()

        for timeframe in timeframes:
            result = await self._data.fetch_klines(symbol=symbol, timeframe=timeframe, limit=kline_limit)
            klines = result["data"]
            if len(klines) < 30:
                continue
            latest, previous = klines[-1], klines[-2]
            close = float(latest["close"])
            change = (close / float(previous["close"]) - 1) * 100 if float(previous["close"]) else 0
            period_facts = [
                _fact("最新收盘", _number(close), "K线", timeframe),
                _fact("单周期涨跌", f"{change:+.2f}%", "K线", timeframe),
                _fact("区间最高", _number(max(float(item["high"]) for item in klines[-20:])), "K线", timeframe),
                _fact("区间最低", _number(min(float(item["low"]) for item in klines[-20:])), "K线", timeframe),
            ]
            paragraphs = [f"截至数据截止时点，{timeframe}最新收盘为{_number(close)}，单周期变动{change:+.2f}%。"]
            period_charts: list[tuple[str, str, list[dict[str, Any]], list[str]]] = []

            if indicator_policies.get("ma") and indicator_policies["ma"].public_visible:
                ma_values: dict[int, float] = {}
                for period in (5, 10, 20):
                    calculated = await self._indicator.calculate(symbol, timeframe, "ma", {"period": period}, klines)
                    if calculated.values:
                        ma_values[period] = float(calculated.values[-1].get("value", 0))
                        period_facts.append(_fact(f"MA{period}", _number(ma_values[period]), f"MA({period})", timeframe))
                if len(ma_values) == 3:
                    arrangement = "短期均线位于中长期均线上方" if ma_values[5] > ma_values[10] > ma_values[20] else "均线之间仍处于交错或反向排列"
                    paragraphs.append(f"均线方面，{arrangement}；价格当前{'位于' if close >= ma_values[20] else '低于'}20周期均线。")
                    period_charts.append(("ma", "均线趋势", [
                        {"type": "ma", "params": {"period": 5}},
                        {"type": "ma", "params": {"period": 10}},
                        {"type": "ma", "params": {"period": 20}},
                    ], []))

            if indicator_policies.get("macd") and indicator_policies["macd"].public_visible:
                macd = await self._indicator.calculate(symbol, timeframe, "macd", {"fast": 12, "slow": 26, "signal": 9}, klines)
                if macd.values:
                    row = macd.values[-1]
                    dif, dea, histogram = float(row.get("dif", 0)), float(row.get("dea", 0)), float(row.get("histogram", 0))
                    period_facts.extend([_fact("DIF", _number(dif, 4), "MACD", timeframe), _fact("DEA", _number(dea, 4), "MACD", timeframe), _fact("MACD柱", _number(histogram, 4), "MACD", timeframe)])
                    paragraphs.append(f"动量方面，DIF{'高于' if dif >= dea else '低于'}DEA，柱体为{'正' if histogram >= 0 else '负'}值，反映当前动量状态但不代表未来方向。")
                    period_charts.append(("macd", "MACD 动量", [{"type": "macd", "params": {"fast": 12, "slow": 26, "signal": 9}}], []))

            if indicator_policies.get("rsi") and indicator_policies["rsi"].public_visible:
                rsi = await self._indicator.calculate(symbol, timeframe, "rsi", {"period": 14}, klines)
                if rsi.values:
                    rsi_value = float(rsi.values[-1].get("value", 0))
                    period_facts.append(_fact("RSI14", _number(rsi_value), "RSI(14)", timeframe))
                    paragraphs.append(f"RSI14为{_number(rsi_value)}，处于{'相对高位' if rsi_value >= 70 else '相对低位' if rsi_value <= 30 else '中性区间'}。")
                    period_charts.append(("rsi", "RSI 强弱", [{"type": "rsi", "params": {"period": 14}}], []))

            if indicator_policies.get("volume") and indicator_policies["volume"].public_visible:
                volume = float(latest.get("volume", 0))
                previous_volume = float(previous.get("volume", 0))
                ratio = volume / previous_volume if previous_volume else 0
                period_facts.append(_fact("相邻量比", _number(ratio), "成交量", timeframe))
                paragraphs.append(f"成交量约为上一周期的{_number(ratio)}倍，需结合价格位置观察量价配合。")
                period_charts.append(("volume", "成交量", [{"type": "volume", "params": {}}], []))

            chan_policy = indicator_policies.get("chan")
            visible_chan = [code for code, item in chan_features.items() if item.public_visible]
            if chan_policy and chan_policy.public_visible and visible_chan:
                chan = await self._chan.analyze(symbol, timeframe, klines)
                chan_fact_values = {
                    "bi": len(chan.bis), "duan": len(chan.duans), "zhongshu": len(chan.zhongshus),
                    "divergence": len(chan.divergences), "buy_sell_points": len(chan.buy_sell_points),
                }
                for feature in visible_chan:
                    if feature in chan_fact_values:
                        period_facts.append(_fact(chan_features[feature].display_name, str(chan_fact_values[feature]), "缠论结构", timeframe))
                paragraphs.append("结构分析仅呈现管理员允许公开的分型、笔、段和中枢等客观结构，不构成交易建议。")
                period_charts.append(("chan", "结构分析", [], visible_chan))

            sections.append({
                "code": f"technical_{timeframe}", "title": f"{timeframe} 技术观察",
                "timeframe": timeframe, "facts": period_facts, "paragraphs": paragraphs,
            })
            for chart_code, chart_name, chart_indicators, chart_chan_features in period_charts:
                chart_specs.append({
                    "id": f"chart-{timeframe}-{chart_code}",
                    "title": f"{symbol_name} {timeframe} · {chart_name}",
                    "symbol": symbol, "symbol_name": symbol_name, "timeframe": timeframe,
                    "kline_limit": kline_limit, "indicators": chart_indicators,
                    "chan_features": chart_chan_features,
                    "aspect_ratio": "16:9",
                })
            as_of = datetime.fromtimestamp(int(latest["open_time"]) / 1000)

        title = f"{symbol_name}（{symbol}）技术结构观察"
        summary = self._summary(symbol_name, sections)
        standard = self._standard_markdown(title, as_of, summary, sections)
        variants = {
            "wechat": standard,
            "zhihu": self._zhihu_markdown(title, as_of, summary, sections),
            "xueqiu": self._xueqiu_markdown(title, as_of, summary, sections),
        }
        draft = ArticleDraft(
            user_id=user_id, template_id=template.id, title=title, symbol=symbol,
            symbol_name=symbol_name, market=market, as_of=as_of, timeframes=timeframes,
            structured_data={"summary": summary, "sections": sections, "generator": "rules-v1"},
            chart_specs=chart_specs, standard_markdown=standard,
            platform_variants=variants, status="draft",
        )
        session.add(draft)
        await session.commit()
        await session.refresh(draft)
        return draft

    @staticmethod
    def _summary(symbol_name: str, sections: list[dict[str, Any]]) -> str:
        return f"本文基于{symbol_name}截至数据时点的行情与公开技术指标，从趋势、动量、量价和结构等角度进行客观梳理。共覆盖{len(sections)}个周期，结论用于研究记录，不构成投资建议。"

    @staticmethod
    def _standard_markdown(title: str, as_of: datetime, summary: str, sections: list[dict[str, Any]]) -> str:
        parts = [f"# {title}", f"> 数据截止：{as_of:%Y-%m-%d %H:%M}", summary]
        for section in sections:
            parts.append(f"## {section['title']}")
            parts.extend(section["paragraphs"])
            parts.append("\n".join(f"- {fact['label']}：{fact['value']}（{fact['source']}）" for fact in section["facts"]))
        parts.extend(["## 风险与观察", "技术指标基于历史行情计算，可能存在滞后。后续可持续观察价格、成交量与结构是否发生一致性变化。", "---", "本文为行情研究工具生成的客观数据整理，不构成任何投资建议。市场有风险，决策需谨慎。"])
        return "\n\n".join(parts)

    @classmethod
    def _zhihu_markdown(cls, title: str, as_of: datetime, summary: str, sections: list[dict[str, Any]]) -> str:
        body = cls._standard_markdown(title, as_of, summary, sections)
        return body.replace("# ", "# 如何从多个技术维度观察：", 1)

    @staticmethod
    def _xueqiu_markdown(title: str, as_of: datetime, summary: str, sections: list[dict[str, Any]]) -> str:
        lines = [f"【{title}】", f"数据截止：{as_of:%Y-%m-%d %H:%M}", summary]
        for section in sections:
            lines.append(f"\n{section['title']}：")
            lines.extend(f"• {paragraph}" for paragraph in section["paragraphs"][:3])
        lines.append("\n仅为客观行情研究记录，不构成投资建议。")
        return "\n".join(lines)
