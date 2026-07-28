"""yfinance provider — primary for US (true dividend+split adjusted close)."""
from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd

from .base import DataProvider, DataProviderError, normalize

logger = logging.getLogger(__name__)


class YFinanceProvider(DataProvider):
    name = "yfinance"

    def get_ohlcv(
        self, ticker: str, market: str, start: date, end: date
    ) -> pd.DataFrame:
        import yfinance as yf

        try:
            df = yf.download(
                ticker,
                start=str(start),
                # yfinance treats `end` as exclusive.
                end=str(end + timedelta(days=1)),
                auto_adjust=False,
                actions=False,
                progress=False,
                threads=False,
            )
        except Exception as exc:  # noqa: BLE001
            raise DataProviderError(f"yfinance failed for {ticker}: {exc}") from exc

        if df is None or df.empty:
            raise DataProviderError(f"yfinance returned no rows for {ticker}")
        return normalize(df, provider="yfinance")

    def list_universe(self, market: str) -> pd.DataFrame:
        # yfinance has no listing endpoint; universe discovery goes through FDR.
        raise DataProviderError("yfinance does not provide universe listings")


def top_us_etfs(limit: int = 200) -> pd.DataFrame:
    """A curated large-AUM ETF list.

    There is no free, stable "ETFs by AUM" endpoint, so Phase 1 ships a static list of
    the largest/most-traded funds and takes the first `limit`.
    """
    symbols = [
        # Broad US equity
        "SPY", "IVV", "VOO", "VTI", "QQQ", "QQQM", "IWM", "IWB", "IWV", "ITOT",
        "SCHB", "SCHX", "SPLG", "SPTM", "VV", "VONE", "VTHR", "MGC", "DIA", "OEF",
        # Style / factor
        "VUG", "VTV", "IWF", "IWD", "IVW", "IVE", "SCHG", "SCHV", "MTUM", "QUAL",
        "USMV", "VLUE", "SIZE", "SPHQ", "SPLV", "RSP", "VYM", "SCHD", "DVY", "SDY",
        "NOBL", "HDV", "DGRO", "VIG", "SPYD", "SPYG", "SPYV", "PRF", "COWZ", "CALF",
        # Mid / small cap
        "VO", "VB", "IJH", "IJR", "MDY", "SCHM", "SCHA", "VBR", "VBK", "IWN",
        "IWO", "IWS", "IWP", "VOE", "VOT", "XSLV", "AVUV", "DFAT", "SLYV", "SLYG",
        # Sector
        "XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE",
        "XLC", "VGT", "VFH", "VDE", "VHT", "VIS", "VCR", "VDC", "VPU", "VAW",
        "VNQ", "VOX", "SMH", "SOXX", "IBB", "XBI", "IYR", "ITB", "XHB", "KRE",
        "KBE", "OIH", "XOP", "XME", "GDX", "GDXJ", "JETS", "TAN", "ICLN", "PAVE",
        # International
        "VEA", "VWO", "IEFA", "IEMG", "EFA", "EEM", "VXUS", "IXUS", "ACWI", "VT",
        "SCHF", "SCHE", "SPDW", "SPEM", "EWJ", "EWY", "EWT", "EWZ", "EWU", "EWG",
        "EWC", "EWA", "EWH", "EWS", "INDA", "FXI", "MCHI", "KWEB", "ASHR", "EZU",
        "IEUR", "VGK", "VPL", "AAXJ", "EMXC", "DXJ", "HEFA", "IQLT", "EFV", "EFG",
        # Fixed income
        "AGG", "BND", "BNDX", "VCIT", "VCSH", "LQD", "HYG", "JNK", "TLT", "IEF",
        "SHY", "GOVT", "TIP", "VTIP", "SCHP", "MUB", "VTEB", "BSV", "BIV", "BLV",
        "IGSB", "IGIB", "USIG", "SPTL", "SPTI", "SPSB", "SJNK", "SHYG", "EMB", "PCY",
        "BIL", "SGOV", "SHV", "ICSH", "MINT", "NEAR", "FLOT", "FLRN", "STIP", "VGIT",
        # Commodities / alternatives / thematic
        "GLD", "IAU", "GLDM", "SLV", "PDBC", "DBC", "USO", "UNG", "PPLT", "PALL",
        "ARKK", "ARKG", "ARKW", "ARKQ", "ARKF", "BOTZ", "ROBO", "LIT", "REMX", "URA",
        "SKYY", "HACK", "CIBR", "FINX", "IPAY", "ESPO", "HERO", "MOAT", "FDN", "IGV",
    ]
    seen: list[str] = []
    for s in symbols:
        if s not in seen:
            seen.append(s)
    return pd.DataFrame(
        {
            "ticker": seen[:limit],
            "name_en": seen[:limit],
            "name_ko": None,
            "market": "US",
            "sector": "ETF",
            "industry": "ETF",
            "board": "ETF",
        }
    )
