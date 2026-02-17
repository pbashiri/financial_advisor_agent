"""Portfolio CRUD endpoints."""

import logging

from fastapi import APIRouter, HTTPException, Request, UploadFile

from ...portfolio.csv_import import parse_holdings_csv
from ...portfolio.models import Holding
from ...portfolio.storage import PortfolioStorage

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_CSV_SIZE_BYTES = 1_000_000  # 1 MB


def _get_storage(request: Request) -> PortfolioStorage:
    return request.app.state.storage


@router.get("", response_model=list[Holding])
async def get_holdings(request: Request):
    """Return all portfolio holdings."""
    storage = _get_storage(request)
    return await storage.get_holdings()


@router.post("", response_model=Holding, status_code=201)
async def upsert_holding(holding: Holding, request: Request):
    """Add or update a holding."""
    storage = _get_storage(request)
    await storage.upsert_holding(holding)
    holdings = await storage.get_holdings()
    for h in holdings:
        if h.symbol == holding.symbol:
            return h
    raise HTTPException(status_code=500, detail="Upsert succeeded but holding not found")


@router.delete("/{symbol}", status_code=204)
async def delete_holding(symbol: str, request: Request):
    """Remove a holding by symbol."""
    storage = _get_storage(request)
    deleted = await storage.delete_holding(symbol)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Holding '{symbol.upper()}' not found")


@router.post("/import")
async def import_csv(file: UploadFile, request: Request):
    """Import holdings from a CSV file.

    CSV format:
        symbol,shares,cost_basis,account_type,notes
        AAPL,50,150.00,brokerage,Core tech
    """
    storage = _get_storage(request)

    content = await file.read()
    if len(content) > MAX_CSV_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="CSV file is too large (max 1MB)")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded")

    result = parse_holdings_csv(text)

    if not result.holdings and result.errors:
        raise HTTPException(status_code=400, detail={"errors": result.errors})

    imported = 0
    for holding in result.holdings:
        await storage.upsert_holding(holding)
        imported += 1

    return {
        "imported": imported,
        "skipped": result.skipped,
        "errors": result.errors,
    }


@router.post("/import/text")
async def import_csv_text(request: Request):
    """Import holdings from CSV text in the request body (for bot usage)."""
    storage = _get_storage(request)
    body = await request.body()
    if len(body) > MAX_CSV_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="CSV body is too large (max 1MB)")
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Body must be UTF-8 encoded")

    result = parse_holdings_csv(text)

    if not result.holdings and result.errors:
        raise HTTPException(status_code=400, detail={"errors": result.errors})

    imported = 0
    for holding in result.holdings:
        await storage.upsert_holding(holding)
        imported += 1

    return {
        "imported": imported,
        "skipped": result.skipped,
        "errors": result.errors,
    }
