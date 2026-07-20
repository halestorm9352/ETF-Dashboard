import re
from typing import Any


ETF_VEHICLE = "ETF"
MUTUAL_FUND_SHARE_CLASS = "Mutual fund share class"
UNKNOWN_VEHICLE = "Other / unknown"
VEHICLE_TYPES = (ETF_VEHICLE, MUTUAL_FUND_SHARE_CLASS, UNKNOWN_VEHICLE)


def is_share_class_name(value: Any) -> bool:
    name = str(value or "").strip()
    class_label = r"Class\s+[A-Z0-9]+(?:-[A-Z0-9]+)*(?:\s+Shares)?"
    named_class = r"(?:Institutional|Investor|Retail)\s+Class(?:\s+Shares)?"
    return bool(
        re.fullmatch(rf"(?:{class_label}|{named_class})", name, re.IGNORECASE)
        or re.search(rf":\s*{class_label}$", name, re.IGNORECASE)
    )


def is_mutual_fund_ticker(value: Any) -> bool:
    ticker = str(value or "").strip().upper()
    return bool(re.fullmatch(r"[A-Z]{4}X", ticker))


def is_authoritative_mapped_ticker(row: dict[str, Any]) -> bool:
    if row.get("ticker_source") != "sec_fund_ticker_map":
        return False
    ticker = str(row.get("ticker", "") or "").strip().upper()
    return bool(re.fullmatch(r"[A-Z0-9.\-]{1,10}", ticker))


def is_vehicle_ticker_present(row: dict[str, Any]) -> bool:
    if is_authoritative_mapped_ticker(row):
        return True
    return (
        row.get("vehicle") == MUTUAL_FUND_SHARE_CLASS
        and is_mutual_fund_ticker(row.get("ticker", ""))
    )


def classify_vehicle(row: dict[str, Any]) -> str:
    ticker = str(row.get("ticker", "") or "").strip().upper()
    class_name = str(row.get("class_name", "") or row.get("etf_name", "")).strip()
    series_name = str(row.get("series_name", "") or "").strip()

    if is_mutual_fund_ticker(ticker) or is_share_class_name(class_name):
        return MUTUAL_FUND_SHARE_CLASS

    combined_name = f"{series_name} {class_name}".upper()
    if re.search(r"\bETF\b", combined_name):
        return ETF_VEHICLE
    if re.search(r"\b(?:BULL|BEAR)\s+\dX\s+SHARES\b", combined_name):
        return ETF_VEHICLE
    if re.fullmatch(r"[A-Z]{1,4}", ticker):
        return ETF_VEHICLE
    return UNKNOWN_VEHICLE


def uses_parent_series_identity(row: dict[str, Any]) -> bool:
    series_id = str(row.get("series_id", "") or "").strip()
    if not series_id:
        return False
    return classify_vehicle(row) == MUTUAL_FUND_SHARE_CLASS or is_share_class_name(
        row.get("class_name", "")
    )
