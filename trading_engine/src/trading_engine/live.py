from __future__ import annotations

from datetime import datetime
from math import isclose

from pydantic import ValidationError

from trading_engine.astock import AstockClient
from trading_engine.errors import LiveDataError
from trading_engine.models import LiveQuote, MarketSnapshot
from trading_engine.replay import SHANGHAI_TZ


class LiveMarketData:
    def __init__(self, client: AstockClient, codes: tuple[str, ...]) -> None:
        if not codes:
            raise LiveDataError("at least one --code is required")
        self.client = client
        self.codes = codes

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
            calculated_pct = (quote.price - quote.pre_close) / quote.pre_close * 100
            if not isclose(calculated_pct, quote.change_pct, abs_tol=0.02):
                raise LiveDataError(
                    f"{code}: change_pct does not match price and pre_close"
                )
            quotes.append(quote)

        return MarketSnapshot(
            as_of=observed_at,
            source="astock-live",
            payload={
                "mode": "shadow",
                "quotes": [quote.model_dump(mode="json") for quote in quotes],
            },
        )
