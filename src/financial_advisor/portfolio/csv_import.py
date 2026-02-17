"""CSV import for portfolio holdings.

Expected CSV format:
    symbol,shares,cost_basis,account_type,notes
    AAPL,50,150.00,brokerage,Core tech holding
    VOO,100,380.00,roth_ira,S&P 500 index

account_type and notes are optional columns.
"""

import csv
import io
import logging
from typing import NamedTuple

from .models import Holding

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"symbol", "shares", "cost_basis"}
VALID_ACCOUNT_TYPES = {"brokerage", "roth_ira", "traditional_ira", "401k", "hsa", "other"}


class ImportResult(NamedTuple):
    holdings: list[Holding]
    errors: list[str]
    skipped: int


def parse_holdings_csv(content: str) -> ImportResult:
    """Parse CSV content into a list of Holding models.

    Returns ImportResult with successfully parsed holdings, any row-level errors,
    and a count of skipped rows.
    """
    reader = csv.DictReader(io.StringIO(content.strip()))

    if reader.fieldnames is None:
        return ImportResult(holdings=[], errors=["CSV is empty or has no header row"], skipped=0)

    # Normalize header names (lowercase, strip whitespace)
    normalized_fields = {f.strip().lower() for f in reader.fieldnames}
    missing = REQUIRED_COLUMNS - normalized_fields
    if missing:
        return ImportResult(
            holdings=[],
            errors=[f"Missing required columns: {', '.join(sorted(missing))}"],
            skipped=0,
        )

    holdings: list[Holding] = []
    errors: list[str] = []
    skipped = 0

    for row_num, raw_row in enumerate(reader, start=2):  # start=2 (row 1 is header)
        row = {k.strip().lower(): v.strip() for k, v in raw_row.items() if k}

        symbol = row.get("symbol", "").upper()
        if not symbol:
            errors.append(f"Row {row_num}: symbol is empty, skipping")
            skipped += 1
            continue

        try:
            shares = float(row.get("shares", ""))
        except ValueError:
            errors.append(f"Row {row_num} ({symbol}): invalid shares value '{row.get('shares')}'")
            skipped += 1
            continue

        try:
            cost_basis = float(row.get("cost_basis", ""))
        except ValueError:
            errors.append(
                f"Row {row_num} ({symbol}): invalid cost_basis '{row.get('cost_basis')}'"
            )
            skipped += 1
            continue

        account_type = row.get("account_type", "brokerage") or "brokerage"
        if account_type not in VALID_ACCOUNT_TYPES:
            logger.warning(
                "Row %d (%s): unknown account_type '%s', defaulting to 'brokerage'",
                row_num, symbol, account_type,
            )
            account_type = "brokerage"

        notes = row.get("notes") or None

        try:
            holding = Holding(
                symbol=symbol,
                shares=shares,
                cost_basis=cost_basis,
                account_type=account_type,
                notes=notes,
            )
            holdings.append(holding)
        except ValueError as e:
            errors.append(f"Row {row_num} ({symbol}): {e}")
            skipped += 1

    return ImportResult(holdings=holdings, errors=errors, skipped=skipped)
