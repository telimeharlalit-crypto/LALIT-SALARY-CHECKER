import streamlit as st
import pandas as pd
import re

# PDF Text Extraction (pypdf with pdfplumber fallback)
def extract_pdf_text(file):
    try:
        import pypdf
        reader = pypdf.PdfReader(file)
        return "\n".join([p.extract_text() or "" for p in reader.pages])
    except Exception:
        import pdfplumber
        with pdfplumber.open(file) as pdf:
            return "\n".join([p.extract_text() or "" for p in pdf.pages])

# ----------------- SLAB CALCULATIONS -----------------
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

VALID_SI_STEPS = {800, 1200, 2200, 3000, 5000, 7000}

# ----------------- PARSER -----------------
def parse_pdf(file):
    full_text = extract_pdf_text(file)
    emp_id_pattern = re.compile(r'(RJ[A-Z]{2}\d{10,14})', re.IGNORECASE)
    matches = list(emp_id_pattern.finditer(full_text))

    desig_words = [
        'PRINCIPAL', 'ASSISTANT', 'OFFICER', 'LECTURER', 'TEACHER', 
        'SHERISTEDAR', 'CLERK', 'GRADE', 'RESOURCE', 'PERSON', 'EDUCATION',
        'SENIOR', 'HEADMASTER', 'DRIVER', 'PEON', 'PHYSICAL', 'INSPECTOR'
    ]

    employees = []

    if matches:
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)

            pre_text = full_text[max(0, start - 400):start]
            lines = [l.strip() for l in pre_text.split('\n') if l.strip()]

            name = "Employee"
            for line in reversed(lines):
                if '(' in line or ')' in line:
                    continue
                if re.search(r'(\d{4,}|null|Date|Death|Nominee|Grade|Scale|L\d+|GPF)', line, re.IGNORECASE):
                    continue
                if any(d in line.upper() for d in desig_words):
                    continue
                clean_name = re.sub(r'[^A-Za-z\s]', '', line).strip()
                if len(clean_name) >= 3 and not any(k in clean_name.upper() for k in ['BASIC', 'PAY', 'NAME', 'DESIG', 'BELT', 'AADHAR', 'PAN', 'BANK', 'TOTAL', 'GROSS', 'NET', 'SR', 'NO']):
                    name = " ".join([w.capitalize() for w in clean_name.split()])
                    break

            block_text = full_text[start:end]

            basic_match = re.search(r'Basic\s+100\s+(\d+)', block_text, re.IGNORECASE)
            basic = int(basic_match.group(1)) if basic_match else 0

            da_match = re.search(r'DA\s+104\s+(\d+)', block_text, re.IGNORECASE)
            da = int(da_match.group(1)) if da_match else 0

            hra_match = re.search(r'HRA\s+107\s+(\d+)', block_text, re.IGNORECASE)
            hra = int(hra_match.group(1)) if hra_match else 0

            si_match = re.search(r'SIP\s+217\s+(\d+)', block_text, re.IGNORECASE)
            si = int(si_match.group(1)) if si_match else 0

            rghs_match = re.search(r'RGHS\s+297\s+(\d+)', block_text, re.IGNORECASE)
            rghs = int(rghs_match.group(1)) if rghs_match else 0

            gpf_match = re.search(r'GPF(?:\s+2004)?\s+\d+\s+(\d+)', block_text, re.IGNORECASE)
            gpf = int(gpf_match.group(1)) if gpf_match else 0

            nums = [float(n) for n in re.findall(r'\b\d+(?:\.\d+)?\b', block_text)]
            if basic == 0:
                pot_b = [n for n in nums if 10000 <= n <= 225000 and (n % 100 == 0)]
                basic = int(pot_b[0]) if pot_b else 0

            employees.append({
                "name": name,
                "has_rj_id": True,
                "basic": basic,
                "da": da,
                "hra": hra,
                "gpf": gpf,
                "si": si,
                "rghs": rghs,
                "nums": nums
            })
    else:
        # Fallback for schedules / bills without RJ IDs
        lines = [l.strip() for l in full_text.split("\n") if l.strip()]
        for line in lines:
            line_upper = line.upper()
            if any(h in line_upper for h in ["SCHEDULE", "TREASURY", "OFFICE OF", "GRAND TOTAL", "ESTABLISHMENT"]):
                continue
            nums = [float(t) for t in re.findall(r'\b\d+(?:\.\d+)?\b', line)]
            words = [t for t in re.findall(r'[A-Za-z]+', line) if len(t) > 1]
            valid_words = [w for w in words if w.upper() not in ["BASIC", "DA", "HRA", "GPF", "SI", "RGHS", "TOTAL", "NET", "BILL"]]
            has_rj = bool(re.search(r'\bRJ[A-Z]{2}\d+\b', line, re.IGNORECASE))
            pot_b = [n for n in nums if 10000 <= n <= 225000 and (n % 100 == 0)]
            if valid_words and pot_b:
                employees.append({
                    "name": " ".join([w.capitalize() for w in valid_words[:3]]),
                    "has_rj_id": has_rj,
                    "basic": int(pot_b[0]),
                    "da": 0, "hra": 0, "gpf": 0, "si": 0, "rghs": 0,
                    "nums": nums
                })

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
            basic = emp["basic"]
            if basic == 0:
                continue

            has_rj_id = emp.get("has_rj_id", False)
            raw_name = emp["name"]
            
            # Agar RJ Employee ID nahi hai toh sirf Name ke aage "संविदा कार्मिक" likhe
            display_name = raw_name if has_rj_id else f"{raw_name} (संविदा कार्मिक)"

            nums = emp["nums"]
            actual_da = emp["da"] if emp["da"] > 0 else (int(round(next((n for n in nums if abs(n - round(basic * (da_rate / 100))) <= 2), 0))))
            actual_hra = emp["hra"] if emp["hra"] > 0 else (int(round(next((n for n in nums if abs(n - round(basic * (hra_rate / 100))) <= 2 or abs(n - round(basic * 0.09)) <= 2), 0))))
            actual_gpf = emp["gpf"] if emp["gpf"] > 0 else int(round(next((n for n in nums if n in [1450, 1625, 2100, 2850, 3575, 4200, 4800, 6150, 8900, 10000, 10500]), 0)))
            actual_si = emp["si"] if emp["si"] > 0 else int(round(max([n for n in nums if n in [800, 1200, 2200, 3000, 5000, 7000]] or [0])))
            actual_rghs = emp["rghs"] if emp["rghs"] > 0 else int(round(next((n for n in nums if n in [265, 440, 658, 875]), 0)))

            if not has_rj_id:
                # संविदा कार्मिक: Error check nahi hoga, N/A rahega
                exp_da = 0
                exp_hra = 0
                min_gpf = 0
                min_si = 0
                min_rghs = 0
                da_status = "N/A (संविदा)"
                hra_status = "N/A (संविदा)"
                gpf_status = "N/A (संविदा)"
                si_status = "N/A (संविदा)"
                rghs_status = "N/A (संविदा)"
            else:
                # Regular Employee: Full Error Verification
                exp_da = int(round(basic * (da_rate / 100)))
                exp_hra = int(round(basic * (hra_rate / 100)))
                min_gpf = get_min_gpf(basic)
                min_si = get_min_si(basic)
                min_rghs = get_min_rghs(basic)

                da_status = "OK" if abs(actual_da - exp_da) <= 2 else "Mismatch"
                hra_status = "OK" if (abs(actual_hra - exp_hra) <= 2 or actual_hra > 0) else "Mismatch"
                gpf_status = "OK" if (actual_gpf > 0 and actual_gpf >= min_gpf) else "Mismatch"

                if actual_si >= min_si:
                    si_status = "OK"
                elif actual_si in VALID_SI_STEPS and actual_si > 0:
                    si_status = "OK (Old Slab)"
                else:
                    si_status = "Mismatch"

                rghs_status = "OK" if (actual_rghs > 0 and actual_rghs >= min_rghs) else "Mismatch"

            results.append({
                "Employee Name": display_name,
                "Basic Pay": basic,
                "Exp DA": exp_da,
                "Actual DA": actual_da,
                "DA Check": da_status,
                "Exp HRA": exp_hra,
                "Actual HRA": actual_hra,
                "HRA Check": hra_status,
                "Min GPF": min_gpf,
                "Actual GPF": actual_gpf,
                "GPF Check": gpf_status,
                "Min SI": min_si,
                "Actual SI": actual_si,
                "SI Check": si_status,
                "Min RGHS": min_rghs,
                "Actual RGHS": actual_rghs,
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
