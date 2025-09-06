from __future__ import annotations


def df_to_csv_bytes(df) -> bytes:
    return df.to_csv().encode("utf-8")
