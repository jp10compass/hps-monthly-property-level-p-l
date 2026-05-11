import re
import streamlit as st
import pandas as pd

st.set_page_config(page_title="HPS Tools", layout="wide")


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
    text = re.sub(r'(\s+\.\d+|\s+X+)+$', '', text, flags=re.IGNORECASE).strip()
    return text


def apply_property_merges(df, merges):
    rename_map = {}
    for group in merges:
        canonical = group["canonical"]
        for variant in group["variants"]:
            if variant != canonical:
                rename_map[variant] = canonical
    if not rename_map:
        return df
    df = df.copy()
    df["Property"] = df["Property"].replace(rename_map)
    owner_lookup = df.groupby("Property")["Owner"].first()
    group_keys = ["Accounting Period", "Account", "Property"]
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    df = df.groupby(group_keys, as_index=False)[numeric_cols].sum()
    df["Owner"] = df["Property"].map(owner_lookup)
    return df


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

if "tool" not in st.session_state:
    st.session_state.tool = None
if "step" not in st.session_state:
    st.session_state.step = "upload"
if "accumulated" not in st.session_state:
    st.session_state.accumulated = pd.DataFrame()
if "raw_df" not in st.session_state:
    st.session_state.raw_df = None
if "tool2_step" not in st.session_state:
    st.session_state.tool2_step = "upload"
if "tool2_accumulated" not in st.session_state:
    st.session_state.tool2_accumulated = pd.DataFrame()
if "tool2_merges" not in st.session_state:
    st.session_state.tool2_merges = []


### ── MENU ────────────────────────────────────────────────────────────────────

def go_home():
    st.session_state.tool = None
    st.session_state.step = "upload"
    st.session_state.accumulated = pd.DataFrame()
    st.session_state.raw_df = None
    st.session_state.tool2_step = "upload"
    st.session_state.tool2_accumulated = pd.DataFrame()
    st.session_state.tool2_merges = []


if st.session_state.tool is None:
    st.title("HPS Tools")
    st.write("Select a tool to get started.")
    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("P&L by Property Data - Based on Monthly P&L by Property")
        st.caption("P&L by Property Data - Based on Monthly P&L by Property")
        if st.button("Open", key="open_pnl", use_container_width=True, type="primary"):
            st.session_state.tool = "pnl_restructure"
            st.rerun()
    with col2:
        st.subheader("P&L by Property Data - Based on GL Report")
        st.caption("P&L by Property Data - Based on GL Report")
        if st.button("Open", key="open_tool2", use_container_width=True, type="primary"):
            st.session_state.tool = "tool2"
            st.rerun()


### ── TOOL 1: P&L BY PROPERTY RESTRUCTURE ────────────────────────────────────

elif st.session_state.tool == "pnl_restructure":

    st.title("P&L by Property Data - Based on Monthly P&L by Property")
    if st.button("← Back to Menu", key="back_pnl"):
        go_home()
        st.rerun()

    st.divider()

    # ── STEP: UPLOAD ──────────────────────────────────────────────────────────

    if st.session_state.step == "upload":

        if not st.session_state.accumulated.empty:
            n = st.session_state.accumulated["Accounting Period"].nunique()
            st.info(f"{n} month(s) already loaded. Upload the next file.")

        uploaded_file = st.file_uploader("Upload Excel file", type=["xlsx", "xls"])

        if uploaded_file is not None:
            st.session_state.raw_df = pd.read_excel(uploaded_file, header=None)
            st.session_state.step = "inputs"
            st.rerun()

    # ── STEP: INPUTS ──────────────────────────────────────────────────────────

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

    # ── STEP: ACTION ──────────────────────────────────────────────────────────

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

    # ── STEP: EXPORT ──────────────────────────────────────────────────────────

    elif st.session_state.step == "export":

        acc = st.session_state.accumulated
        n_months = acc["Accounting Period"].nunique()

        st.success(f"Ready to export — {len(acc):,} rows across {n_months} month(s)")

        st.subheader("Version 1 — Long Format")
        st.caption(
            "One row per Account + Property + Month combination. "
            "Best for filtering, pivot tables, and loading into databases or BI tools."
        )
        acc_long = acc[(acc["Amount"].notna()) & (acc["Amount"] != 0) & (acc["Is_Grand_Total"] == False)].copy()
        acc_long = acc_long.drop(columns=["Is_Owner_Subtotal", "Is_Grand_Total"])

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

        st.subheader("Version 2 — Wide Format")
        st.caption(
            "One row per Account + Property combination, with one column per month sorted earliest to latest. "
            "Best for side-by-side month comparison and sharing as a report."
        )

        acc_wide = acc.copy()
        acc_wide["Accounting Period"] = acc_wide["Accounting Period"].astype(str).str.replace("-", "/")
        acc_wide["Amount"] = acc_wide["Amount"].replace(0, pd.NA)

        sorted_months = sorted(acc_wide["Accounting Period"].unique())

        owner_lookup = acc_wide.groupby("Property Name")["Property Owner"].first().reset_index()

        wide_df = acc_wide.pivot_table(
            index=["Account", "Property Name"],
            columns="Accounting Period",
            values="Amount",
            aggfunc="first",
        ).reset_index()

        wide_df.columns.name = None
        wide_df = wide_df[["Account", "Property Name"] + sorted_months]
        wide_df = wide_df.merge(owner_lookup, on="Property Name", how="left")
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


### ── TOOL 2: P&L BY PROPERTY DATA - BASED ON GL REPORT ──────────────────────

elif st.session_state.tool == "tool2":

    import csv

    st.title("P&L by Property Data - Based on GL Report")
    if st.button("← Back to Menu", key="back_tool2"):
        go_home()
        st.rerun()

    st.divider()

    # ── STEP: UPLOAD ──────────────────────────────────────────────────────────

    if st.session_state.tool2_step == "upload":

        if not st.session_state.tool2_accumulated.empty:
            n = st.session_state.tool2_accumulated["Accounting Period"].nunique()
            st.info(f"{n} file(s) already loaded. Upload the next file.")

        uploaded_file = st.file_uploader("Upload Excel file", type=["xlsx", "xls"])

        if uploaded_file is not None:
            with st.spinner("Processing..."):
                df = pd.read_excel(uploaded_file, header=None)

                # Remove first 3 rows, use 4th row as header
                df = df.iloc[3:].reset_index(drop=True)
                df.columns = df.iloc[0]
                df = df[1:].reset_index(drop=True)

                # Remove first 4 columns
                df = df.iloc[:, 4:]

                # Remove rows where Account is empty
                df.columns = df.columns.str.strip()
                df = df[df["Account"].notna()]
                df = df[df["Account"] != ""]
                df = df.reset_index(drop=True)

                # Create Accounting Period from Date
                df["Date"] = pd.to_datetime(df["Date"])
                df["Accounting Period"] = df["Date"] + pd.offsets.MonthEnd(0)

                # Create Owner and Property from Name / Class
                owners = []
                properties = []
                for _, row in df.iterrows():
                    name_value = str(row["Name"])
                    class_value = str(row["Class"])
                    if ":" in name_value:
                        parts = name_value.split(":", 1)
                        owners.append(parts[0].strip())
                        properties.append(parts[1].strip())
                    elif ":" in class_value:
                        parts = class_value.split(":", 1)
                        owners.append(parts[0].strip())
                        properties.append(parts[1].strip())
                    else:
                        owners.append(class_value.strip())
                        properties.append(class_value.strip())

                df["Owner"] = owners
                df["Property"] = properties

                # Clean Owner and Property
                df["Owner"] = df["Owner"].str.replace(" -C$", "", regex=True).str.strip().str.replace(r"\s+", " ", regex=True)
                df["Property"] = df["Property"].str.replace("XXX", "", regex=False).str.replace(r"\.\d{2}", "", regex=True).str.strip().str.replace(r"\s+", " ", regex=True)

                # Force Amount to numeric in case it was read as text
                if "Amount" in df.columns:
                    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce")

                # Lock first-seen Owner per Property before grouping
                owner_lookup = df.groupby("Property")["Owner"].first()

                # Group by Accounting Period + Account + Property, sum numeric columns
                group_keys = ["Accounting Period", "Account", "Property", "Department"]
                numeric_cols = df.select_dtypes(include="number").columns.tolist()
                df = df.groupby(group_keys, as_index=False)[numeric_cols].sum()
                df["Owner"] = df["Property"].map(owner_lookup)

            st.session_state.tool2_accumulated = pd.concat(
                [st.session_state.tool2_accumulated, df], ignore_index=True
            )
            st.session_state.tool2_step = "action"
            st.rerun()

    # ── STEP: ACTION ──────────────────────────────────────────────────────────

    elif st.session_state.tool2_step == "action":

        acc = st.session_state.tool2_accumulated
        n_files = acc["Accounting Period"].nunique()

        st.success(f"{n_files} file(s) loaded — {len(acc):,} total rows")
        st.dataframe(acc, use_container_width=True)

        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("Add Another File", use_container_width=True):
                st.session_state.tool2_step = "upload"
                st.rerun()
        with col2:
            if st.button("Merge Properties", use_container_width=True):
                st.session_state.tool2_step = "merge"
                st.rerun()
        with col3:
            if st.button("Export", type="primary", use_container_width=True):
                st.session_state.tool2_step = "export"
                st.rerun()

    # ── STEP: MERGE ───────────────────────────────────────────────────────────

    elif st.session_state.tool2_step == "merge":

        st.subheader("Merge Properties")
        st.caption("Group property names that refer to the same property. Select all variants, then pick which name to keep.")

        all_properties = sorted(st.session_state.tool2_accumulated["Property"].unique().tolist())

        if st.session_state.tool2_merges:
            st.write("**Current merge groups:**")
            for i, group in enumerate(st.session_state.tool2_merges):
                col1, col2 = st.columns([6, 1])
                with col1:
                    variants_str = ", ".join(f"`{v}`" for v in group["variants"] if v != group["canonical"])
                    st.write(f"{variants_str} → **{group['canonical']}**")
                with col2:
                    if st.button("Remove", key=f"remove_merge_{i}"):
                        st.session_state.tool2_merges.pop(i)
                        st.rerun()
            st.divider()

        st.write("**Add a new merge group:**")
        n = len(st.session_state.tool2_merges)
        selected_variants = st.multiselect(
            "Select property names to merge",
            options=all_properties,
            key=f"merge_variants_{n}",
        )

        if len(selected_variants) >= 2:
            canonical = st.radio(
                "Which name to keep?",
                options=selected_variants,
                key=f"merge_canonical_{n}",
            )
            if st.button("Add Group", type="primary"):
                st.session_state.tool2_merges.append({
                    "variants": selected_variants,
                    "canonical": canonical,
                })
                st.rerun()

        st.divider()

        col1, col2 = st.columns(2)
        with col1:
            if st.button("← Back", use_container_width=True):
                st.session_state.tool2_step = "action"
                st.rerun()
        with col2:
            if st.button("Apply & Continue", type="primary", use_container_width=True):
                if st.session_state.tool2_merges:
                    st.session_state.tool2_accumulated = apply_property_merges(
                        st.session_state.tool2_accumulated,
                        st.session_state.tool2_merges,
                    )
                st.session_state.tool2_step = "action"
                st.rerun()

    # ── STEP: EXPORT ──────────────────────────────────────────────────────────

    elif st.session_state.tool2_step == "export":

        acc = st.session_state.tool2_accumulated.copy()
        n_files = acc["Accounting Period"].nunique()

        columns_to_keep = ["Accounting Period", "Account", "Department", "Property", "Owner", "Amount"]
        df_export = acc[[col for col in columns_to_keep if col in acc.columns]]

        df_export["Owner"] = '="' + df_export["Owner"].astype(str).str.replace('"', '""') + '"'
        df_export["Property"] = '="' + df_export["Property"].astype(str).str.replace('"', '""') + '"'

        csv_data = df_export.to_csv(index=False, quoting=csv.QUOTE_MINIMAL).encode("utf-8")

        st.success(f"Ready to export — {len(df_export):,} rows across {n_files} file(s)")
        st.dataframe(df_export, use_container_width=True)

        st.download_button(
            label="Download CSV",
            data=csv_data,
            file_name="cleaned_data.csv",
            mime="text/csv",
            type="primary",
            use_container_width=True,
        )

        st.divider()

        if st.button("Restart", use_container_width=True):
            st.session_state.tool2_step = "upload"
            st.session_state.tool2_accumulated = pd.DataFrame()
            st.session_state.tool2_merges = []
            st.rerun()
