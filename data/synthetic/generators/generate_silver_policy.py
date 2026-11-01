"""
Generates MediShield Silver Plan policy PDF.
Saved to dataset/policies/medishield_silver_plan.pdf
"""

import os
from datetime import datetime, timezone

from fpdf import FPDF

BRAND_NAVY = (14, 68, 48)  # forest green / teal — distinct from Gold's navy
BRAND_SILVER = (120, 130, 145)
BODY_GRAY = (50, 50, 50)
LIGHT_GREEN = (232, 245, 238)
TABLE_HEAD = (14, 68, 48)
TABLE_ALT = (238, 248, 242)


class SilverPDF(FPDF):
    def header(self):
        if self.page_no() > 1:
            self.set_font("helvetica", "B", 9)
            self.set_text_color(*BODY_GRAY)
            self.cell(
                0, 8, "MediShield Silver Plan -- Policy Document  |  MED-SLV-SERIES-2025", align="L"
            )
            self.set_font("helvetica", "I", 9)
            self.cell(0, 8, f"Page {self.page_no()}", align="R", new_x="LMARGIN", new_y="NEXT")
            self.set_draw_color(*BRAND_NAVY)
            self.line(15, self.get_y(), 195, self.get_y())
            self.ln(3)

    def footer(self):
        if self.page_no() > 1:
            self.set_y(-14)
            self.set_font("helvetica", "I", 8)
            self.set_text_color(120, 120, 140)
            self.cell(
                0,
                8,
                "MediShield Health Insurance Ltd. * 123 Healthcare Blvd, Suite 500, Chicago IL 60601 * "
                "1-800-MEDISHIELD * www.medishield-insurance.com",
                align="C",
            )

    def section_title(self, text, level=1):
        self.start_section(text, level=level - 1)
        if level == 1:
            self.set_fill_color(*LIGHT_GREEN)
            self.set_font("helvetica", "B", 14)
            self.set_text_color(*BRAND_NAVY)
            self.cell(0, 10, text, fill=True, new_x="LMARGIN", new_y="NEXT")
            self.set_draw_color(*BRAND_NAVY)
            self.line(15, self.get_y(), 195, self.get_y())
            self.ln(4)
        else:
            self.set_font("helvetica", "B", 12)
            self.set_text_color(*BRAND_NAVY)
            self.cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")
            self.ln(2)
        self.set_text_color(*BODY_GRAY)

    def body(self, text, indent=0):
        self.set_font("helvetica", "", 11)
        self.set_text_color(*BODY_GRAY)
        self.set_x(15 + indent)
        self.multi_cell(180 - indent, 6.5, text)
        self.ln(3)

    def bullet(self, items, indent=5):
        self.set_font("helvetica", "", 11)
        self.set_text_color(*BODY_GRAY)
        for item in items:
            self.set_x(15 + indent)
            self.cell(6, 7, "*")
            self.multi_cell(174 - indent, 7, item)
        self.ln(2)

    def table_header(self, cols, widths):
        self.set_fill_color(*TABLE_HEAD)
        self.set_text_color(255, 255, 255)
        self.set_font("helvetica", "B", 10)
        for col, w in zip(cols, widths):
            self.cell(w, 8, col, border=1, fill=True)
        self.ln()
        self.set_text_color(*BODY_GRAY)

    def table_row(self, cells, widths, alt=False):
        self.set_fill_color(*TABLE_ALT if alt else (255, 255, 255))
        self.set_font("helvetica", "", 10)
        for cell, w in zip(cells, widths):
            self.cell(w, 7, cell, border=1, fill=True)
        self.ln()

    def definition_entry(self, term, text):
        self.set_font("helvetica", "B", 11)
        self.set_text_color(*BRAND_NAVY)
        self.set_x(15)
        self.multi_cell(180, 7, term + ":")
        self.set_font("helvetica", "", 11)
        self.set_text_color(*BODY_GRAY)
        self.set_x(20)
        self.multi_cell(175, 6.5, text)
        self.ln(3)


def create_silver_plan_document():
    pdf = SilverPDF()
    pdf.set_creation_date(datetime(2025, 1, 1, tzinfo=timezone.utc))
    pdf.set_auto_page_break(auto=True, margin=20)

    # ── Cover Page ───────────────────────────────────────────
    pdf.add_page()
    pdf.set_fill_color(*BRAND_NAVY)
    pdf.rect(0, 0, 210, 297, "F")

    pdf.set_text_color(255, 255, 255)
    pdf.set_font("helvetica", "B", 10)
    pdf.ln(15)
    pdf.cell(0, 8, "MEDISHIELD HEALTH INSURANCE LTD.", align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(4)
    pdf.set_font("helvetica", "B", 40)
    pdf.cell(0, 20, "MediShield", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "B", 30)
    pdf.set_text_color(192, 215, 192)
    pdf.cell(0, 16, "Silver Plan", align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(6)
    pdf.set_text_color(180, 220, 200)
    pdf.set_font("helvetica", "", 16)
    pdf.cell(0, 10, "Standard Health Insurance Policy", align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(10)
    pdf.set_font("helvetica", "I", 12)
    pdf.set_text_color(160, 200, 180)
    pdf.cell(
        0,
        8,
        "ACA-Compliant -- Silver Tier (70% Actuarial Value)",
        align="C",
        new_x="LMARGIN",
        new_y="NEXT",
    )

    pdf.ln(20)
    pdf.set_font("helvetica", "", 12)
    pdf.set_text_color(180, 210, 195)
    for line in [
        "Policy Series:     MED-SLV-SERIES-2025",
        "Effective Date:    January 1, 2025",
        "Expiration Date:   December 31, 2025",
        "Policy Year:       2025",
        "Product Code:      SLV-2025-US-IL",
    ]:
        pdf.cell(0, 9, line, align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(30)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("helvetica", "B", 14)
    pdf.cell(0, 10, "MediShield Health Insurance Ltd.", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 11)
    pdf.set_text_color(180, 210, 195)
    for line in [
        "123 Healthcare Blvd, Suite 500  |  Chicago, IL 60601",
        "Phone: 1-800-MEDISHIELD (1-800-633-4744)",
        "Fax: 1-800-633-4745  |  Claims: claims@medishield-insurance.com",
        "Web: www.medishield-insurance.com",
        "",
        "NAIC Company Code: 63010  |  IL DOI License: 9876543",
        "Regulated by the Illinois Department of Insurance",
    ]:
        pdf.cell(0, 7, line, align="C", new_x="LMARGIN", new_y="NEXT")

    # ── Table of Contents ────────────────────────────────────
    pdf.add_page()
    pdf.start_section("Table of Contents", level=0)
    pdf.set_font("helvetica", "B", 16)
    pdf.set_text_color(*BRAND_NAVY)
    pdf.cell(0, 12, "Table of Contents", new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*BRAND_NAVY)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(4)

    toc = [
        ("1. Schedule of Benefits", 3),
        ("2. Definitions", 4),
        ("3. Inclusions", 5),
        ("4. Exclusions", 5),
        ("5. Optional Riders", 6),
        ("6. Claims Procedure", 7),
        ("7. HIPAA Compliance", 8),
        ("8. ERISA Disclosure", 9),
        ("9. Illinois Dept. of Insurance Notice", 9),
        ("10. Policyholder Attestation", 10),
    ]
    pdf.set_font("helvetica", "", 12)
    pdf.set_text_color(*BODY_GRAY)
    for entry, pg in toc:
        pdf.set_x(15)
        pdf.cell(150, 9, entry)
        pdf.cell(30, 9, str(pg), align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(200, 210, 205)
        pdf.line(15, pdf.get_y() - 1, 195, pdf.get_y() - 1)
    pdf.ln(6)
    pdf.set_font("helvetica", "I", 10)
    pdf.set_text_color(100, 120, 100)
    pdf.multi_cell(
        180,
        6,
        "The Silver Plan provides standard coverage at 70% actuarial value. "
        "Cost-sharing is higher than the Gold Plan -- members pay more at point of service "
        "but benefit from lower monthly premiums. This document contains PDF bookmarks "
        "for digital navigation. Terminology is standardized throughout.",
    )

    # ── 1. Schedule of Benefits ──────────────────────────────
    pdf.add_page()
    pdf.section_title("1. Schedule of Benefits")
    pdf.body(
        "The Schedule of Benefits below summarizes coverage amounts and cost-sharing for the "
        "MediShield Silver Plan (2025 policy year). The Silver Plan provides 70% actuarial "
        "value -- on average, the plan pays 70% of covered medical expenses and the member "
        "pays 30% through deductibles, copays, and coinsurance. All amounts are in USD."
    )

    cols = ["Benefit Category", "In-Network", "Out-of-Network"]
    widths = [90, 45, 45]
    pdf.table_header(cols, widths)

    rows = [
        ("Lifetime Maximum Benefit", "$2,000,000", "$2,000,000"),
        ("Annual Policy Limit", "$1,000,000", "$1,000,000"),
        ("Individual Deductible", "$3,000", "$6,000"),
        ("Family Deductible", "$6,000", "$12,000"),
        ("Out-of-Pocket Maximum (Individual)", "$8,550", "$17,100"),
        ("Out-of-Pocket Maximum (Family)", "$17,100", "$34,200"),
        ("Primary Care Physician (PCP) Copay", "$40 / visit", "50% coinsurance"),
        ("Specialist Copay", "$80 / visit", "50% coinsurance"),
        ("Emergency Room (ER) Copay", "$350 / visit", "$350 + 30%"),
        ("Urgent Care Copay", "$75 / visit", "$100 / visit"),
        ("Inpatient Hospitalization", "30% after ded.", "50% after ded."),
        ("Outpatient Surgery", "30% after ded.", "50% after ded."),
        ("Diagnostic Lab & Imaging", "30% after ded.", "50% after ded."),
        ("Preventive Care (ACA-mandated)", "$0 copay", "Not covered"),
        ("Mental Health / Substance Use (outpatient)", "$80 / visit", "50% coinsurance"),
        ("Mental Health (inpatient)", "30% after ded.", "50% after ded."),
        ("Prescription Drugs -- Tier 1 (Generic)", "$20 / 30-day", "$20 / 30-day"),
        ("Prescription Drugs -- Tier 2 (Preferred)", "$60 / 30-day", "$90 / 30-day"),
        ("Prescription Drugs -- Tier 3 (Non-Preferred)", "$110 / 30-day", "$160 / 30-day"),
        ("Prescription Drugs -- Tier 4 (Specialty)", "30% (max $450)", "30% (max $550)"),
        ("Home Health Care", "30% after ded.", "Not covered"),
        ("Skilled Nursing Facility (max 30 days/yr)", "30% after ded.", "Not covered"),
        ("Durable Medical Equipment (DME)", "30% after ded.", "50% after ded."),
        ("Ambulance (medically necessary only)", "30% after ded.", "30% after ded."),
    ]
    for i, row in enumerate(rows):
        pdf.table_row(list(row), widths, alt=(i % 2 == 0))

    pdf.ln(4)
    pdf.set_font("helvetica", "I", 9)
    pdf.set_text_color(100, 100, 120)
    pdf.multi_cell(
        180,
        5.5,
        "* ER copay is waived if the member is admitted within 24 hours of the emergency visit. "
        "Silver Plan deductible must be met before most benefits (except preventive care and "
        "certain copay services) are payable. Cost-sharing reduction (CSR) variants may apply "
        "for members with incomes between 100-250% of the Federal Poverty Level.",
    )

    # ── 2. Definitions ──────────────────────────────────────
    pdf.add_page()
    pdf.section_title("2. Definitions")
    pdf.body(
        "The following terms have specific meanings within this Silver Plan policy. "
        "Terminology is consistent with the MediShield Gold Plan where applicable, "
        "but cost-sharing thresholds differ."
    )

    for term, defn in [
        (
            "Actuarial Value",
            "The percentage of total average costs for covered benefits that a health plan will cover. "
            "The Silver Plan has a 70% actuarial value -- on average, members pay 30% of costs. "
            "Individual experience will vary based on actual services used.",
        ),
        (
            "Pre-existing Condition",
            "Any illness, injury, or medical condition for which the Policyholder received medical "
            "advice, diagnosis, care, or treatment within the 24 months immediately preceding the "
            "Effective Date. Subject to a 24-month waiting period before benefits are payable. "
            "Per the ACA, pre-existing condition exclusions cannot be applied to essential health "
            "benefits for non-grandfathered plans.",
        ),
        (
            "Deductible",
            "The amount a member pays for covered health care services before the insurance plan "
            "begins to pay. For the Silver Plan, the individual deductible is $3,000 in-network. "
            "Preventive care and certain copay services are exempt from the deductible.",
        ),
        (
            "Cost-Sharing Reduction (CSR)",
            "A federal subsidy available to eligible members enrolled through the Health Insurance "
            "Marketplace with incomes between 100-250% of the Federal Poverty Level. CSR variants "
            "of the Silver Plan (CSR 73, CSR 87, CSR 94) have lower cost-sharing than the standard "
            "Silver Plan. Eligibility is determined at enrollment.",
        ),
        (
            "Network Provider",
            "A physician, hospital, or other healthcare provider that has a participation agreement "
            "with MediShield to provide covered services at negotiated rates. Using in-network "
            "providers results in significantly lower cost-sharing under the Silver Plan.",
        ),
        (
            "Essential Health Benefits (EHB)",
            "The ten categories of services that ACA-compliant plans must cover: (1) ambulatory "
            "patient services, (2) emergency services, (3) hospitalization, (4) maternity and "
            "newborn care, (5) mental health and substance use disorder services, (6) prescription "
            "drugs, (7) rehabilitative services, (8) laboratory services, (9) preventive and "
            "wellness services, (10) pediatric services including oral and vision care.",
        ),
        (
            "Out-of-Pocket Maximum",
            "The most a member pays for covered services in a plan year. After this amount is "
            "reached, the plan pays 100% of covered in-network services. For the Silver Plan, "
            "the individual OOP maximum is $8,550 in-network (ACA maximum for 2025).",
        ),
    ]:
        pdf.definition_entry(term, defn)

    # ── 3 & 4. Inclusions / Exclusions ──────────────────────
    pdf.add_page()
    pdf.section_title("3. Inclusions (Covered Services)")
    pdf.body(
        "The following services are covered under the MediShield Silver Plan, subject to the "
        "cost-sharing amounts in the Schedule of Benefits and any applicable waiting periods."
    )
    pdf.bullet(
        [
            "Inpatient hospital services: semi-private room and board, general nursing care, "
            "operating and recovery room, ICU/CCU services, medically necessary hospitalization.",
            "Outpatient surgery and procedures performed in a licensed ambulatory surgical center "
            "or hospital outpatient department.",
            "Physician services: office visits, consultations, second opinions, and home visits "
            "by network physicians.",
            "Emergency care: emergency room services and urgent care for sudden illness or injury. "
            "ER copay waived if patient is admitted within 24 hours.",
            "Diagnostic services: laboratory tests (blood work, urinalysis, pathology), "
            "imaging (X-ray, CT, MRI, PET scans), and nuclear medicine.",
            "Preventive care: annual wellness exams, immunizations, cancer screenings (mammography, "
            "colonoscopy, Pap smear), blood pressure and cholesterol screening at $0 copay "
            "when performed by an in-network provider.",
            "Prescription drugs: covered under the 4-tier formulary. Specialty drugs (Tier 4) "
            "require prior authorization. Step therapy may apply for certain drug classes.",
            "Maternity and newborn care: prenatal visits, delivery (vaginal and cesarean), "
            "postpartum care, and newborn care for the first 48 hours (vaginal) or 96 hours "
            "(cesarean) following delivery.",
            "Mental health and substance use disorder services: outpatient therapy, inpatient "
            "psychiatric care, and substance use treatment at parity with medical benefits "
            "per the Mental Health Parity and Addiction Equity Act (MHPAEA).",
            "Pediatric services: well-child visits, immunizations, pediatric dental (routine "
            "exams and cleanings), and pediatric vision (one exam and corrective lenses per year) "
            "for covered dependents under age 19.",
            "Rehabilitation services: physical therapy (max 30 visits/year), occupational therapy "
            "(max 20 visits/year), speech therapy (max 20 visits/year) when medically necessary.",
            "Durable Medical Equipment (DME): wheelchairs, crutches, CPAP machines, and other "
            "medically necessary equipment with prior authorization for items over $500.",
            "Home health care: skilled nursing, physical therapy, and medical social services "
            "when ordered by a physician and provided by a licensed home health agency.",
        ]
    )

    pdf.section_title("4. Exclusions (Non-Covered Services)")
    pdf.body(
        "The following services are not covered under the MediShield Silver Plan. "
        "Submitting a claim for an excluded service will result in rejection. "
        "Members are responsible for 100% of costs for excluded services."
    )
    pdf.bullet(
        [
            "Cosmetic and elective procedures: rhinoplasty, blepharoplasty (CPT 15820-15823), "
            "liposuction, breast augmentation, hair restoration, and any procedure performed "
            "primarily to improve appearance rather than restore function.",
            "Experimental and investigational treatments: procedures, drugs, or devices not "
            "approved by the FDA or not yet established as effective through peer-reviewed "
            "clinical trials. Includes off-label drug use not supported by compendia.",
            "Dental services (adult): routine dental exams, cleanings, fillings, extractions, "
            "orthodontics, and dental implants for members age 19 and older. "
            "Pediatric dental is covered (see Inclusions).",
            "Vision services (adult): routine eye exams, eyeglasses, and contact lenses for "
            "members age 19 and older. Pediatric vision is covered (see Inclusions).",
            "Hearing aids and hearing exams: routine audiological exams and hearing aids. "
            "Cochlear implants may be covered if medically necessary with prior authorization.",
            "Custodial and long-term care: services that are primarily for personal care rather "
            "than skilled nursing or rehabilitative in nature.",
            "Weight loss programs: bariatric surgery, weight loss medications, dietary counseling "
            "for obesity, and non-medically-necessary weight loss programs.",
            "Fertility treatments: in vitro fertilization (IVF), gamete intrafallopian transfer "
            "(GIFT), embryo freezing, and sperm or egg donation.",
            "Non-emergency transportation: ambulance transport when not medically necessary, "
            "or transportation to a medical facility for non-emergency purposes.",
            "Over-the-counter (OTC) medications and supplies: unless prescribed and dispensed "
            "by a licensed pharmacist under a valid prescription.",
            "Services outside the United States: except for emergency care. Reimbursement for "
            "international emergency care is limited to $10,000 per occurrence.",
            "Workers' compensation claims: injuries or illnesses covered by a Workers' "
            "Compensation policy are not payable under this plan.",
        ]
    )

    # ── 4.1 Machine-readable CPT exclusion table ─────────────
    pdf.ln(4)
    pdf.set_font("helvetica", "B", 12)
    pdf.set_text_color(*BRAND_NAVY)
    pdf.cell(0, 8, "4.1 Excluded CPT Code Ranges (Machine-Readable)", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_text_color(*BODY_GRAY)
    pdf.set_font("helvetica", "", 10)
    pdf.multi_cell(
        180,
        5.5,
        "The table below lists CPT code ranges explicitly excluded from the MediShield Silver Plan. "
        "Claims with codes in these ranges are automatically denied unless a qualifying rider is active. "
        "Codes not in this table are subject to medical necessity review.",
    )
    pdf.ln(3)

    cols = ["CPT Range", "Procedure Category", "Exclusion Basis"]
    widths = [32, 98, 50]
    pdf.table_header(cols, widths)
    excl_rows = [
        ("15000-15999", "Integumentary / Skin Grafts (Cosmetic)", "Cosmetic S4(a)"),
        ("15820-15829", "Blepharoplasty - Eyelid Surgery", "Cosmetic S4(a)"),
        ("17000-17999", "Destruction of Benign Skin Lesions (cosmetic)", "Cosmetic S4(a)"),
        ("19300-19499", "Breast Surgery - Augmentation / Reduction", "Cosmetic S4(a)"),
        ("21120-21299", "Facial Bone Surgery (cosmetic only)", "Cosmetic S4(a)"),
        ("21920-21935", "Liposuction", "Cosmetic S4(a)"),
        ("55400-55450", "Vasectomy / Sterilization", "Elective S4(d)"),
        ("58300-58353", "Intrauterine Device Insertion / Removal", "Contraception S4(d)"),
        ("58600-58770", "Fallopian Tube Ligation", "Sterilization S4(d)"),
        ("58900-58999", "Oocyte / Fertility Procedures", "Fertility S4(b)"),
        ("89250-89356", "Embryo / Sperm Analysis and Cryopreservation", "Fertility S4(b)"),
        ("86849-86999", "Experimental Immunology Panels", "Experimental S4(c)"),
        ("0001T-0099T", "Category III - Emerging Technologies", "Experimental S4(c)"),
        ("97010-97799", "Physical Medicine - Non-Acute", "Prior Auth Req S5"),
        ("21600-21685", "Weight Loss Surgery / Bariatric Procedures", "Weight-loss S4(k)"),
        ("99241-99245", "Outpatient Consultations (standalone)", "Specialist copay only"),
        ("V2100-V2799", "Spectacles / Eyeglasses / Contact Lenses", "Vision excl. S4(i)"),
        ("D0100-D9999", "Dental Procedures (ADA codes)", "Dental excl. S4(h)"),
    ]
    for i, row in enumerate(excl_rows):
        pdf.table_row(list(row), widths, alt=(i % 2 == 0))
    pdf.ln(3)
    pdf.set_font("helvetica", "I", 8)
    pdf.set_text_color(100, 100, 120)
    pdf.multi_cell(
        180,
        5,
        "Note: CPT codes not in this exclusion table and not in the Schedule of Benefits are "
        "subject to medical necessity review. MediShield reserves the right to update this table annually. "
        "Current version: 2025 policy year.",
    )
    pdf.ln(4)

    # ── 5. Optional Riders ───────────────────────────────────
    pdf.add_page()
    pdf.section_title("5. Optional Riders")
    pdf.body(
        "The following optional riders may be added to the Silver Plan at an additional "
        "premium. Riders must be elected at enrollment or during an annual open enrollment "
        "period. Mid-year elections are permitted only upon a qualifying life event."
    )

    riders = [
        (
            "Maternity Rider",
            "Monthly Premium: + $48.00/month",
            "Extends maternity coverage to include fertility treatments (3 IVF cycles maximum), "
            "prenatal genetic testing (NIPT, amniocentesis), lactation consultant visits "
            "(max 6 visits), and postpartum mental health services (max 12 sessions). "
            "9-month waiting period applies from rider effective date.",
            [
                "Infertility evaluation and up to 3 IVF cycles",
                "Non-invasive prenatal testing (NIPT) and amniocentesis",
                "Lactation consultant: 6 visits at $0 copay",
                "Postpartum depression screening and treatment: 12 sessions",
            ],
        ),
        (
            "Critical Illness Rider",
            "Monthly Premium: + $32.00/month",
            "Provides a lump-sum benefit upon first diagnosis of a covered critical illness. "
            "Benefit is paid directly to the policyholder and may be used for any purpose "
            "(medical bills, lost income, living expenses). 90-day survival period required.",
            [
                "Cancer (malignant tumors only): $15,000 lump sum",
                "Heart attack (myocardial infarction): $15,000 lump sum",
                "Stroke (with permanent neurological deficit): $15,000 lump sum",
                "Organ transplant (major): $10,000 lump sum",
                "End-stage renal failure: $10,000 lump sum",
            ],
        ),
        (
            "Dental & Vision Rider (Adult)",
            "Monthly Premium: + $28.00/month",
            "Extends dental and vision coverage to members age 19 and older. "
            "Covers routine preventive dental care and one annual vision exam with "
            "allowance for corrective lenses or contacts.",
            [
                "Dental: 2 cleanings/year, 1 exam/year, bitewing X-rays at $0 copay",
                "Dental: Basic restorative (fillings) at 30% after $50 deductible",
                "Dental: Major restorative (crowns, bridges) at 50% after deductible; max $1,000/year",
                "Vision: 1 comprehensive exam/year at $0 copay",
                "Vision: Frames/lenses allowance: $150/year or contacts: $120/year",
            ],
        ),
    ]

    for rname, premium, desc, benefits in riders:
        pdf.section_title(rname, level=2)
        pdf.set_font("helvetica", "B", 11)
        pdf.set_text_color(*BRAND_NAVY)
        pdf.set_x(15)
        pdf.cell(0, 7, premium, new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(*BODY_GRAY)
        pdf.body(desc)
        pdf.bullet(benefits)

    # ── 6. Claims Procedure ──────────────────────────────────
    pdf.add_page()
    pdf.section_title("6. Claims Procedure")
    pdf.body(
        "MediShield processes claims submitted by network providers on the member's behalf "
        "(cashless) and reimburses members directly for out-of-network services. "
        "All claims are subject to the Silver Plan's cost-sharing schedule."
    )

    pdf.section_title("6.1 Cashless Claims (In-Network Providers)", level=2)
    pdf.body(
        "In-network providers submit claims electronically to MediShield using the member's "
        "policy number and group number. The member presents their MediShield ID card at "
        "the point of service and pays only the applicable copay or coinsurance."
    )
    pdf.bullet(
        [
            "Present MediShield Silver Plan ID card at point of service.",
            "Provider submits claim via EDI 837P (professional) or 837I (institutional).",
            "MediShield processes claim within 15 business days of receipt.",
            "Explanation of Benefits (EOB) is mailed/emailed within 5 days of processing.",
            "Prior authorization required for: inpatient admissions, outpatient surgery, "
            "imaging (MRI/CT/PET), specialist referrals for certain services, and Tier 4 drugs.",
        ]
    )

    pdf.section_title("6.2 Reimbursement Claims (Out-of-Network)", level=2)
    pdf.body(
        "Members who use out-of-network providers must pay the provider in full at the "
        "time of service and submit a reimbursement claim to MediShield within 180 days "
        "of the date of service."
    )
    pdf.bullet(
        [
            "Complete the MediShield Reimbursement Claim Form (available at medishield-insurance.com/forms).",
            "Attach itemized invoice from the provider (must include: provider name, NPI, "
            "date of service, CPT codes, ICD-10 diagnosis codes, billed amount).",
            "Submit to: MediShield Claims Dept., PO Box 7200, Chicago IL 60607.",
            "Reimbursement calculated at out-of-network rates after applicable deductible and coinsurance.",
            "Claims submitted after 180 days from date of service will be denied as untimely.",
        ]
    )

    pdf.section_title("6.3 Required Claim Documentation", level=2)
    pdf.bullet(
        [
            "Completed claim form with member signature.",
            "Valid government-issued photo ID (for first-time claim submissions).",
            "Itemized provider invoice or Explanation of Benefits from the provider.",
            "Prescription label (for drug reimbursement claims).",
            "Referral or prior authorization number (if applicable).",
            "Operative report or pathology report (for surgical claims over $2,000).",
        ]
    )

    pdf.section_title("6.4 Grievance & Appeals", level=2)
    pdf.body(
        "If a claim is denied or you disagree with a coverage decision, you have the right "
        "to file an internal appeal within 180 days of the denial notice."
    )
    pdf.bullet(
        [
            "Level 1 Internal Appeal: reviewed by a MediShield clinical reviewer not involved "
            "in the original decision. Decision within 30 days (standard) or 72 hours (urgent).",
            "Level 2 Internal Appeal: reviewed by an independent panel. Decision within 30 days.",
            "External Review: if internal appeals are exhausted, request independent external "
            "review through the Illinois DOI at www.insurance.illinois.gov.",
            "Grievance Hotline: 1-800-MED-HELP (Mon-Fri 8am-8pm CT).",
            "Email: grievances@medishield-insurance.com (response within 5 business days).",
        ]
    )

    # ── 7. HIPAA ─────────────────────────────────────────────
    pdf.add_page()
    pdf.section_title("7. HIPAA Compliance -- Notice of Privacy Practices")
    pdf.body(
        "MediShield Health Insurance Ltd. is required by law to maintain the privacy and "
        "security of your Protected Health Information (PHI). This notice describes how "
        "medical information about you may be used and disclosed."
    )
    pdf.section_title("7.1 Permitted Uses and Disclosures", level=2)
    pdf.bullet(
        [
            "Treatment: sharing PHI with your healthcare providers for treatment coordination.",
            "Payment: processing claims, coordinating benefits, and obtaining reimbursements.",
            "Operations: quality assessment, underwriting, fraud detection, and compliance.",
            "Public Health: reporting communicable diseases, adverse drug events as required by law.",
            "Business Associates: vendors under a Business Associate Agreement (BAA).",
        ]
    )
    pdf.section_title("7.2 Your Rights", level=2)
    pdf.bullet(
        [
            "Right to Access: request copies of your medical records and claims history.",
            "Right to Amend: request corrections to inaccurate information.",
            "Right to Restrict: request limitations on how your PHI is used.",
            "Right to Complaint: file with MediShield Privacy Officer or HHS at www.hhs.gov/hipaa.",
        ]
    )
    pdf.body(
        "Privacy Officer contact: privacy@medishield-insurance.com | 1-800-MEDISHIELD. "
        "MediShield encrypts all ePHI at rest and in transit and conducts annual HIPAA "
        "compliance training. Breach notification within 60 days per 45 CFR Part 164."
    )

    # ── 8. ERISA ─────────────────────────────────────────────
    pdf.add_page()
    pdf.section_title("8. ERISA Disclosure")
    pdf.body(
        "If offered through an employer-sponsored group health plan, this policy may be "
        "subject to ERISA (29 U.S.C. S 1001 et seq.). ERISA grants participants the right "
        "to examine plan documents, obtain copies of the Summary Plan Description (SPD), "
        "receive a Summary of Benefits and Coverage (SBC), appeal denied claims, and file "
        "suit under ERISA S 502(a) if rights are violated. Contact EBSA at www.dol.gov/ebsa "
        "or 1-866-444-3272 for information. Individually purchased policies are governed "
        "solely by Illinois state insurance law."
    )

    # ── 9. Illinois DOI ──────────────────────────────────────
    pdf.section_title("9. Illinois Department of Insurance -- Regulatory Notice")
    pdf.body(
        "This policy is issued in Illinois and regulated by the Illinois Department of "
        "Insurance (IDOI). MediShield is licensed under IL DOI License No. IL-HLT-2025."
    )
    pdf.bullet(
        [
            "Illinois DOI Consumer Hotline: 1-866-445-5364",
            "Illinois DOI Website: www.insurance.illinois.gov",
            "Illinois DOI Address: 320 W. Washington St., Springfield, IL 62767",
            "Online Complaint Filing: www.insurance.illinois.gov/consumer/complaint.asp",
        ]
    )
    pdf.body(
        "This policy complies with the Illinois Insurance Code (215 ILCS 5) and the "
        "Illinois Life and Health Insurance Guaranty Association Act (215 ILCS 105), "
        "which protects policyholders up to $500,000 in the event of insurer insolvency."
    )

    # ── 10. Attestation ──────────────────────────────────────
    pdf.add_page()
    pdf.section_title("10. Policyholder Attestation")
    pdf.body("By signing below, the Policyholder acknowledges and agrees that:")
    pdf.bullet(
        [
            "I have received, read, and understood this MediShield Silver Plan policy document.",
            "All information in my application is true and complete. Misrepresentation may "
            "result in rescission of this policy.",
            "I authorize MediShield to use my PHI as described in the Notice of Privacy Practices.",
            "I agree to notify MediShield within 30 days of any material changes to my "
            "household composition, address, or other information affecting this policy.",
            "I understand this policy is governed by Illinois law and subject to IDOI oversight.",
        ]
    )

    pdf.set_auto_page_break(False)
    pdf.ln(14)

    pdf.ln(18)
    sig_y = pdf.get_y()
    pdf.set_draw_color(60, 60, 80)
    pdf.line(15, sig_y, 90, sig_y)
    pdf.line(110, sig_y, 195, sig_y)
    pdf.ln(2)
    pdf.set_font("helvetica", "", 9)
    pdf.set_text_color(80, 80, 100)
    pdf.set_x(15)
    pdf.cell(75, 6, "Policyholder Signature")
    pdf.set_x(110)
    pdf.cell(85, 6, "Date (MM/DD/YYYY)", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(14)
    sig_y2 = pdf.get_y()
    pdf.line(15, sig_y2, 90, sig_y2)
    pdf.line(110, sig_y2, 195, sig_y2)
    pdf.ln(2)
    pdf.set_x(15)
    pdf.cell(75, 6, "Printed Name of Policyholder")
    pdf.set_x(110)
    pdf.cell(85, 6, "Policy Number (MED-SLV-XXXXXXX)", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(14)
    box_y = pdf.get_y()
    pdf.set_fill_color(235, 245, 238)
    pdf.set_draw_color(*BRAND_NAVY)
    pdf.rect(15, box_y, 180, 30, "FD")
    pdf.set_font("helvetica", "B", 8)
    pdf.set_text_color(*BRAND_NAVY)
    pdf.set_xy(18, box_y + 3)
    pdf.cell(60, 5, "FOR OFFICE USE ONLY")
    pdf.set_draw_color(140, 175, 155)
    pdf.line(15, box_y + 11, 195, box_y + 11)
    pdf.set_font("helvetica", "", 8)
    pdf.set_text_color(80, 80, 100)
    pdf.set_xy(18, box_y + 14)
    pdf.cell(58, 4, "Authorized MediShield Officer:")
    pdf.set_x(80)
    pdf.cell(38, 4, "Approval Date:")
    pdf.set_x(130)
    pdf.cell(62, 4, "Policy Issuance Ref #:")
    pdf.set_draw_color(120, 150, 135)
    pdf.line(18, box_y + 26, 76, box_y + 26)
    pdf.line(80, box_y + 26, 126, box_y + 26)
    pdf.line(130, box_y + 26, 193, box_y + 26)

    pdf.set_auto_page_break(True, margin=20)

    # ── Save ─────────────────────────────────────────────────
    out_dir = os.environ.get(
        "POLICY_OUT_DIR",
        os.path.join(os.environ.get("DOC_OUT_DIR", "dataset"), "policies"),
    )
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "medishield_silver_plan.pdf")
    pdf.output(out_path)
    return out_path


if __name__ == "__main__":
    path = create_silver_plan_document()
    size = os.path.getsize(path)
    print(f"Generated: {path}  ({size / 1024:.1f} KB)")
