from datetime import datetime
from typing import Any

import pandas as pd

from config import SERIES_NEW_MONTHS
from sec_parsers import sanitize_ticker
from vehicle_classifier import ETF_VEHICLE, is_vehicle_ticker_present


INITIAL_REVIEW = "Initial review"
UPCOMING_LAUNCH = "Upcoming launch"
RECENTLY_LAUNCHED = "Recently launched"
LAUNCHED_STALE = "Launched (stale)"
EXISTING_FUND_AMENDMENT = "Existing fund amendment"
ROUTINE_485B_UPDATE = "Routine 485(b) update"
EFFECTIVE_AMENDMENT = "Effective (amendment)"
TIMING_UNDETECTED = "Timing undetected"
RECENTLY_LAUNCHED_WINDOW_DAYS = 30

SERIES_AGE_PIPELINE_STATUSES = {
    UPCOMING_LAUNCH,
    RECENTLY_LAUNCHED,
    LAUNCHED_STALE,
}
DEFAULT_VISIBLE_STATUSES = {
    INITIAL_REVIEW,
    UPCOMING_LAUNCH,
    RECENTLY_LAUNCHED,
}
HIDDEN_BY_DEFAULT_STATUSES = {
    LAUNCHED_STALE,
    EXISTING_FUND_AMENDMENT,
    ROUTINE_485B_UPDATE,
    EFFECTIVE_AMENDMENT,
    TIMING_UNDETECTED,
}


def classify_filing_stage(form):
    form_value = str(form or "").upper()
    if form_value in {"S-1", "N-1A"}:
        return "Initial filing"
    if form_value == "485APOS":
        return "Rule 485(a) amendment"
    if form_value == "485BPOS":
        return "Rule 485(b) amendment"
    return "Filing"


def earliest_auto_effective_date(row):
    filing_date = row.get("date")
    if pd.isna(filing_date):
        return pd.NaT

    designated_date = str(row.get("designated_effective_date", "") or "").strip()
    if designated_date:
        parsed_date = pd.to_datetime(designated_date, errors="coerce")
        if not pd.isna(parsed_date):
            return parsed_date

    effectiveness_days = row.get("effectiveness_days")
    parsed_days = pd.to_numeric(effectiveness_days, errors="coerce")
    if not pd.isna(parsed_days):
        return filing_date + pd.Timedelta(days=int(parsed_days))
    return pd.NaT


def filing_form_history(row) -> list[str]:
    history = str(row.get("filing_form_history", "") or "")
    forms = [form.strip().upper() for form in history.split("->") if form.strip()]
    if not forms:
        form_value = str(row.get("form", "") or "").strip().upper()
        if form_value:
            forms.append(form_value)
    return forms


def readiness_status(row, today):
    readiness_date = row.get("earliest_auto_effective_date")
    form_value = str(row.get("form", "")).upper()

    if form_value in {"S-1", "N-1A"}:
        return INITIAL_REVIEW
    if pd.isna(readiness_date):
        return TIMING_UNDETECTED

    history = filing_form_history(row)
    is_new_pipeline = (
        bool(history)
        and history[0] in {"S-1", "N-1A", "485APOS"}
        and row.get("vehicle") == ETF_VEHICLE
    )
    effective_date = readiness_date.date()
    if is_new_pipeline:
        if effective_date > today:
            return UPCOMING_LAUNCH
        days_since_effective = (today - effective_date).days
        if days_since_effective <= RECENTLY_LAUNCHED_WINDOW_DAYS:
            return RECENTLY_LAUNCHED
        return LAUNCHED_STALE
    if history and all(form == "485BPOS" for form in history):
        return ROUTINE_485B_UPDATE
    return EFFECTIVE_AMENDMENT


def _needs_ticker(row) -> bool:
    return not (
        is_vehicle_ticker_present(row)
        or sanitize_ticker(row.get("ticker", "")) != "Not Listed"
    )


def requires_series_age_lookup(row) -> bool:
    readiness = str(row.get("launch_readiness", "") or "")
    if readiness in SERIES_AGE_PIPELINE_STATUSES:
        return True
    return (
        readiness == TIMING_UNDETECTED
        and str(row.get("form", "") or "").upper() in {"485APOS", "485BPOS"}
    )


def series_ids_requiring_age_lookup(df: pd.DataFrame) -> list[str]:
    if df.empty or "series_id" not in df.columns:
        return []
    return sorted(
        {
            str(row.get("series_id", "") or "").strip().upper()
            for _, row in df.iterrows()
            if requires_series_age_lookup(row)
            and str(row.get("series_id", "") or "").strip()
        }
    )


def _is_existing_series(
    first_filing_date: Any,
    search_start_date: Any,
    series_new_months: int,
) -> bool:
    first_date = pd.to_datetime(first_filing_date, errors="coerce")
    search_start = pd.to_datetime(search_start_date, errors="coerce")
    if pd.isna(first_date) or pd.isna(search_start):
        return False
    cutoff = search_start - pd.DateOffset(months=series_new_months)
    return first_date < cutoff


def _has_prior_effectiveness(row) -> bool:
    value = row.get("prior_effective_485bpos", False)
    return value is True or str(value).strip().lower() in {"1", "true", "yes"}


def add_launch_readiness_columns(
    df,
    *,
    series_first_filing_dates: dict[str, Any] | None = None,
    search_start_date: Any = None,
    series_new_months: int = SERIES_NEW_MONTHS,
    today=None,
):
    enriched_df = df.copy()
    if enriched_df.empty:
        enriched_df["filing_stage"] = pd.Series(dtype="object")
        enriched_df["earliest_auto_effective_date"] = pd.Series(
            dtype="datetime64[ns]"
        )
        enriched_df["launch_readiness"] = pd.Series(dtype="object")
        enriched_df["needs_ticker"] = pd.Series(dtype="bool")
        enriched_df["days_to_readiness"] = pd.Series(dtype="object")
        return enriched_df

    today = today or datetime.today().date()
    enriched_df["filing_stage"] = enriched_df["form"].apply(classify_filing_stage)
    enriched_df["earliest_auto_effective_date"] = enriched_df.apply(
        earliest_auto_effective_date,
        axis=1,
    )
    enriched_df["launch_readiness"] = enriched_df.apply(
        lambda row: readiness_status(row, today),
        axis=1,
    )
    enriched_df["needs_ticker"] = enriched_df.apply(_needs_ticker, axis=1)
    if search_start_date is not None:
        normalized_dates = {
            str(series_id or "").strip().upper(): first_date
            for series_id, first_date in (series_first_filing_dates or {}).items()
        }
        existing_mask = enriched_df.apply(
            lambda row: (
                requires_series_age_lookup(row)
                and (
                    _has_prior_effectiveness(row)
                    or _is_existing_series(
                        normalized_dates.get(
                            str(row.get("series_id", "") or "").strip().upper()
                        ),
                        search_start_date,
                        series_new_months,
                    )
                )
            ),
            axis=1,
        )
        enriched_df.loc[existing_mask, "launch_readiness"] = EXISTING_FUND_AMENDMENT
    enriched_df["days_to_readiness"] = enriched_df["earliest_auto_effective_date"].apply(
        lambda value: "" if pd.isna(value) else (value.date() - today).days
    )
    return enriched_df
