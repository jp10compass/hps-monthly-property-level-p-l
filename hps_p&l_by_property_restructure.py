import re
import streamlit as st
import pandas as pd

st.set_page_config(page_title="HPS P&L Restructure", layout="wide")
st.title("HPS P&L by Property — Multi-Month Restructure")


### ── HELPERS ─────────────────────────────────────────────────────────────────

def convert_letter_to_index(letter):
    index = 0
    for char in letter.upper().strip():
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def get_account_label(row, label_columns):
    label = ""
    for col in label_columns:
        val = row[col]
        if pd.notna(val) and str(val).strip():
            label = str(val).strip()
    return label


def clean_owner_name(owner):
    if pd.isna(owner):
        return ""
    return " ".join(str(owner).replace("(", "").replace(")", "").split())


def normalize_property_name(name):
    if pd.isna(name):
        return name
    text = str(name).strip()
    ### Strip trailing suffixes in any order/combination:
    ###   .## (dot followed by digits, e.g. .20, .18, .25)
    ###   X+  (one or more X characters, e.g. X, XX, XXX)
    ### Only removes when preceded by a space, so mid-name X characters are safe
    text = re.sub(r'(\s+\.\d+|\s+X+)+$', '', text, flags=re.IGNORECASE).strip()
    return text


ROLLUP_ACCOUNTS = {"Gross Profit", "Net Ordinary Income", "Net Other Income"}


def is_rollup_account(account):
    if pd.isna(account):
        return True
    text = str(account).strip()
    return text == "" or text.lower().startswith("total ") or text in ROLLUP_ACCOUNTS


def process_file(df, first_data_col_idx, period_month_end):
    label_columns = df.columns[:first_data_col_idx]
    header_property = df.iloc[0]
    header_owner = df.iloc[1]
    body = df.iloc[2:].copy()

    body["Account"] = body.apply(
        lambda r: get_account_label(r, label_columns), axis=1
    )

    records = []
    n_cols = len(df.columns)

    for _, row in body.iterrows():
        account = str(row["Account"]).strip()
        if not account:
            continue
        for col_idx in range(first_data_col_idx, n_cols):
            prop_name = header_property.iloc[col_idx]
            prop_owner = header_owner.iloc[col_idx]
            prop_owner_text = "" if pd.isna(prop_owner) else str(prop_owner).strip()
            is_grand_total = col_idx == n_cols - 1
            is_owner_subtotal = "total" in prop_owner_text.lower() and not is_grand_total
            raw_prop_name = "N/A" if pd.isna(prop_name) else str(prop_name).strip()
            records.append({
                "Account": account,
                "Amount": row.iloc[col_idx],
                "Property Name": normalize_property_name(raw_prop_name),
                "Property Owner": prop_owner_text,
                "Is_Owner_Subtotal": is_owner_subtotal,
                "Is_Grand_Total": is_grand_total,
            })

    df_long = pd.DataFrame(records)
    df_long["Property Owner"] = df_long["Property Owner"].apply(clean_owner_name)

    valid = df_long.groupby("Account")["Amount"].apply(lambda s: s.notna().any())
    df_long = df_long[df_long["Account"].isin(valid[valid].index)].copy()
    df_long = df_long[~df_long["Account"].apply(is_rollup_account)].copy()
    df_long = df_long[
        (df_long["Is_Owner_Subtotal"] == False) | (df_long["Is_Grand_Total"] == True)
    ].copy()

    df_long["Accounting Period"] = period_month_end.date()
    return df_long


### ── SESSION STATE INIT ──────────────────────────────────────────────────────

if "step" not in st.session_state:
    st.session_state.step = "upload"
if "accumulated" not in st.session_state:
    st.session_state.accumulated = pd.DataFrame()
if "raw_df" not in st.session_state:
    st.session_state.raw_df = None


### ── STEP: UPLOAD ────────────────────────────────────────────────────────────

if st.session_state.step == "upload":

    if not st.session_state.accumulated.empty:
        n = st.session_state.accumulated["Accounting Period"].nunique()
        st.info(f"{n} month(s) already loaded. Upload the next file.")

    uploaded_file = st.file_uploader("Upload Excel file", type=["xlsx", "xls"])

    if uploaded_file is not None:
        st.session_state.raw_df = pd.read_excel(uploaded_file, header=None)
        st.session_state.step = "inputs"
        st.rerun()


### ── STEP: INPUTS ────────────────────────────────────────────────────────────

elif st.session_state.step == "inputs":

    st.subheader("File Preview")
    st.dataframe(st.session_state.raw_df.head(10), use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        col_letter = st.text_input("First data column letter (e.g. H)")
    with col2:
        date_input = st.text_input("Accounting period date (MM/DD/YYYY)")

    if st.button("Process", type="primary"):
        if not col_letter:
            st.error("Enter the first data column letter.")
        elif not date_input:
            st.error("Enter the accounting period date.")
        else:
            try:
                col_idx = convert_letter_to_index(col_letter)
                period_date = pd.to_datetime(date_input, format="%m/%d/%Y")
                period_month_end = period_date + pd.offsets.MonthEnd(0)

                with st.spinner(f"Processing {period_month_end.strftime('%B %Y')}..."):
                    month_df = process_file(
                        st.session_state.raw_df, col_idx, period_month_end
                    )

                st.session_state.accumulated = pd.concat(
                    [st.session_state.accumulated, month_df], ignore_index=True
                )
                st.session_state.raw_df = None
                st.session_state.step = "action"
                st.rerun()

            except ValueError as e:
                st.error(f"Error: {e} — check your date format (MM/DD/YYYY).")


### ── STEP: ACTION ────────────────────────────────────────────────────────────

elif st.session_state.step == "action":

    acc = st.session_state.accumulated
    n_months = acc["Accounting Period"].nunique()

    st.success(f"{n_months} month(s) loaded — {len(acc):,} total rows")
    st.dataframe(acc, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Add Another Month", use_container_width=True):
            st.session_state.step = "upload"
            st.rerun()
    with col2:
        if st.button("Export", type="primary", use_container_width=True):
            st.session_state.step = "export"
            st.rerun()


### ── STEP: EXPORT ────────────────────────────────────────────────────────────

elif st.session_state.step == "export":

    acc = st.session_state.accumulated
    n_months = acc["Accounting Period"].nunique()

    st.success(f"Ready to export — {len(acc):,} rows across {n_months} month(s)")

    ### ── Version 1: Long format ──────────────────────────────────────────────
    st.subheader("Version 1 — Long Format")
    st.caption(
        "One row per Account + Property + Month combination. "
        "Best for filtering, pivot tables, and loading into databases or BI tools."
    )
    acc_long = acc[(acc["Amount"].notna()) & (acc["Amount"] != 0) & (acc["Is_Grand_Total"] == False)].copy()
    acc_long = acc_long.drop(columns=["Is_Owner_Subtotal", "Is_Grand_Total"])

    ### Normalize Property Owner to first-seen name per property (same logic as wide format)
    owner_lookup_long = acc_long.groupby("Property Name")["Property Owner"].first()
    acc_long["Property Owner"] = acc_long["Property Name"].map(owner_lookup_long)
    st.dataframe(acc_long, use_container_width=True)

    csv_long = acc_long.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download Long Format CSV",
        data=csv_long,
        file_name="hps_pnl_long.csv",
        mime="text/csv",
        type="primary",
        use_container_width=True,
    )

    st.divider()

    ### ── Version 2: Wide format ──────────────────────────────────────────────
    st.subheader("Version 2 — Wide Format")
    st.caption(
        "One row per Account + Property combination, with one column per month sorted earliest to latest. "
        "Best for side-by-side month comparison and sharing as a report."
    )

    ### Build wide format from the same accumulated data
    ### Convert Accounting Period to string in YYYY/MM/DD format for column headers
    acc_wide = acc.copy()
    acc_wide["Accounting Period"] = acc_wide["Accounting Period"].astype(str).str.replace("-", "/")

    ### Treat 0 as blank — Excel stores empty cells as 0, not as actual values
    acc_wide["Amount"] = acc_wide["Amount"].replace(0, pd.NA)

    ### Sort months chronologically before pivoting
    sorted_months = sorted(acc_wide["Accounting Period"].unique())

    ### Lock in the first-seen owner name per property — avoids duplicate rows
    ### caused by owner name variations across files (suffix, name order, etc.)
    owner_lookup = acc_wide.groupby("Property Name")["Property Owner"].first().reset_index()

    ### Pivot on Account + Property Name only to guarantee one row per combination
    wide_df = acc_wide.pivot_table(
        index=["Account", "Property Name"],
        columns="Accounting Period",
        values="Amount",
        aggfunc="first",
    ).reset_index()

    wide_df.columns.name = None

    ### Enforce chronological column order
    wide_df = wide_df[["Account", "Property Name"] + sorted_months]

    ### Add Property Owner back using the first-seen name
    wide_df = wide_df.merge(owner_lookup, on="Property Name", how="left")

    ### Final column order: Account, Property Name, Property Owner, then months
    wide_df = wide_df[["Account", "Property Name", "Property Owner"] + sorted_months]

    st.dataframe(wide_df, use_container_width=True)

    csv_wide = wide_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download Wide Format CSV",
        data=csv_wide,
        file_name="hps_pnl_wide.csv",
        mime="text/csv",
        type="primary",
        use_container_width=True,
    )

    st.divider()

    if st.button("Restart", use_container_width=True):
        st.session_state.accumulated = pd.DataFrame()
        st.session_state.raw_df = None
        st.session_state.step = "upload"
        st.rerun()
