# =====================================================
# STEP 1: IMPORT LIBRARIES
# =====================================================

import pandas as pd
import datetime as dt
import numpy as np
import re

try:
    import gspread  # type: ignore[import]
    from google.oauth2.service_account import Credentials  # type: ignore[import]
    from gspread_dataframe import set_with_dataframe, get_as_dataframe  # type: ignore[import]
    from gspread_formatting import CellFormat, format_cell_range  # type: ignore[import]
except ModuleNotFoundError as e:
    # If gspread and related packages are not installed, provide fallbacks
    # so static analysis/linting won't fail immediately. At runtime the
    # script will still require these packages to access Google Sheets.
    gspread = None
    Credentials = None
    CellFormat = None
    def set_with_dataframe(*args, **kwargs):
        raise ModuleNotFoundError("gspread-dataframe is required to set dataframes to Google Sheets")
    def get_as_dataframe(*args, **kwargs):
        raise ModuleNotFoundError("gspread-dataframe is required to read dataframes from Google Sheets")
    # Import of gspread-formatting not available; provide no-op names
    def format_cell_range(*args, **kwargs):
        return None
    print(
        "Warning: Missing required Google Sheets packages. "
        "Install via pip: pip install gspread google-auth gspread-dataframe gspread-formatting"
    )

# If Google Sheets packages are not available, stop execution with a clear error.
if gspread is None or Credentials is None:
    raise ModuleNotFoundError(
        "Missing required Google Sheets packages. "
        "Install via pip: pip install gspread google-auth gspread-dataframe gspread-formatting"
    )


# =====================================================
# STEP 2: GOOGLE SHEETS AUTHENTICATION
# =====================================================

import streamlit as st

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_info(
    st.secrets["gcp_service_account"],
    scopes=SCOPES
)

gc = gspread.authorize(creds)


# =====================================================
# STEP 3: SHEET URLS
# =====================================================

SCREENING_SHEET_URL = "https://docs.google.com/spreadsheets/d/1BAByzSVh6gq03R_KcsWyFwISgM52NgWxcI_nXHzwRTw/edit?usp=sharing"

RECRUITMENT_SHEET_URL = "https://docs.google.com/spreadsheets/d/1WjvZ2eZEoN42WLlNoelD-aH8oOtwvYoKtgy7eZdPZmo/edit?usp=sharing"

VACCINATION_SHEET_URL = "https://docs.google.com/spreadsheets/d/1_SB16T3QUfZJhXMyEPw5HuWUwUScIUAzfzezbFj4e-Q/edit?usp=sharing"

DEST_SHEET_URL = "https://docs.google.com/spreadsheets/d/1z3ey_vJrTNtbLAPlzRXYWEJFRY4_-89nvJLwmSBXRfs/edit?usp=sharing"

DEST_SHEET_URL_lab = "https://docs.google.com/spreadsheets/d/1uEaBqs8DoSF4X88ERq6KfXo54Abj7qtft_0lx1dxaxU/edit?usp=sharing"


# =====================================================
# STEP 4: OPEN SHEETS
# =====================================================

screening_sheet = gc.open_by_url(SCREENING_SHEET_URL).worksheet("data")

recruitment_sheet = gc.open_by_url(RECRUITMENT_SHEET_URL).worksheet("data")

vaccination_sheet = gc.open_by_url(VACCINATION_SHEET_URL).worksheet("data")

dest_sheet = gc.open_by_url(DEST_SHEET_URL).worksheet("Database")

dest_sheet_lab = gc.open_by_url(DEST_SHEET_URL_lab).worksheet("SCREENING")

cohort_sheet = gc.open_by_url(DEST_SHEET_URL_lab).worksheet("COHORT Follow-up")

aravind_sheet = gc.open_by_url(DEST_SHEET_URL_lab).worksheet("Aravind details")


# =====================================================
# STEP 5: READ SOURCE DATA
# =====================================================

# Screening
df_screening = get_as_dataframe(screening_sheet).dropna(how="all")

df_screening.columns = (
    df_screening.columns
    .astype(str)
    .str.strip()
    .str.lower()
)

df_screening = df_screening.drop(
    columns=["age"],
    errors="ignore"
)

# =====================================================
# RECRUITMENT DATA
# =====================================================

df_recruitment = get_as_dataframe(recruitment_sheet).dropna(how="all")

df_recruitment.columns = (
    df_recruitment.columns
    .astype(str)
    .str.strip()
    .str.lower()
)

# Change date_enrol to recruit_date if your recruitment sheet uses recruit_date
required_cols = {"study_id","recruitment_id", "date_enrol"}

if required_cols.issubset(df_recruitment.columns):

    df_recruitment_date = (
        df_recruitment[["study_id","recruitment_id", "date_enrol"]]
        .rename(columns={
            "study_id": "Screening ID",
            "date_enrol": "Date of Recruitment",
            "recruitment_id": "Recruitment ID"
        })
    )

    df_recruitment_date["Date of Recruitment"] = pd.to_datetime(
        df_recruitment_date["Date of Recruitment"],
        errors="coerce"
    )

else:
    raise ValueError(
        f"Required columns not found in Recruitment sheet. "
        f"Available columns: {df_recruitment.columns.tolist()}"
    )

# =====================================================
# VACCINATION DATA
# =====================================================

df_vaccination = get_as_dataframe(vaccination_sheet).dropna(how="all")

df_vaccination.columns = (
    df_vaccination.columns
    .astype(str)
    .str.strip()
    .str.lower()
)

# =====================================================
# READ ARAVIND DETAILS
# =====================================================

df_aravind = get_as_dataframe(aravind_sheet).dropna(how="all")

# Standardize column names
df_aravind.columns = (
    df_aravind.columns
    .astype(str)
    .str.strip()
    .str.lower()
)

# Check actual column names
#print("Aravind columns:", df_aravind.columns.tolist())

df_aravind["available dates"] = pd.to_datetime(
    df_aravind["available dates"],
    format="%d-%b-%y",
    errors="coerce"
)

available_dates = sorted(
    pd.to_datetime(df_aravind["available dates"], errors="coerce")
    .dropna()
    .tolist()
)

# =====================================================
# STEP 6: COLUMN MAPPING
# =====================================================

columns_map = {
    "study_id": "Screening ID",
    "sample_date": "Date of Collection",
    "name": "Name",
    "hospital_no": "Hospital ID",
    "gender": "Gender",
    "parent_guardian_name": "Parents name",
    "dob": "DOB",
    "address": "Location",
    "contact_no": "Phone no.1",
    "contact_no_2": "Phone no.2",
    "sample_col_str": "Incharge",
    "family_willing_visit": "willing to visit"
}

available_columns = [
    c for c in columns_map
    if c in df_screening.columns
]

df_partial = (
    df_screening[available_columns]
    .rename(columns=columns_map)
)

# =====================================================
# MERGE RECRUITMENT DATE
# =====================================================

df_partial = (
    df_screening[available_columns]
    .rename(columns=columns_map)
)

df_partial = df_partial.merge(
    df_recruitment_date,
    on="Screening ID",
    how="left"
)

# Move Recruitment ID after Screening ID
if "Recruitment ID" in df_partial.columns:

    recruitment_col = df_partial.pop("Recruitment ID")

    insert_pos = (
        df_partial.columns.get_loc("Screening ID") + 1
    )

    df_partial.insert(
        insert_pos,
        "Recruitment ID",
        recruitment_col
    )

# Place Date of Recruitment after Date of Collection
if (
    "Date of Recruitment" in df_partial.columns and
    "Date of Collection" in df_partial.columns
):

    recruit_col = df_partial.pop("Date of Recruitment")

    insert_pos = (
        df_partial.columns.get_loc("Date of Collection") + 1
    )

    df_partial.insert(insert_pos,"Date of Recruitment",recruit_col)
    
# =====================================================
# STEP 7: WILLING TO VISIT MAPPING
# =====================================================

if "willing to visit" in df_partial.columns:

    df_partial["willing to visit"] = (
        df_partial["willing to visit"]
        .map({
            1: "Yes",
            0: "No",
            "1": "Yes",
            "0": "No"
        })
    )


# =====================================================
# STEP 8: AGE CALCULATION
# =====================================================

if "DOB" in df_partial.columns:

    df_partial["DOB"] = pd.to_datetime(
        df_partial["DOB"],
        errors="coerce"
    )

    def calculate_age(born):

        if pd.isnull(born):
            return ""

        today = dt.date.today()

        years = today.year - born.year
        months = today.month - born.month

        if today.day < born.day:
            months -= 1

        if months < 0:
            years -= 1
            months += 12

        if years < 1:
            return f"{months} m"
        else:
            return f"{years} y"

    df_partial["Age"] = (
        df_partial["DOB"]
        .apply(calculate_age)
    )

    df_partial.drop(
        columns=["DOB"],
        inplace=True
    )


# =====================================================
# STEP 9: INSERT USER ENTRY COLUMNS
# =====================================================

# Insert after Date of Recruitment
if "Date of Recruitment" in df_partial.columns:
    insert_pos = (
        df_partial.columns.get_loc("Date of Recruitment") + 1
    )
else:
    insert_pos = (
        df_partial.columns.get_loc("Date of Collection") + 1
    )

if "Result Type" not in df_partial.columns:
    df_partial.insert(insert_pos, "Result Type", "")

if "Result" not in df_partial.columns:
    df_partial.insert(insert_pos + 1, "Result", "")

if "Cohort" not in df_partial.columns:
    df_partial.insert(insert_pos + 2, "Cohort", "")

# Move Age after Hospital ID
if "Age" in df_partial.columns:
    age_col = df_partial.pop("Age")

    df_partial.insert(
        df_partial.columns.get_loc("Hospital ID") + 1,
        "Age",
        age_col
    )


# =====================================================
# STEP 10: CLEAN TEXT
# =====================================================

df_partial["Gender"] = df_partial["Gender"].replace({
    1: "Male",
    2: "Female",
    "1": "Male",
    "2": "Female"
})

for col in [
    "Name",
    "Parents name",
    "Location"
]:
    if col in df_partial.columns:
        df_partial[col] = (
            df_partial[col]
            .astype(str)
            .str.strip()
            .str.title()
        )


df_partial["Location"] = (
    df_partial["Location"]
    .apply(
        lambda x:
        re.split(r"[,\s]+", x.strip())[-1].title()
        if isinstance(x, str)
        else ""
    )
)


# =====================================================
# STEP 11: ADD SERIAL NUMBER
# =====================================================

df_partial.insert(
    0,
    "S.No",
    range(1, len(df_partial) + 1)
)


# =====================================================
# STEP 12: READ LAB SHEET
# =====================================================

df_lab_existing = (get_as_dataframe(dest_sheet_lab).dropna(how="all"))

df_lab_existing.columns = (
    df_lab_existing.columns
    .astype(str)
    .str.strip()
)

df_cohort = get_as_dataframe(cohort_sheet).dropna(how="all")

df_cohort.columns = (
    df_cohort.columns
    .astype(str)
    .str.strip()
    .str.lower()
)

df_cohort["screening id"] = (
    df_cohort["screening id"]
    .astype(str)
    .str.strip()
    .str.upper()
)

df_cohort = df_cohort.drop_duplicates(
    "screening id",
    keep="last"
)


# =====================================================
# STEP 13: DEDUPLICATE LAB SHEET
# =====================================================

df_lab_dedup = (
    df_lab_existing
    .dropna(subset=["Screening ID"])
    .drop_duplicates(
        subset=["Screening ID"],
        keep="last"
    )
)


# =====================================================
# STEP 14: USER COLUMNS
# =====================================================

lab_user_cols = [
    "Incharge",
    "Result Type",
    "Result",
    "willing to visit",
    "Decision",
    "Reason",
    "Date of confirmed visit",
    "Cohort"
]


# =====================================================
# STEP 15: MERGE LAB DATA
# =====================================================

common_cols = [
    "Screening ID"
] + [
    c for c in lab_user_cols
    if c in df_lab_dedup.columns
]

df_partial = df_partial.merge(
    df_lab_dedup[common_cols],
    on="Screening ID",
    how="left",
    suffixes=("", "_lab")
)

for col in lab_user_cols:

    lab_col = f"{col}_lab"

    if lab_col in df_partial.columns:

        df_partial[col] = (
            df_partial[lab_col]
            .combine_first(df_partial[col])
        )

        df_partial.drop(
            columns=[lab_col],
            inplace=True
        )

# =====================================================
# FILL COHORT FROM COHORT FOLLOW-UP
# =====================================================

if (
    "screening id" in df_cohort.columns and
    "cohort" in df_cohort.columns
):

    cohort_map = (
        df_cohort
        .set_index("screening id")["cohort"]
    )

    df_partial["Cohort"] = (
        df_partial["Screening ID"]
        .astype(str)
        .str.strip()
        .str.upper()
        .map(cohort_map)
        .fillna("")
    )

# =====================================================
# DECISION & DATE OF CONFIRMED VISIT (SCREENING + COHORT)
# =====================================================

# Clean IDs
df_lab_dedup["Screening ID"] = (
    df_lab_dedup["Screening ID"].astype(str).str.strip().str.upper()
)

df_cohort["screening id"] = (
    df_cohort["screening id"].astype(str).str.strip().str.upper()
)

# Clean decision values
if "Decision" in df_lab_dedup.columns:
    df_lab_dedup["Decision"] = (
        df_lab_dedup["Decision"].fillna("").astype(str).str.strip()
    )

if "decision" in df_cohort.columns:
    df_cohort["decision"] = (
        df_cohort["decision"].fillna("").astype(str).str.strip()
    )

# Clean dates
if "Date of confirmed visit" in df_lab_dedup.columns:
    df_lab_dedup["Date of confirmed visit"] = pd.to_datetime(
        df_lab_dedup["Date of confirmed visit"], errors="coerce"
    )

if "date of confirmed visit" in df_cohort.columns:
    df_cohort["date of confirmed visit"] = pd.to_datetime(
        df_cohort["date of confirmed visit"], errors="coerce"
    )

screening_lookup = (
    df_lab_dedup.set_index("Screening ID")[
        ["Decision","Date of confirmed visit"]
    ].to_dict("index")
)

cohort_lookup = (
    df_cohort.set_index("screening id")[
        ["decision","date of confirmed visit"]
    ].to_dict("index")
)

def get_decision_and_date(screening_id):
    sid = str(screening_id).strip().upper()

    s = screening_lookup.get(sid,{})
    c = cohort_lookup.get(sid,{})

    s_dec = str(s.get("Decision","")).strip()
    c_dec = str(c.get("decision","")).strip()

    if c_dec.lower() == "yes":
        return pd.Series(["Yes", c.get("date of confirmed visit", pd.NaT)])

    if s_dec.lower() == "yes":
        return pd.Series(["Yes", s.get("Date of confirmed visit", pd.NaT)])

    if c_dec != "":
        return pd.Series([c_dec, pd.NaT])

    if s_dec != "":
        return pd.Series([s_dec, pd.NaT])

    return pd.Series(["", pd.NaT])

df_partial[["Decision","Date of confirmed visit"]] = (
    df_partial["Screening ID"].apply(get_decision_and_date)
)

print("Tracker YES:",
      (df_partial["Decision"].astype(str).str.lower()=="yes").sum())

# =====================================================
# VISIT DATE CALCULATIONS
# =====================================================

def add_days(date_value, days):
    try:
        if pd.isna(date_value):
            return pd.NaT

        date_value = pd.to_datetime(date_value, errors="coerce")

        if pd.isna(date_value):
            return pd.NaT

        return (date_value + pd.Timedelta(days=days)).date()

    except:
        return pd.NaT
    
# Ensure recruitment date is datetime
df_partial["Date of Collection"] = pd.to_datetime(
    df_partial["Date of Collection"],
    errors="coerce"
)

# Ensure Recruitment Date is datetime
df_partial["Date of Recruitment"] = pd.to_datetime(
    df_partial["Date of Recruitment"],
    errors="coerce"
)

def assign_aravind_dates(base_date):

    if pd.isna(base_date):
        return pd.Series([pd.NaT, pd.NaT])

    target_date = pd.to_datetime(base_date) + pd.Timedelta(days=7)

    valid_dates = [
        d for d in available_dates
        if pd.to_datetime(d) >= target_date
    ]

    date1 = valid_dates[0] if len(valid_dates) > 0 else pd.NaT

    if pd.notna(date1):
        next_dates = [
            d for d in available_dates
            if pd.to_datetime(d) > pd.to_datetime(date1)
        ]
        date2 = next_dates[0] if len(next_dates) > 0 else pd.NaT
    else:
        date2 = pd.NaT

    return pd.Series([date1, date2])

# =====================================================
# RECRUITED MASK
# =====================================================

recruited = (
    df_partial["Recruitment ID"]
    .fillna("")
    .astype(str)
    .str.strip()
    != ""
)

# =====================================================
# VISIT 1 (ALL RECORDS)
# =====================================================

df_partial["Visit 1 - 1D Notification"] = df_partial.apply(
    lambda row:
        add_days(row["Date of Collection"], 84)
        if str(row.get("Result Type", "")).strip().lower() == "positive"
        else (
            add_days(row["Date of Collection"], 7)
            if str(row.get("Result Type", "")).strip().lower() == "negative"
            else pd.NaT
        ),
    axis=1
)

# Aravind dates for ALL records
df_partial[
    ["Aravind Available date1", "Aravind Available date2"]
] = df_partial["Visit 1 - 1D Notification"].apply(
    assign_aravind_dates
)

# Visit 1 Dose 1 = Recruitment Date (only recruited)
df_partial["Visit 1 - Dose 1"] = pd.NaT

#df_partial.loc[recruited, "Visit 1 - Dose 1"] = pd.to_datetime(
 #   df_partial.loc[recruited, "Date of Recruitment"],
  #  errors="coerce"
#)

df_partial.loc[recruited, "Visit 1 - Dose 1"] = (
    pd.to_datetime(
        df_partial.loc[recruited, "Visit 1 - 1D Notification"]
    )
    + pd.Timedelta(days=7)
)

# =====================================================
# VISIT 2 (RECRUITED ONLY)
# =====================================================

df_partial["Visit 2 - 2D Notification"] = pd.NaT
df_partial["Visit 2 - Dose 2"] = pd.NaT

df_partial.loc[recruited, "Visit 2 - 2D Notification"] = (
    pd.to_datetime(
        df_partial.loc[recruited, "Visit 1 - Dose 1"]
    )
    + pd.Timedelta(days=21)
)

df_partial.loc[recruited, "Visit 2 - Dose 2"] = (
    pd.to_datetime(
        df_partial.loc[recruited, "Visit 2 - 2D Notification"]
    )
    + pd.Timedelta(days=7)
)

df_partial[
    ["Aravind Visit2 date1", "Aravind Visit2 date2"]
] = df_partial["Visit 2 - 2D Notification"].apply(assign_aravind_dates)

# =====================================================
# VISIT 3 (RECRUITED ONLY)
# =====================================================

df_partial["Visit 3 - S Notification"] = pd.NaT
df_partial["Visit 3 - Sample"] = pd.NaT

df_partial.loc[recruited, "Visit 3 - S Notification"] = (
    pd.to_datetime(
        df_partial.loc[recruited, "Visit 2 - Dose 2"]
    )
    + pd.Timedelta(days=21)
)

df_partial.loc[recruited, "Visit 3 - Sample"] = (
    pd.to_datetime(
        df_partial.loc[recruited, "Visit 3 - S Notification"]
    )
    + pd.Timedelta(days=7)
)

df_partial[
    ["Aravind Visit3 date1", "Aravind Visit3 date2"]
] = df_partial["Visit 3 - S Notification"].apply(assign_aravind_dates)

# =====================================================
# VISIT 4 (RECRUITED ONLY)
# =====================================================

df_partial["Visit 4 - 3D Notification"] = pd.NaT
df_partial["Visit 4 - Dose 3"] = pd.NaT

df_partial.loc[recruited, "Visit 4 - 3D Notification"] = (
    pd.to_datetime(
        df_partial.loc[recruited, "Visit 2 - Dose 2"]
    )
    + pd.Timedelta(days=358)
)

df_partial.loc[recruited, "Visit 4 - Dose 3"] = (
    pd.to_datetime(
        df_partial.loc[recruited, "Visit 4 - 3D Notification"]
    )
    + pd.Timedelta(days=7)
)

df_partial[
    ["Aravind Visit4 date1", "Aravind Visit4 date2"]
] = df_partial["Visit 4 - 3D Notification"].apply(assign_aravind_dates)

# =====================================================
# VISIT 5 (RECRUITED ONLY)
# =====================================================

df_partial["Visit 5 - S Notification"] = pd.NaT
df_partial["Visit 5 - Sample"] = pd.NaT

df_partial.loc[recruited, "Visit 5 - S Notification"] = (
    pd.to_datetime(
        df_partial.loc[recruited, "Visit 4 - Dose 3"]
    )
    + pd.Timedelta(days=21)
)

df_partial.loc[recruited, "Visit 5 - Sample"] = (
    pd.to_datetime(
        df_partial.loc[recruited, "Visit 5 - S Notification"]
    )
    + pd.Timedelta(days=7)
)

df_partial[
    ["Aravind Visit5 date1", "Aravind Visit5 date2"]
] = df_partial["Visit 5 - S Notification"].apply(assign_aravind_dates)




# =====================================================
# VISIT HIERARCHY VALIDATION (ADD HERE)
# =====================================================

df_partial["Visit_Hierarchy_Status"] = "OK"

# Convert to datetime safely (VERY IMPORTANT)
df_partial["Visit 1 - 1D Notification"] = pd.to_datetime(
    df_partial["Visit 1 - 1D Notification"], errors="coerce"
)

df_partial["Visit 2 - 2D Notification"] = pd.to_datetime(
    df_partial["Visit 2 - 2D Notification"], errors="coerce"
)

# RULE: Visit 2 must be >= Visit 1
mask_error = (
    df_partial["Visit 1 - 1D Notification"].notna() &
    df_partial["Visit 2 - 2D Notification"].notna() &
    (df_partial["Visit 2 - 2D Notification"] < df_partial["Visit 1 - 1D Notification"])
)

df_partial.loc[mask_error, "Visit_Hierarchy_Status"] = "Visit2 < Visit1 ERROR"


print("Total hierarchy errors:",
      (df_partial["Visit_Hierarchy_Status"] == "Visit2 < Visit1 ERROR").sum())

df_partial[df_partial["Visit_Hierarchy_Status"] == "Visit2 < Visit1 ERROR"][
    ["Screening ID",
     "Visit 1 - 1D Notification",
     "Visit 2 - 2D Notification"]
]


print("\n========== DATE CHECK ==========")

source_screening = set(
    df_lab_dedup.loc[
        df_lab_dedup["Date of confirmed visit"].notna(),
        "Screening ID"
    ]
    .astype(str)
    .str.strip()
    .str.upper()
)

source_cohort = set(
    df_cohort.loc[
        df_cohort["date of confirmed visit"].notna(),
        "screening id"
    ]
    .astype(str)
    .str.strip()
    .str.upper()
)

tracker_ids = set(
    df_partial.loc[
        df_partial["Date of confirmed visit"].notna(),
        "Screening ID"
    ]
    .astype(str)
    .str.strip()
    .str.upper()
)

source_ids = source_screening | source_cohort

print("SCREENING:", len(source_screening))
print("COHORT   :", len(source_cohort))
print("EXPECTED :", len(source_ids))
print("TRACKER  :", len(tracker_ids))

missing_ids = source_ids - tracker_ids

print("MISSING COUNT:", len(missing_ids))
print("MISSING IDS:", missing_ids)

screening_ids_with_date = set(
    df_lab_dedup.loc[
        df_lab_dedup["Date of confirmed visit"]
        .astype(str)
        .str.strip()
        .ne(""),
        "Screening ID"
    ]
    .astype(str)
    .str.strip()
    .str.upper()
)

cohort_ids_with_date = set(
    df_cohort.loc[
        df_cohort["date of confirmed visit"]
        .astype(str)
        .str.strip()
        .ne(""),
        "screening id"
    ]
    .astype(str)
    .str.strip()
    .str.upper()
)

print("SCREENING:", len(screening_ids_with_date))
print("COHORT   :", len(cohort_ids_with_date))
print("TOTAL    :", len(screening_ids_with_date | cohort_ids_with_date))

print(
    repr(
        df_lab_dedup.loc[
            df_lab_dedup["Screening ID"] == "CEIR-0536",
            "Date of confirmed visit"
        ].iloc[0]
    )
)

# =====================================================
# STEP 16: WRITE SCREENING CALL TRACKER
# =====================================================
date_cols = [
    "Date of Collection",
    "Date of Recruitment",
    "Visit 1 - 1D Notification",
    "Visit 1 - Dose 1",
    "Aravind Available date1",
    "Aravind Available date2",
    "Visit 2 - 2D Notification",
    "Visit 2 - Dose 2",
    "Aravind Visit2 date1",
    "Aravind Visit2 date2",
    "Visit 3 - S Notification",
    "Visit 3 - Sample",
    "Aravind Visit3 date1",
    "Aravind Visit3 date2",
    "Visit 4 - 3D Notification",
    "Visit 4 - Dose 3",
    "Aravind Visit4 date1",
    "Aravind Visit4 date2",
    "Visit 5 - S Notification",
    "Visit 5 - Sample",
    "Aravind Visit5 date1",
    "Aravind Visit5 date2",
]

if "Date of confirmed visit" in df_partial.columns:

    df_partial["Date of confirmed visit"] = (
        df_partial["Date of confirmed visit"]
        .astype(str)
        .str.strip()
        .replace("", np.nan)
    )

df_partial["Date of confirmed visit"] = pd.to_datetime(
    df_partial["Date of confirmed visit"],
    format="%Y-%m-%d",
    errors="coerce"
).dt.date

for col in date_cols:
    if col in df_partial.columns:
        #print(f"Converting: {col}")
        df_partial[col] = pd.to_datetime(
            df_partial[col],
            errors="coerce"
        ).dt.date

# =====================================================
# PRESERVE CAPTURED VISIT DATE COLUMNS
# =====================================================

df_tracker_existing = get_as_dataframe(dest_sheet).dropna(how="all")

df_tracker_existing.columns = (
    df_tracker_existing.columns
    .astype(str)
    .str.strip()
)

tracker_preserve_cols = [
    "Screening ID",
    "(V1/D1) date",
    "(V2/D2) date",
    "(V3/S) date",
    "(V4/D3) date",
    "(V5/S) date",
]

existing_cols = [
    c for c in tracker_preserve_cols
    if c in df_tracker_existing.columns
]

if existing_cols:
    df_tracker_preserve = (
        df_tracker_existing[existing_cols]
        .drop_duplicates("Screening ID", keep="last")
    )

    df_partial = df_partial.merge(
        df_tracker_preserve,
        on="Screening ID",
        how="left"
    )
        
# =====================================================
# FINAL COLUMN ORDER FIX (IMPORTANT)
# =====================================================

preferred_order = [
    "S.No",
    "Screening ID",
    "Recruitment ID",
    "Date of Collection",
    "Date of Recruitment",
    "Result Type",
    "Result",
    "Cohort",
    "Name",
    "Hospital ID",
    "Age",
    "Gender",
    "Parents name",
    "Location",
    "Phone no.1",
    "Phone no.2",
    "Incharge",
    "willing to visit",
    "Decision",
    "Reason",
    "Date of confirmed visit",

    # Captured Visit Dates
    "(V1/D1) date",
    "(V2/D2) date",
    "(V3/S) date",
    "(V4/D3) date",
    "(V5/S) date",

    # Visit 1
    "Visit 1 - 1D Notification",
    "Aravind Available date1",
    "Aravind Available date2",
    "Visit 1 - Dose 1",

    # Visit 2
    "Visit 2 - 2D Notification",
    "Aravind Visit2 date1",
    "Aravind Visit2 date2",
    "Visit 2 - Dose 2",

    # Visit 3
    "Visit 3 - S Notification",
    "Aravind Visit3 date1",
    "Aravind Visit3 date2",
    "Visit 3 - Sample",

    # Visit 4
    "Visit 4 - 3D Notification",
    "Aravind Visit4 date1",
    "Aravind Visit4 date2",
    "Visit 4 - Dose 3",

    # Visit 5
    "Visit 5 - S Notification",
    "Aravind Visit5 date1",
    "Aravind Visit5 date2",
    "Visit 5 - Sample",
]

# keep only existing columns safely
df_partial = df_partial[
    [c for c in preferred_order if c in df_partial.columns] +
    [c for c in df_partial.columns if c not in preferred_order]
]

# =====================================================
# INSERT EXTRA COLUMNS BEFORE WRITING
# =====================================================

insert_after = "Date of confirmed visit"

extra_cols = [
    "(V1/D1) date",
    "(V2/D2) date",
    "(V3/S) date",
    "(V4/D3) date",
    "(V5/S) date"
]

# find position
if insert_after in df_partial.columns:
    pos = df_partial.columns.get_loc(insert_after) + 1
else:
    pos = len(df_partial.columns)

# insert safely
for i, col in enumerate(extra_cols):
    if col not in df_partial.columns:
        df_partial.insert(pos + i, col, np.nan)

# =====================================================
# NOW WRITE TO SHEET
# =====================================================

set_with_dataframe(
    dest_sheet,
    df_partial,
    include_index=False,
    include_column_header=True
)


# =====================================================
# STEP 17: FORMAT SHEET
# =====================================================

def col_letter(n):

    s = ""

    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s

    return s


fmt = CellFormat(
    horizontalAlignment="LEFT",
    wrapStrategy="CLIP"
)

last_col = col_letter(
    len(df_partial.columns)
)

format_cell_range(
    dest_sheet,
    f"A1:{last_col}{len(df_partial)+1}",
    fmt
)


print("SCREENING Call Tracker updated")
print(
    f"Successfully copied "
    f"{len(df_partial)} records"
)


# =====================================================
# STEP 18: UPDATE ONLY S.No, Screening ID, Incharge
# =====================================================

df_lab_update = df_partial[
    ["S.No", "Screening ID", "Incharge"]
].copy()

data_to_write = (
    [df_lab_update.columns.tolist()]
    + df_lab_update.values.tolist()
)

dest_sheet_lab.update(
    range_name=f"A1:C{len(data_to_write)}",
    values=data_to_write
)

print("LAB sheet columns A:C updated")
print(f"Rows written: {len(df_lab_update)}")