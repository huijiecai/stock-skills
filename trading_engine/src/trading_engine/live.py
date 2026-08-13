from __future__ import annotations

from datetime import datetime
from math import isclose

from pydantic import ValidationError

from trading_engine.astock import AstockClient
from trading_engine.errors import LiveDataError
from trading_engine.models import LiveQuote, MarketSnapshot
from trading_engine.replay import SHANGHAI_TZ


MARKET_INDICES = {
    "000001": "上证指数",
    "399001": "深证成指",
    "399006": "创业板指",
    "000016": "上证50",
    "000300": "沪深300",
    "000852": "中证1000",
}


class LiveMarketData:
    def __init__(
        self,
        client: AstockClient,
        codes: tuple[str, ...],
        include_discovery: bool = False,
    ) -> None:
        if not codes:
            raise LiveDataError("at least one --code is required")
        self.client = client
        self.codes = codes
        self.include_discovery = include_discovery

    def snapshot(self, at: datetime | None = None) -> MarketSnapshot:
        observed_at = at or datetime.now(SHANGHAI_TZ)
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=SHANGHAI_TZ)
        else:
            observed_at = observed_at.astimezone(SHANGHAI_TZ)

        rows = self.client.run_json("live", "quote", *self.codes)
        if not isinstance(rows, list):
            raise LiveDataError("astock live quote returned a non-list payload")

        returned_codes = [str(row.get("code", "")) for row in rows]
        if len(returned_codes) != len(set(returned_codes)):
            raise LiveDataError("astock live quote returned duplicate stock codes")
        if set(returned_codes) != set(self.codes):
            missing = sorted(set(self.codes) - set(returned_codes))
            unexpected = sorted(set(returned_codes) - set(self.codes))
            raise LiveDataError(
                "astock live quote code mismatch: "
                f"missing={','.join(missing) or 'none'} "
                f"unexpected={','.join(unexpected) or 'none'}"
            )

        rows_by_code = {str(row["code"]): row for row in rows}
        quotes = []
        for code in self.codes:
            try:
                quote = LiveQuote.model_validate(rows_by_code[code])
            except ValidationError as exc:
                raise LiveDataError(f"{code}: invalid live quote: {exc}") from exc
            calculated_pct = (
                (quote.price - quote.pre_close) / quote.pre_close * 100
                if quote.pre_close
                else quote.change_pct
            )
            if quote.pre_close and not isclose(
                calculated_pct, quote.change_pct, abs_tol=0.02
            ):
                raise LiveDataError(
                    f"{code}: change_pct does not match price and pre_close"
                )
            quotes.append(quote)

        payload = {
            "mode": "shadow",
            "quotes": [quote.model_dump(mode="json") for quote in quotes],
        }
        if self.include_discovery:
            payload["market_discovery"] = self._market_discovery()

        return MarketSnapshot(
            as_of=observed_at,
            source="astock-live",
            payload=payload,
        )

    def _market_discovery(self) -> dict:
        # live market returns {rows: [...], returned, ...} — rows are the
        # top stocks by the requested sort. Treat them as candidates.
        market = self.client.run_json(
            "live", "market", "--limit", "50", "--sort", "amount", "--market", "all",
        )
        if not isinstance(market, dict):
            raise LiveDataError("astock live market returned a non-object payload")
        rows = market.get("rows")
        if not isinstance(rows, list):
            raise LiveDataError("astock live market omitted rows")
        candidates = rows
        top_amount = rows  # same payload (sorted by amount)

        sector_leaders = self.client.run_json(
            "live", "block", "rank", "--limit", "50"
        )
        if not isinstance(sector_leaders, list):
            raise LiveDataError("astock live block rank returned a non-list payload")
        index_snapshot = self.client.run_json("live", "index", *MARKET_INDICES)
        if not isinstance(index_snapshot, dict):
            raise LiveDataError("astock live index returned a non-object payload")
        indices = index_snapshot.get("indices")
        breadth = index_snapshot.get("breadth")
        if not isinstance(indices, list):
            raise LiveDataError("astock live index omitted indices")
        if not isinstance(breadth, dict):
            raise LiveDataError("astock live index omitted breadth")
        if {str(row.get("code", "")) for row in indices} != set(MARKET_INDICES):
            raise LiveDataError("astock live index returned an incomplete index set")

        discovered_codes = {
            str(row.get("code", ""))
            for row in (*candidates, *top_amount)
            if isinstance(row, dict) and row.get("code")
        }
        discovered_codes.update(self.codes)
        limit_up_codes = tuple(
            sorted(
                {
                    str(row.get("code"))
                    for row in candidates
                    if isinstance(row, dict)
                    and row.get("code")
                    and row.get("state") in {"limit_up", "limits"}
                }
            )
        )

        return {
            "coverage_mode": "candidate_universe",
            "scanned_codes": sorted(discovered_codes),
            "universe_count": market.get("returned"),
            "scanned_count": len(rows),
            "missing_quote_count": 0,
            "failed_batches": 0,
            "candidate_codes": sorted(
                {
                    str(row.get("code"))
                    for row in candidates
                    if isinstance(row, dict) and row.get("code")
                }
            ),
            "candidates": candidates,
            "top_amount": top_amount,
            "sector_leaders": sector_leaders,
            "indices": [
                {
                    "code": str(row["code"]),
                    "name": MARKET_INDICES[str(row["code"])],
                    "price": row["price"],
                    "pre_close": row["pre_close"],
                    "change_pct": row["change_pct"],
                    "amount": row.get("amount", 0),
                }
                for row in indices
            ],
            "breadth": breadth,
            "limit_up_codes": limit_up_codes,
            "missing_capabilities": [],
        }
