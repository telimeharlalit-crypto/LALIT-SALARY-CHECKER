import streamlit as st
import pdfplumber
import pandas as pd
import re

# ----------------- SLAB MINIMUM CALCULATIONS -----------------
def get_min_gpf(basic):
    if basic <= 23100: return 1450
    elif basic <= 28500: return 1625
    elif basic <= 38500: return 2100
    elif basic <= 51500: return 2850
    elif basic <= 62000: return 3575
    elif basic <= 72000: return 4200
    elif basic <= 80000: return 4800
    elif basic <= 116000: return 6150
    elif basic <= 167000: return 8900
    else: return 10500

def get_min_si(basic):
    if basic <= 22000: return 800
    elif basic <= 28500: return 1200
    elif basic <= 46500: return 2200
    elif basic <= 72000: return 3000
    else: return 7000

def get_min_rghs(basic):
    if basic <= 18000: return 265
    elif basic <= 33500: return 440
    elif basic <= 54000: return 658
    else: return 875

# ----------------- STRICT JUNK FILTER -----------------
# Agar line me inme se koi shabd hai toh wo kabhi naya employee nahi ho sakta
JUNK_PHRASES = [
    "SCHOOL", "SECONDARY", "HIGHER", "DEATH", "WHERE PAYMENT", "PAYMENT IS",
    "ESTABLISHMENT", "TREASURY", "OFFICE OF", "GRAND TOTAL", "SCHEDULE", 
    "BILL SUMMARY", "GOVT", "GOVERNMENT", "DESIGNATION", "STATEMENT", "VICE",
    "SENIOR SECONDARY", "BLOCK", "PANCHAYAT", "SAMITI", "DISTRICT", "RAJASTHAN"
]

IGNORE_WORDS = {
    "DETAILED", "ESTABLISHMENT", "OFFICE", "ID", "AMSSOUNT", "AMOUNT", "DEDUCTION", 
    "TOTAL", "GOVERNMENT", "RAJASTHAN", "TREASURY", "BILL", "SUMMARY", "GRAND", 
    "PAGE", "MAJOR", "HEAD", "SUB", "BUDGET", "DDO", "DATE", "INNER", "OUTER", 
    "SCHEDULE", "TOKEN", "GROSS", "NET", "SIGNATURE", "ACCOUNT", "IFSC", "BRANCH", 
    "BANK", "PAYMANAGER", "MONTH", "YEAR", "ALLOWANCES", "DEDUCTIONS", "BASIC", 
    "PAY", "DA", "HRA", "GPF", "SI", "RGHS", "NAME", "DESIG", "OF", "THE", "IN", 
    "AT", "FOR", "AND", "TO", "BY", "RJ", "REFERENCE", "REF", "NO", "AUGUST", 
    "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER", "JANUARY", "FEBRUARY", 
    "MARCH", "APRIL", "MAY", "JUNE", "JULY", "SAB", "2004", "PT", "FIXED",
    "TEACHER", "LECTURER", "PRINCIPAL", "LDC", "UDC", "HEADMASTER", "PEON", 
    "DRIVER", "OFFICER", "CLERK", "ASSISTANT", "SIP", "JJ", "PHYSICAL", "EDUCATION", 
    "GRADE", "III", "II", "I", "ITAX", "LIC", "SIL", "SS", "RRBASIC"
}

PROBATION_FIXED_PAYS = {17700, 18500, 19700, 20700, 23700}
VALID_SI_STEPS = {800, 1200, 2200, 3000, 5000, 7000}

def is_line_junk(line_upper):
    return any(p in line_upper for p in JUNK_PHRASES)

def clean_employee_name(tokens):
    cleaned = []
    for t in tokens:
        w = re.sub(r'[^A-Za-z]', '', t).strip()
        if not w or w.upper() in IGNORE_WORDS or len(w) <= 1:
            continue
        cleaned.append(w.capitalize())
    return " ".join(cleaned)

def parse_pdf(file):
    employees = []
    full_text_pages = []

    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                full_text_pages.append(t)

    full_text = "\n".join(full_text_pages)
    lines = [l.strip() for l in full_text.split("\n") if l.strip()]

    current_emp = None

    for line in lines:
        line_upper = line.upper()

        tokens = line.replace(',', '').split()
        nums = [float(t) for t in tokens if re.match(r'^\d+(\.\d+)?$', t)]
        words = [t for t in tokens if re.match(r'^[A-Za-z\.]+$', t)]

        # Agar line me school ya office heading ka text hai, toh naya karmchari nahi banega
        if is_line_junk(line_upper):
            # Ye numbers current karmchari ke hi allowances/deductions hain
            if current_emp:
                current_emp["numbers"].extend(nums)
            continue

        potential_name = clean_employee_name(words)

        # Valid Karmchari Name Check (2 ya 3 shabdon ka naam)
        if potential_name and len(potential_name.split()) >= 2:
            if current_emp:
                employees.append(current_emp)
            current_emp = {
                "name": potential_name,
                "numbers": list(nums)
            }
        elif current_emp:
            current_emp["numbers"].extend(nums)

    if current_emp:
        employees.append(current_emp)

    return employees

# ----------------- STREAMLIT UI -----------------
st.set_page_config(page_title="Salary Deduction Checker", layout="wide")
st.title("📋 Rajasthan Govt. Salary & Deduction Checker")

col_top1, col_top2 = st.columns([1, 1])
with col_top1:
    da_rate = st.number_input("DA Rate (%)", value=60, min_value=0, max_value=100, step=1)
with col_top2:
    hra_rate = st.selectbox("HRA Rate (%)", options=[10, 9, 20, 18], index=0)

uploaded_file = st.file_uploader("Salary Bill PDF Upload Karein", type=["pdf"])

if uploaded_file:
    with st.spinner("PDF process aur verify ki ja rahi hai..."):
        emp_records = parse_pdf(uploaded_file)

    if not emp_records:
        st.error("Koi valid employee record extract nahi hua.")
    else:
        results = []
        for emp in emp_records:
            name = emp["name"]
            nums = emp["numbers"]

            # Basic Pay: Multiple of 100 between 17,000 and 2,25,000
            potential_basics = sorted([n for n in nums if 17000 <= n <= 225000 and (n % 100 == 0)], reverse=True)
            if not potential_basics:
                continue

            basic = None
            da = 0
            hra = 0

            # Match Basic and DA (60%)
            for b in potential_basics:
                calc_da = round(b * (da_rate / 100))
                match_da = next((n for n in nums if abs(n - calc_da) <= 2), None)
                if match_da is not None:
                    basic = b
                    da = int(round(match_da))
                    break

            if basic is None:
                basic = potential_basics[0]
                calc_da = round(basic * (da_rate / 100))
                da_candidate = next((n for n in nums if abs(n - calc_da) <= 2), 0)
                da = int(round(da_candidate))

            # Match HRA (10% ya 9%)
            exp_hra = int(round(basic * (hra_rate / 100)))
            hra_candidate = next((n for n in nums if abs(n - exp_hra) <= 2 or abs(n - round(basic * 0.09)) <= 2), None)
            hra = int(round(hra_candidate)) if hra_candidate is not None else 0

            # Samvida check: Only if basic is strictly in probation slab AND DA/HRA == 0
            is_samvida = (da == 0 and hra == 0 and basic in PROBATION_FIXED_PAYS)

            exp_da = 0 if is_samvida else int(round(basic * (da_rate / 100)))
            exp_hra_val = 0 if is_samvida else exp_hra

            min_gpf = 0 if is_samvida else get_min_gpf(basic)
            min_si = 0 if is_samvida else get_min_si(basic)
            min_rghs = 0 if is_samvida else get_min_rghs(basic)

            gross_estimate = basic + da + hra
            remaining_nums = [n for n in nums if n not in [basic, da, hra] and abs(n - gross_estimate) > 10 and n < 30000]

            # 1. RGHS Match
            rghs_candidates = [n for n in remaining_nums if n in [265, 440, 658, 875]]
            act_rghs = int(round(rghs_candidates[0])) if rghs_candidates else 0
            if act_rghs in remaining_nums:
                remaining_nums.remove(act_rghs)

            # 2. SI Match
            si_candidates = [n for n in remaining_nums if n in [800, 1200, 2200, 3000, 5000, 7000]]
            act_si = int(round(max(si_candidates))) if si_candidates else 0
            if act_si in remaining_nums:
                remaining_nums.remove(act_si)

            # 3. GPF Match
            if is_samvida:
                act_gpf = 0
            else:
                standard_gpfs = [1450, 1625, 2100, 2850, 3575, 4200, 4800, 6150, 8900, 10500]
                gpf_exact = [n for n in remaining_nums if n in standard_gpfs and n >= min_gpf]
                if gpf_exact:
                    act_gpf = int(round(gpf_exact[0]))
                else:
                    gpf_vol = [n for n in remaining_nums if min_gpf <= n <= 25000]
                    act_gpf = int(round(gpf_vol[0])) if gpf_vol else 0

            # Status Checks
            if is_samvida:
                da_status = "OK (संविदा)"
                hra_status = "OK (संविदा)"
                gpf_status = "N/A (संविदा)"
                si_status = "N/A (संविदा)"
                rghs_status = "OK" if act_rghs in [0, 265, 440, 658, 875] else "Mismatch"
            else:
                da_status = "OK" if abs(da - exp_da) <= 2 else ("N/A (Schedule)" if da == 0 else "Mismatch")
                hra_status = "OK" if abs(hra - exp_hra_val) <= 2 else ("N/A (Schedule)" if hra == 0 else "Mismatch")
                gpf_status = "OK" if (act_gpf > 0 and act_gpf >= min_gpf) else "Mismatch"
                
                if act_si >= min_si:
                    si_status = "OK"
                elif act_si in VALID_SI_STEPS and act_si > 0:
                    si_status = "OK (Old Slab)"
                else:
                    si_status = "Mismatch"

                rghs_status = "OK" if (act_rghs > 0 and act_rghs >= min_rghs) else "Mismatch"

            results.append({
                "Employee Name": name,
                "Basic Pay": int(round(basic)),
                "Category": "संविदा / Fixed" if is_samvida else "Regular",
                "Exp DA": exp_da,
                "Actual DA": da,
                "DA Check": da_status,
                "Exp HRA": exp_hra_val,
                "Actual HRA": hra,
                "HRA Check": hra_status,
                "Min GPF": min_gpf,
                "Actual GPF": act_gpf,
                "GPF Check": gpf_status,
                "Min SI": min_si,
                "Actual SI": act_si,
                "SI Check": si_status,
                "Min RGHS": min_rghs,
                "Actual RGHS": act_rghs,
                "RGHS Check": rghs_status
            })

        df = pd.DataFrame(results)
        df = df.drop_duplicates(subset=["Employee Name", "Basic Pay"]).reset_index(drop=True)

        def highlight_status(val):
            val_str = str(val)
            if val_str.startswith("OK") or val_str.startswith("N/A"):
                return "background-color: #c8e6c9; color: #1b5e20; font-weight: bold;"
            elif val_str == "Mismatch":
                return "background-color: #ffcdd2; color: #b71c1c; font-weight: bold;"
            return ""

        check_cols = ["DA Check", "HRA Check", "GPF Check", "SI Check", "RGHS Check"]
        try:
            styled_df = df.style.map(highlight_status, subset=check_cols)
        except AttributeError:
            styled_df = df.style.applymap(highlight_status, subset=check_cols)

        st.subheader("👥 Employee Verification Report")
        st.dataframe(styled_df, use_container_width=True)

        col1, col2, col3 = st.columns(3)
        total_emp = len(df)
        all_ok = len(df[
            (df["DA Check"].str.contains("OK|N/A")) & 
            (df["HRA Check"].str.contains("OK|N/A")) & 
            (df["GPF Check"].str.contains("OK|N/A")) & 
            (df["SI Check"].str.contains("OK|N/A")) & 
            (df["RGHS Check"].str.contains("OK|N/A"))
        ])
        mismatch_cnt = total_emp - all_ok

        col1.metric("Total Employees", total_emp)
        col2.metric("Sab Sahi (All OK)", all_ok)
        col3.metric("Mismatch / Check Required", mismatch_cnt)

        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Verified Data Download Karein (CSV)", csv, "salary_verified.csv", "text/csv")
