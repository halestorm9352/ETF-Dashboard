from datetime import datetime

import pandas as pd

from sec_parsers import sanitize_ticker
from vehicle_classifier import ETF_VEHICLE, is_vehicle_ticker_present


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
    ticker_present = is_vehicle_ticker_present(row) or (
        sanitize_ticker(row.get("ticker", "")) != "Not Listed"
    )
    readiness_date = row.get("earliest_auto_effective_date")
    form_value = str(row.get("form", "")).upper()

    if form_value in {"S-1", "N-1A"}:
        return "Initial review"
    if pd.isna(readiness_date):
        return "Timing not detected"
    if not ticker_present:
        return "Needs ticker"
    if readiness_date.date() <= today:
        history = filing_form_history(row)
        if (
            history
            and history[0] in {"S-1", "N-1A", "485APOS"}
            and row.get("vehicle") == ETF_VEHICLE
        ):
            return "Launch candidate"
        if history and all(form == "485BPOS" for form in history):
            return "Effective (485(b) update)"
        return "Effective (amendment)"
    return "Waiting on effectiveness"


def add_launch_readiness_columns(df):
    enriched_df = df.copy()
    if enriched_df.empty:
        enriched_df["filing_stage"] = pd.Series(dtype="object")
        enriched_df["earliest_auto_effective_date"] = pd.Series(
            dtype="datetime64[ns]"
        )
        enriched_df["launch_readiness"] = pd.Series(dtype="object")
        enriched_df["days_to_readiness"] = pd.Series(dtype="object")
        return enriched_df

    today = datetime.today().date()
    enriched_df["filing_stage"] = enriched_df["form"].apply(classify_filing_stage)
    enriched_df["earliest_auto_effective_date"] = enriched_df.apply(
        earliest_auto_effective_date,
        axis=1,
    )
    enriched_df["launch_readiness"] = enriched_df.apply(
        lambda row: readiness_status(row, today),
        axis=1,
    )
    enriched_df["days_to_readiness"] = enriched_df["earliest_auto_effective_date"].apply(
        lambda value: "" if pd.isna(value) else (value.date() - today).days
    )
    return enriched_df
