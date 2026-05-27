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
    has_dept = "_group_by_dept" in df.columns and bool(df["_group_by_dept"].any())
    group_keys = ["Accounting Period", "Account", "Property", "Department"] if has_dept else ["Accounting Period", "Account", "Property"]
    numeric_cols = [c for c in df.select_dtypes(include="number").columns if c != "_group_by_dept"]
    df = df.groupby(group_keys, as_index=False)[numeric_cols].sum()
    df["Owner"] = df["Property"].map(owner_lookup)
    df["_group_by_dept"] = has_dept
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


TOOL3_DEFAULT_ACCOUNT_MAP = {
    "Booking Income": "Booking Income",
    "Cleaning Fees": "Cleaning Income",
    "Credit Card Income": "Credit Card Income",
    "Damage Income": "Damage Income",
    "Linen Program Fee Income": "Linen Program Fee",
    "Management Fee Income": "Management Fee Income",
    "Markup - Appliance": "Markups",
    "Markup - Cleaning": "Markups",
    "Markup - Guest Expenses": "Markups",
    "Markup - Locks": "Markups",
    "Markup - Materials": "Markups",
    "Markup - Postage": "Markups",
    "Markup - Repair Labor": "Markups",
    "Markup - Unit Inventory": "Markups",
    "Markups": "Markups",
    "Airbnb Booking Fee": "Other Revenue",
    "Booking.com Commission": "Other Revenue",
    "Break Fee Income": "Other Revenue",
    "Cancellation Insurance": "Other Revenue",
    "Chargeback": "Other Revenue",
    "Early/Late Fee Check In/Out": "Other Revenue",
    "Expedia Commission": "Other Revenue",
    "Float Fees Forfeited": "Other Revenue",
    "Home Away Commission": "Other Revenue",
    "Lease Application Fee": "Other Revenue",
    "Occupancy Violation": "Other Revenue",
    "Pool Heating": "Other Revenue",
    "Referral Income": "Other Revenue",
    "Refund Cancellation": "Other Revenue",
    "Reimbursed Income": "Other Revenue",
    "Rentals United Commission": "Other Revenue",
    "Storage Locker Rental Income": "Other Revenue",
    "Trip Insurance": "Other Revenue",
    "Pet Fees": "Pet Fees",
    "Rent": "Rental Income",
    "Credit Card Fees": "Other COGS",
    "Guest Expenses": "Other COGS",
    "Linen Program Fee": "Other COGS",
    "Owners Proceed": "Owners Rental Proceeds",
    "Owners Reimbursement": "Other COGS",
    "Health Insurance": "Insurance",
    "Property-Liability Insurance": "Insurance",
    "Bad debt": "Other G&A",
    "Bank Service Charges": "Other G&A",
    "Break Fee": "Other G&A",
    "Delivery": "Other G&A",
    "Lease Application Fees": "Other G&A",
    "Licenses and Permits": "Licenses and Permits",
    "Management Fee Adjustment": "Other G&A",
    "Management Fees": "Management Fee Expense",
    "Not Collected Sales Tax": "Other G&A",
    "Office Supplies": "Other G&A",
    "Penalty Expense": "Other G&A",
    "Postage & Delivery": "Other G&A",
    "Rent Expenses": "Other G&A",
    "Accounting Fees": "Professional Fees",
    "Consulting": "Professional Fees",
    "Legal Fees": "Professional Fees",
    "Professional Fees": "Professional Fees",
    "VA Subcontractor": "Professional Fees",
    "Cable/Internet": "Telephone & Utilities",
    "Fax": "Telephone & Utilities",
    "Phone": "Telephone & Utilities",
    "Entertainment": "Travel & Entertainment",
    "Meals": "Travel & Entertainment",
    "Travel": "Travel & Entertainment",
    "Electricity & Heat": "Telephone & Utilities",
    "Gas Utility": "Telephone & Utilities",
    "Water & Sewer": "Telephone & Utilities",
    "Paid Time Off": "Payroll Costs",
    "Payroll Accounting": "Payroll Costs",
    "Payroll Bonus": "Payroll Costs",
    "Payroll Clearing": "Payroll Costs",
    "Payroll Fees": "Payroll Costs",
    "Payroll Guest Services": "Payroll Costs",
    "Payroll Inter Company": "Payroll Costs",
    "Payroll Marketing": "Payroll Costs",
    "Payroll Mgmt": "Payroll Costs",
    "Payroll Operations": "Payroll Costs",
    "Payroll Overtime": "Payroll Costs",
    "Payroll Owner Services": "Payroll Costs",
    "Payroll Taxes": "Payroll Costs",
    "Payroll Vacation": "Payroll Costs",
    "Worker's Compensation": "Payroll Costs",
    "Conference": "Professional Development",
    "Training": "Professional Development",
    "Recruiting Expense": "Recruiting Expense",
    "Cleaning Inspector": "Cleaning",
    "Cleaning Supplies": "Cleaning",
    "Cleaning Units": "Cleaning",
    "Garage Cleaning": "Cleaning",
    "Laundry Attendant Payroll": "Cleaning",
    "Linen Inventory": "Cleaning",
    "Unit Inventory": "Cleaning",
    "AC Filters": "Maintenance",
    "Appliances": "Maintenance",
    "Auto Allowance": "Maintenance",
    "Consumables": "Maintenance",
    "Electric": "Maintenance",
    "Furniture & Decorations": "Maintenance",
    "Garage Maintenance": "Maintenance",
    "HVAC Repairs": "Maintenance",
    "Landscape Expense": "Maintenance",
    "Materials": "Maintenance",
    "Moveable": "Maintenance",
    "Plumbing": "Maintenance",
    "Repairs": "Maintenance",
    "Subcontractor": "Maintenance",
    "Trash Removal": "Maintenance",
    "Cleaning Slippage": "Slippage",
    "Inventory Slippage": "Slippage",
    "Linen Slippage": "Slippage",
    "Maintenance Slippage": "Slippage",
    "Equipment Rental": "Transportation & Equipment",
    "Gas & Maintenance": "Transportation & Equipment",
    "Truck Rental": "Transportation & Equipment",
    "Advertising": "Ad & Marketing",
    "Marketing": "Ad & Marketing",
    "OTA Fees": "Ad & Marketing",
    "Referral Bonus": "Ad & Marketing",
    "Sign on Bonus": "Ad & Marketing",
    "Staff Promotion": "Ad & Marketing",
    "Staging Bonus": "Ad & Marketing",
    "Unit Photos": "Ad & Marketing",
    "Website Fees": "Ad & Marketing",
    "Dues and Subscriptions": "Dues and Subscriptions",
    "Software": "Software",
    "Admin OH Expenses Split by Unit": "Other Expense",
    "Insurance Reimbursement": "Other Expense",
    "Interest Expense": "Other Expense",
    "R&M OH Expenses Split by Unit": "Other Expense",
    "Transfer FROM Float Fees": "Other Expense",
    "Transfer FROM Reserve Funds": "Other Expense",
    "Transfer FROM Unit": "Other Expense",
    "Write Off": "Other Expense",
    "Interest Income": "Other Income",
    "Other Income Drew": "Other Income",
    "Tax Collection Allowance": "Other Income",
    "Transfer TO Float Fees": "Other Income",
    "Transfer TO Reserve Fund": "Other Income",
    "Transfer TO Unit": "Other Income",
}

TOOL3_EXPENSE_CATEGORIES = sorted(set(TOOL3_DEFAULT_ACCOUNT_MAP.values()))


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
if "tool2_group_by_dept" not in st.session_state:
    st.session_state.tool2_group_by_dept = False
if "tool2_owner_type_map" not in st.session_state:
    st.session_state.tool2_owner_type_map = None  # None = skipped, dict = applied
if "tool2_raw_amount_sum" not in st.session_state:
    st.session_state.tool2_raw_amount_sum = 0.0
if "tool3_step" not in st.session_state:
    st.session_state.tool3_step = "upload"
if "tool3_accumulated" not in st.session_state:
    st.session_state.tool3_accumulated = pd.DataFrame()
if "tool3_merges" not in st.session_state:
    st.session_state.tool3_merges = []
if "tool3_group_by_dept" not in st.session_state:
    st.session_state.tool3_group_by_dept = False
if "tool3_owner_type_map" not in st.session_state:
    st.session_state.tool3_owner_type_map = None
if "tool3_raw_amount_sum" not in st.session_state:
    st.session_state.tool3_raw_amount_sum = 0.0
if "tool3_account_map" not in st.session_state:
    st.session_state.tool3_account_map = None


### ── MENU ────────────────────────────────────────────────────────────────────

def go_home():
    st.session_state.tool = None
    st.session_state.step = "upload"
    st.session_state.accumulated = pd.DataFrame()
    st.session_state.raw_df = None
    st.session_state.tool2_step = "upload"
    st.session_state.tool2_accumulated = pd.DataFrame()
    st.session_state.tool2_merges = []
    st.session_state.tool2_group_by_dept = False
    st.session_state.tool2_owner_type_map = None
    st.session_state.tool2_raw_amount_sum = 0.0
    st.session_state.tool3_step = "upload"
    st.session_state.tool3_accumulated = pd.DataFrame()
    st.session_state.tool3_merges = []
    st.session_state.tool3_group_by_dept = False
    st.session_state.tool3_owner_type_map = None
    st.session_state.tool3_raw_amount_sum = 0.0
    st.session_state.tool3_account_map = None


if st.session_state.tool is None:
    st.title("HPS Tools")
    st.write("Select a tool to get started.")
    st.divider()

    col1, col2, col3 = st.columns(3)
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
    with col3:
        st.subheader("Company Expenses Data Prep")
        st.caption("Company Expenses Data Prep")
        if st.button("Open", key="open_tool3", use_container_width=True, type="primary"):
            st.session_state.tool = "tool3"
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

        if st.session_state.tool2_accumulated.empty:
            checked = st.checkbox("Group by Department", value=st.session_state.tool2_group_by_dept)
            st.session_state.tool2_group_by_dept = checked
        else:
            dept_label = "on" if st.session_state.tool2_group_by_dept else "off"
            st.info(f"Department grouping is **{dept_label}** (set on first upload).")

        group_by_dept = st.session_state.tool2_group_by_dept

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
                df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
                df["Accounting Period"] = df["Date"] + pd.offsets.MonthEnd(0)
                df = df[df["Accounting Period"].notna()].reset_index(drop=True)

                # Fill missing Department so groupby doesn't silently drop those rows
                if group_by_dept and "Department" in df.columns:
                    df["Department"] = df["Department"].fillna("Unassigned")

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

                # Capture raw amount sum before grouping for reconciliation
                st.session_state.tool2_raw_amount_sum += df["Amount"].sum(min_count=1) if "Amount" in df.columns else 0.0

                # Lock first-seen Owner per Property before grouping
                owner_lookup = df.groupby("Property")["Owner"].first()

                # Group by Accounting Period + Account + Property, sum numeric columns
                group_keys = ["Accounting Period", "Account", "Property", "Department"] if group_by_dept else ["Accounting Period", "Account", "Property"]
                numeric_cols = df.select_dtypes(include="number").columns.tolist()
                df = df.groupby(group_keys, as_index=False)[numeric_cols].sum()
                df["Owner"] = df["Property"].map(owner_lookup)
                df["_group_by_dept"] = group_by_dept

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
            if st.button("Continue →", type="primary", use_container_width=True):
                st.session_state.tool2_owner_type_map = None
                st.session_state.tool2_step = "owner_type"
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

    # ── STEP: OWNER TYPE MAPPING ──────────────────────────────────────────────

    elif st.session_state.tool2_step == "owner_type":

        OWNED_DEFAULT = {"CBTS LP", "CIF LP", "PBC LP", "KES LP", "CBC LP", "CinCB LP", "SinCB LP"}
        MGMT_DEFAULT = {"All FL Units"}

        st.subheader("Map Property Owner Type")
        st.caption(
            "Assign each Owner to a category. Everything not listed below is mapped as **Third Party**."
        )

        all_owners = sorted(st.session_state.tool2_accumulated["Owner"].dropna().unique().tolist())

        # Build working map from session state or defaults
        if st.session_state.tool2_owner_type_map is None:
            working_map = {}
            for o in all_owners:
                if o in OWNED_DEFAULT:
                    working_map[o] = "Owned"
                elif o in MGMT_DEFAULT:
                    working_map[o] = "SICB Management"
                else:
                    working_map[o] = "Third Party"
        else:
            working_map = dict(st.session_state.tool2_owner_type_map)
            for o in all_owners:
                if o not in working_map:
                    working_map[o] = "Third Party"

        st.write("**Current mapping** (only Owned and SICB Management shown — all others are Third Party):")

        owned_owners = [o for o, t in working_map.items() if t == "Owned"]
        mgmt_owners = [o for o, t in working_map.items() if t == "SICB Management"]

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Owned**")
            for o in owned_owners:
                st.markdown(f"- `{o}`")
        with col2:
            st.markdown("**SICB Management**")
            for o in mgmt_owners:
                st.markdown(f"- `{o}`")

        st.divider()
        st.write("**Add or change a mapping:**")

        third_party_owners = [o for o in all_owners if working_map.get(o) == "Third Party"]

        if third_party_owners:
            col_a, col_b = st.columns(2)
            with col_a:
                owner_to_add = st.selectbox(
                    "Select an Owner (currently Third Party)",
                    options=third_party_owners,
                    key="owner_type_select",
                )
            with col_b:
                new_type = st.radio(
                    "Map to",
                    options=["Owned", "SICB Management"],
                    key="owner_type_radio",
                    horizontal=True,
                )
            if st.button("Add Mapping", type="primary"):
                working_map[owner_to_add] = new_type
                st.session_state.tool2_owner_type_map = working_map
                st.rerun()
        else:
            st.info("All owners are already mapped.")

        st.divider()
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("← Back", use_container_width=True):
                st.session_state.tool2_step = "action"
                st.rerun()
        with col2:
            if st.button("Skip (no owner type column)", use_container_width=True):
                st.session_state.tool2_owner_type_map = None
                st.session_state.tool2_step = "export"
                st.rerun()
        with col3:
            if st.button("Apply & Continue →", type="primary", use_container_width=True):
                st.session_state.tool2_owner_type_map = working_map
                st.session_state.tool2_step = "export"
                st.rerun()

    # ── STEP: EXPORT ──────────────────────────────────────────────────────────

    elif st.session_state.tool2_step == "export":

        acc = st.session_state.tool2_accumulated.copy()
        n_files = acc["Accounting Period"].nunique()

        # Reconciliation check
        raw_sum = st.session_state.tool2_raw_amount_sum
        export_sum = acc["Amount"].sum(min_count=1) if "Amount" in acc.columns else 0.0
        if abs(raw_sum - export_sum) < 0.01:
            st.success(f"Reconciliation passed — Amount totals match: {raw_sum:,.2f}")
        else:
            st.error(
                f"Reconciliation failed — Raw files total: {raw_sum:,.2f} | "
                f"Export total: {export_sum:,.2f} | "
                f"Difference: {raw_sum - export_sum:,.2f}"
            )

        # Apply Property Owner Type if mapping was provided
        include_owner_type = st.session_state.tool2_owner_type_map is not None
        if include_owner_type:
            owner_type_map = st.session_state.tool2_owner_type_map
            acc["Property Owner Type"] = acc["Owner"].map(lambda o: owner_type_map.get(o, "Third Party"))

        include_dept = st.session_state.tool2_group_by_dept and "Department" in acc.columns
        base_cols = ["Accounting Period", "Account", "Department", "Property", "Owner"] if include_dept else ["Accounting Period", "Account", "Property", "Owner"]
        if include_owner_type:
            base_cols = base_cols + ["Property Owner Type", "Amount"]
        else:
            base_cols = base_cols + ["Amount"]
        columns_to_keep = base_cols
        df_export = acc[[col for col in columns_to_keep if col in acc.columns]]

        df_export = df_export.copy()
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
            st.session_state.tool2_group_by_dept = False
            st.session_state.tool2_owner_type_map = None
            st.session_state.tool2_raw_amount_sum = 0.0
            st.rerun()


### ── TOOL 3: COMPANY EXPENSES DATA PREP ─────────────────────────────────────

elif st.session_state.tool == "tool3":

    import csv

    st.title("Company Expenses Data Prep")
    if st.button("← Back to Menu", key="back_tool3"):
        go_home()
        st.rerun()

    st.divider()

    # ── STEP: UPLOAD ──────────────────────────────────────────────────────────

    if st.session_state.tool3_step == "upload":

        if not st.session_state.tool3_accumulated.empty:
            n = st.session_state.tool3_accumulated["Accounting Period"].nunique()
            st.info(f"{n} file(s) already loaded. Upload the next file.")

        uploaded_file = st.file_uploader("Upload Excel file", type=["xlsx", "xls"], key="tool3_uploader")

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
                df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
                df["Accounting Period"] = df["Date"] + pd.offsets.MonthEnd(0)
                df = df[df["Accounting Period"].notna()].reset_index(drop=True)

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

                # Capture raw amount sum for reconciliation
                st.session_state.tool3_raw_amount_sum += df["Amount"].sum(min_count=1) if "Amount" in df.columns else 0.0

            st.session_state.tool3_accumulated = pd.concat(
                [st.session_state.tool3_accumulated, df], ignore_index=True
            )
            st.session_state.tool3_step = "action"
            st.rerun()

    # ── STEP: ACTION ──────────────────────────────────────────────────────────

    elif st.session_state.tool3_step == "action":

        acc = st.session_state.tool3_accumulated
        n_files = acc["Accounting Period"].nunique()

        st.success(f"{n_files} file(s) loaded — {len(acc):,} total rows")
        st.dataframe(acc, use_container_width=True)

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Add Another File", use_container_width=True, key="tool3_add_file"):
                st.session_state.tool3_step = "upload"
                st.rerun()
        with col2:
            if st.button("Continue →", type="primary", use_container_width=True, key="tool3_continue"):
                st.session_state.tool3_step = "account_mapping"
                st.rerun()

    # ── STEP: ACCOUNT MAPPING ─────────────────────────────────────────────────

    elif st.session_state.tool3_step == "account_mapping":

        st.subheader("Map Accounts to Expense Category")
        st.caption(
            "Review the default mapping below. Accounts not in the default list are shown prominently — "
            "assign them a category before continuing."
        )

        all_accounts = sorted(st.session_state.tool3_accumulated["Account"].dropna().unique().tolist())

        # Build working map from session state or defaults
        if st.session_state.tool3_account_map is None:
            working_map = {a: TOOL3_DEFAULT_ACCOUNT_MAP.get(a, "Uncategorized") for a in all_accounts}
        else:
            working_map = dict(st.session_state.tool3_account_map)
            for a in all_accounts:
                if a not in working_map:
                    working_map[a] = TOOL3_DEFAULT_ACCOUNT_MAP.get(a, "Uncategorized")

        unmapped = [a for a in all_accounts if working_map.get(a) == "Uncategorized"]
        mapped = [a for a in all_accounts if working_map.get(a) != "Uncategorized"]

        # Show unmapped accounts prominently
        if unmapped:
            st.error(
                f"**{len(unmapped)} account(s) are unmapped and must be assigned a category before you can continue:**\n\n"
                + "\n".join(f"- `{a}`" for a in unmapped)
            )
            st.divider()
            st.write("**Assign a category to an unmapped account:**")
            col_a, col_b = st.columns(2)
            with col_a:
                account_to_map = st.selectbox(
                    "Select unmapped account",
                    options=unmapped,
                    key="tool3_unmap_select",
                )
            with col_b:
                new_cat = st.selectbox(
                    "Assign category",
                    options=TOOL3_EXPENSE_CATEGORIES,
                    key="tool3_unmap_cat",
                )
            if st.button("Map Account", type="primary", key="tool3_map_account"):
                working_map[account_to_map] = new_cat
                st.session_state.tool3_account_map = working_map
                st.rerun()
            st.divider()
        else:
            st.success(f"All {len(all_accounts)} accounts are mapped.")

        # Show current mapping grouped by category
        if mapped:
            st.write("**Current mapping (accounts in your data):**")
            by_category = {}
            for a in mapped:
                cat = working_map[a]
                by_category.setdefault(cat, []).append(a)
            for cat in sorted(by_category):
                st.markdown(f"**{cat}**")
                for a in by_category[cat]:
                    st.markdown(f"- `{a}`")

        st.divider()
        st.write("**Change an existing mapping:**")
        col_a, col_b = st.columns(2)
        with col_a:
            account_to_change = st.selectbox(
                "Select account",
                options=all_accounts,
                key="tool3_change_account",
            )
        with col_b:
            current_cat = working_map.get(account_to_change, "Uncategorized")
            cat_options = TOOL3_EXPENSE_CATEGORIES
            default_idx = cat_options.index(current_cat) if current_cat in cat_options else 0
            new_cat_change = st.selectbox(
                "New category",
                options=cat_options,
                index=default_idx,
                key="tool3_change_cat",
            )
        if st.button("Update Mapping", key="tool3_update_mapping"):
            working_map[account_to_change] = new_cat_change
            st.session_state.tool3_account_map = working_map
            st.rerun()

        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            if st.button("← Back", use_container_width=True, key="tool3_acctmap_back"):
                st.session_state.tool3_step = "action"
                st.rerun()
        with col2:
            if unmapped:
                st.button(
                    "Apply & Continue →",
                    type="primary",
                    use_container_width=True,
                    key="tool3_acctmap_apply",
                    disabled=True,
                )
                st.caption("Map all accounts above before continuing.")
            else:
                if st.button("Apply & Continue →", type="primary", use_container_width=True, key="tool3_acctmap_apply"):
                    st.session_state.tool3_account_map = working_map
                    st.session_state.tool3_step = "dept_remap"
                    st.rerun()

    # ── STEP: DEPARTMENT REMAPPING ────────────────────────────────────────────

    elif st.session_state.tool3_step == "dept_remap":

        st.subheader("Rename Department Values")
        st.caption("Each department found in your data is shown below. Edit any name you want to rename — leave as-is to keep it unchanged.")

        acc = st.session_state.tool3_accumulated
        all_departments = sorted(acc["Department"].dropna().unique().tolist()) if "Department" in acc.columns else []

        if not all_departments:
            st.info("No Department values found in the data.")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("← Back", use_container_width=True, key="tool3_dept_back"):
                    st.session_state.tool3_step = "account_mapping"
                    st.rerun()
            with col2:
                if st.button("Continue →", type="primary", use_container_width=True, key="tool3_dept_apply"):
                    st.session_state.tool3_step = "owner_type"
                    st.rerun()
        else:
            if st.session_state.get("tool3_dept_remap") is None:
                working_remap = {d: d for d in all_departments}
            else:
                working_remap = dict(st.session_state.tool3_dept_remap)
                for d in all_departments:
                    if d not in working_remap:
                        working_remap[d] = d

            sorted_depts = sorted(working_remap.keys())

            for i, dept in enumerate(sorted_depts):
                key = f"tool3_dept_input_{i}"
                if key not in st.session_state:
                    st.session_state[key] = working_remap[dept]

            st.write(f"**{len(sorted_depts)} department(s) found:**")
            cols = st.columns(2)
            for i, dept in enumerate(sorted_depts):
                with cols[i % 2]:
                    st.text_input(f"`{dept}`", key=f"tool3_dept_input_{i}")

            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                if st.button("← Back", use_container_width=True, key="tool3_dept_back"):
                    st.session_state.tool3_step = "account_mapping"
                    st.rerun()
            with col2:
                if st.button("Apply & Continue →", type="primary", use_container_width=True, key="tool3_dept_apply"):
                    new_remap = {}
                    for i, dept in enumerate(sorted_depts):
                        new_name = st.session_state.get(f"tool3_dept_input_{i}", dept).strip() or dept
                        new_remap[dept] = new_name
                    st.session_state.tool3_dept_remap = new_remap
                    st.session_state.tool3_step = "owner_type"
                    st.rerun()

    # ── STEP: OWNER TYPE MAPPING ──────────────────────────────────────────────

    elif st.session_state.tool3_step == "owner_type":

        OWNED_DEFAULT = {"CBTS LP", "CIF LP", "PBC LP", "KES LP", "CBC LP", "CinCB LP", "SinCB LP"}
        MGMT_DEFAULT = {"All FL Units"}

        st.subheader("Map Property Owner Type")
        st.caption(
            "Assign each Owner to a category. Everything not listed below is mapped as **Third Party**."
        )

        all_owners = sorted(st.session_state.tool3_accumulated["Owner"].dropna().unique().tolist())

        if st.session_state.tool3_owner_type_map is None:
            working_map = {}
            for o in all_owners:
                if o in OWNED_DEFAULT:
                    working_map[o] = "Owned"
                elif o in MGMT_DEFAULT:
                    working_map[o] = "SICB Management"
                else:
                    working_map[o] = "Third Party"
        else:
            working_map = dict(st.session_state.tool3_owner_type_map)
            for o in all_owners:
                if o not in working_map:
                    working_map[o] = "Third Party"

        st.write("**Current mapping** (only Owned and SICB Management shown — all others are Third Party):")

        owned_owners = [o for o, t in working_map.items() if t == "Owned"]
        mgmt_owners = [o for o, t in working_map.items() if t == "SICB Management"]

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Owned**")
            for o in owned_owners:
                st.markdown(f"- `{o}`")
        with col2:
            st.markdown("**SICB Management**")
            for o in mgmt_owners:
                st.markdown(f"- `{o}`")

        st.divider()
        st.write("**Add or change a mapping:**")

        third_party_owners = [o for o in all_owners if working_map.get(o) == "Third Party"]

        if third_party_owners:
            col_a, col_b = st.columns(2)
            with col_a:
                owner_to_add = st.selectbox(
                    "Select an Owner (currently Third Party)",
                    options=third_party_owners,
                    key="tool3_owner_type_select",
                )
            with col_b:
                new_type = st.radio(
                    "Map to",
                    options=["Owned", "SICB Management"],
                    key="tool3_owner_type_radio",
                    horizontal=True,
                )
            if st.button("Add Mapping", type="primary", key="tool3_add_mapping"):
                working_map[owner_to_add] = new_type
                st.session_state.tool3_owner_type_map = working_map
                st.rerun()
        else:
            st.info("All owners are already mapped.")

        st.divider()
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("← Back", use_container_width=True, key="tool3_owner_back"):
                st.session_state.tool3_step = "dept_remap"
                st.rerun()
        with col2:
            if st.button("Skip (no owner type column)", use_container_width=True, key="tool3_owner_skip"):
                st.session_state.tool3_owner_type_map = None
                st.session_state.tool3_step = "export"
                st.rerun()
        with col3:
            if st.button("Apply & Continue →", type="primary", use_container_width=True, key="tool3_owner_apply"):
                st.session_state.tool3_owner_type_map = working_map
                st.session_state.tool3_step = "export"
                st.rerun()

    # ── STEP: EXPORT ──────────────────────────────────────────────────────────

    elif st.session_state.tool3_step == "export":

        acc = st.session_state.tool3_accumulated.copy()
        n_files = acc["Accounting Period"].nunique()

        # Reconciliation check
        raw_sum = st.session_state.tool3_raw_amount_sum
        export_sum = acc["Amount"].sum(min_count=1) if "Amount" in acc.columns else 0.0
        if abs(raw_sum - export_sum) < 0.01:
            st.success(f"Reconciliation passed — Amount totals match: {raw_sum:,.2f}")
        else:
            st.error(
                f"Reconciliation failed — Raw files total: {raw_sum:,.2f} | "
                f"Export total: {export_sum:,.2f} | "
                f"Difference: {raw_sum - export_sum:,.2f}"
            )

        # Apply Expense Category from account mapping
        account_map = st.session_state.tool3_account_map or {}
        acc["Expense Category"] = acc["Account"].map(lambda a: account_map.get(a, "Uncategorized"))

        # Apply Property Owner Type if mapping was provided
        include_owner_type = st.session_state.tool3_owner_type_map is not None
        if include_owner_type:
            owner_type_map = st.session_state.tool3_owner_type_map
            acc["Property Owner Type"] = acc["Owner"].map(lambda o: owner_type_map.get(o, "Third Party"))

        # Apply Department remap if provided
        if st.session_state.get("tool3_dept_remap") and "Department" in acc.columns:
            dept_remap = st.session_state.tool3_dept_remap
            acc["Department"] = acc["Department"].map(
                lambda d: dept_remap.get(str(d).strip(), str(d)) if pd.notna(d) else d
            )

        # ── FILTER BY ACCOUNTING PERIOD ───────────────────────────────────────
        all_periods = sorted(acc["Accounting Period"].dropna().unique().tolist(), key=lambda x: str(x))

        st.subheader("Filter by Accounting Period")
        st.caption("All periods are selected by default — deselect any you want to exclude from the export.")

        if "tool3_period_multiselect" not in st.session_state:
            st.session_state["tool3_period_multiselect"] = all_periods
        else:
            valid_p = [p for p in st.session_state["tool3_period_multiselect"] if p in all_periods]
            if set(valid_p) != set(st.session_state["tool3_period_multiselect"]):
                st.session_state["tool3_period_multiselect"] = all_periods

        col_sel_p, col_desel_p = st.columns(2)
        with col_sel_p:
            if st.button("Select All", key="tool3_period_select_all", use_container_width=True):
                st.session_state["tool3_period_multiselect"] = all_periods
                st.rerun()
        with col_desel_p:
            if st.button("Deselect All", key="tool3_period_desel_all", use_container_width=True):
                st.session_state["tool3_period_multiselect"] = []
                st.rerun()

        selected_periods = st.multiselect(
            "Accounting Periods to include in export",
            options=all_periods,
            key="tool3_period_multiselect",
            format_func=lambda x: str(x),
        )

        acc = acc[acc["Accounting Period"].isin(selected_periods)].copy()

        st.divider()

        # ── FILTER BY EXPENSE CATEGORY ────────────────────────────────────────
        all_expense_categories = sorted(acc["Expense Category"].dropna().unique().tolist())

        st.subheader("Filter by Expense Category")
        st.caption("All categories are selected by default — deselect any you want to exclude from the export.")

        if "tool3_cat_multiselect" not in st.session_state:
            st.session_state["tool3_cat_multiselect"] = all_expense_categories
        else:
            valid = [c for c in st.session_state["tool3_cat_multiselect"] if c in all_expense_categories]
            if set(valid) != set(st.session_state["tool3_cat_multiselect"]):
                st.session_state["tool3_cat_multiselect"] = all_expense_categories

        col_sel, col_desel = st.columns(2)
        with col_sel:
            if st.button("Select All", key="tool3_cat_select_all", use_container_width=True):
                st.session_state["tool3_cat_multiselect"] = all_expense_categories
                st.rerun()
        with col_desel:
            if st.button("Deselect All", key="tool3_cat_desel_all", use_container_width=True):
                st.session_state["tool3_cat_multiselect"] = []
                st.rerun()

        selected_categories = st.multiselect(
            "Expense Categories to include in export",
            options=all_expense_categories,
            key="tool3_cat_multiselect",
        )

        acc = acc[acc["Expense Category"].isin(selected_categories)].copy()

        st.divider()

        columns_to_keep = ["Accounting Period", "Account", "Department", "Property", "Owner"]
        if include_owner_type:
            columns_to_keep.append("Property Owner Type")
        columns_to_keep += ["Expense Category", "Memo", "Source Name", "Amount"]

        df_export = acc[[col for col in columns_to_keep if col in acc.columns]].copy()

        df_export["Owner"] = '="' + df_export["Owner"].astype(str).str.replace('"', '""') + '"'
        df_export["Property"] = '="' + df_export["Property"].astype(str).str.replace('"', '""') + '"'

        csv_data = df_export.to_csv(index=False, quoting=csv.QUOTE_MINIMAL).encode("utf-8")

        if not selected_periods or not selected_categories:
            st.warning("No periods or categories selected — select at least one of each above to export.")
        else:
            n_sel_p = len(selected_periods)
            n_tot_p = len(all_periods)
            n_sel_c = len(selected_categories)
            n_tot_c = len(all_expense_categories)
            period_label = f"all {n_tot_p} periods" if n_sel_p == n_tot_p else f"{n_sel_p} of {n_tot_p} periods"
            category_label = f"all {n_tot_c} categories" if n_sel_c == n_tot_c else f"{n_sel_c} of {n_tot_c} categories"
            st.success(f"Ready to export — {len(df_export):,} rows · {period_label} · {category_label}")
            st.dataframe(df_export, use_container_width=True)

            st.download_button(
                label="Download CSV",
                data=csv_data,
                file_name="company_expenses.csv",
                mime="text/csv",
                type="primary",
                use_container_width=True,
            )

        st.divider()

        if st.button("Restart", use_container_width=True, key="tool3_restart"):
            st.session_state.tool3_step = "upload"
            st.session_state.tool3_accumulated = pd.DataFrame()
            st.session_state.tool3_merges = []
            st.session_state.tool3_group_by_dept = False
            st.session_state.tool3_owner_type_map = None
            st.session_state.tool3_raw_amount_sum = 0.0
            st.session_state.tool3_account_map = None
            st.session_state.tool3_dept_remap = None
            for k in [k for k in st.session_state if k.startswith("tool3_dept_input_")]:
                del st.session_state[k]
            st.session_state.pop("tool3_period_multiselect", None)
            st.session_state.pop("tool3_cat_multiselect", None)
            st.rerun()
