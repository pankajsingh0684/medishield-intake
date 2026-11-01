import os
from datetime import datetime, timezone

from fpdf import FPDF

BRAND_BLUE = (12, 40, 110)
BRAND_GOLD = (180, 140, 10)
BODY_GRAY = (50, 50, 50)
LIGHT_BLUE = (230, 238, 252)
LIGHT_GRAY = (245, 245, 248)
TABLE_HEAD = (12, 40, 110)
TABLE_ALT = (240, 244, 252)


class PolicyPDF(FPDF):
    def header(self):
        if self.page_no() > 1:
            self.set_font("helvetica", "B", 9)
            self.set_text_color(*BODY_GRAY)
            self.cell(
                0, 8, "MediShield Gold Plan -- Policy Document  |  MED-GLD-SERIES-2025", align="L"
            )
            self.set_font("helvetica", "I", 9)
            self.cell(0, 8, f"Page {self.page_no()}", align="R", new_x="LMARGIN", new_y="NEXT")
            self.set_draw_color(*BRAND_BLUE)
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
            self.set_fill_color(*LIGHT_BLUE)
            self.set_font("helvetica", "B", 14)
            self.set_text_color(*BRAND_BLUE)
            self.cell(0, 10, text, fill=True, new_x="LMARGIN", new_y="NEXT")
            self.set_draw_color(*BRAND_BLUE)
            self.line(15, self.get_y(), 195, self.get_y())
            self.ln(4)
        else:
            self.set_font("helvetica", "B", 12)
            self.set_text_color(*BRAND_BLUE)
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
        if alt:
            self.set_fill_color(*TABLE_ALT)
        else:
            self.set_fill_color(255, 255, 255)
        self.set_font("helvetica", "", 10)
        for cell, w in zip(cells, widths):
            self.cell(w, 7, cell, border=1, fill=True)
        self.ln()

    def definition_entry(self, term, text):
        self.set_font("helvetica", "B", 11)
        self.set_text_color(*BRAND_BLUE)
        self.set_x(15)
        self.multi_cell(180, 7, term + ":")
        self.set_font("helvetica", "", 11)
        self.set_text_color(*BODY_GRAY)
        self.set_x(20)
        self.multi_cell(175, 6.5, text)
        self.ln(3)


def create_policy_document():
    pdf = PolicyPDF()
    pdf.set_creation_date(datetime(2025, 1, 1, tzinfo=timezone.utc))
    pdf.set_auto_page_break(auto=True, margin=20)

    # ════════════════════════════════════════════════════════
    # 1. COVER PAGE
    # ════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.set_fill_color(*BRAND_BLUE)
    pdf.rect(0, 0, 210, 297, "F")

    pdf.set_text_color(255, 255, 255)
    pdf.set_font("helvetica", "B", 10)
    pdf.ln(15)
    pdf.cell(0, 8, "MEDISHIELD HEALTH INSURANCE LTD.", align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(4)
    pdf.set_font("helvetica", "B", 40)
    pdf.cell(0, 20, "MediShield", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "B", 30)
    pdf.set_text_color(255, 215, 80)
    pdf.cell(0, 16, "Gold Plan", align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(6)
    pdf.set_text_color(200, 220, 255)
    pdf.set_font("helvetica", "", 16)
    pdf.cell(
        0, 10, "Comprehensive Health Insurance Policy", align="C", new_x="LMARGIN", new_y="NEXT"
    )

    pdf.ln(30)
    pdf.set_font("helvetica", "", 12)
    pdf.set_text_color(180, 200, 240)
    for line in [
        "Policy Series:     MED-GLD-SERIES-2025",
        "Effective Date:    January 1, 2025",
        "Expiration Date:   December 31, 2025",
        "Policy Year:       2025",
        "Product Code:      GLD-2025-US-IL",
    ]:
        pdf.cell(0, 9, line, align="C", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(35)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("helvetica", "B", 14)
    pdf.cell(0, 10, "MediShield Health Insurance Ltd.", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 11)
    pdf.set_text_color(180, 200, 240)
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

    # ════════════════════════════════════════════════════════
    # 2. TABLE OF CONTENTS  (page 2)
    # ════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.start_section("Table of Contents", level=0)
    pdf.set_font("helvetica", "B", 16)
    pdf.set_text_color(*BRAND_BLUE)
    pdf.cell(0, 12, "Table of Contents", new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*BRAND_BLUE)
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
        pdf.set_draw_color(200, 200, 210)
        pdf.line(15, pdf.get_y() - 1, 195, pdf.get_y() - 1)
    pdf.ln(6)
    pdf.set_font("helvetica", "I", 10)
    pdf.set_text_color(100, 100, 120)
    pdf.multi_cell(
        180,
        6,
        "This policy document contains bookmarks for digital navigation. Each section heading "
        "is a PDF bookmark. The terminology used throughout this document is standardized -- "
        "do not infer synonyms from external sources when interpreting coverage decisions.",
    )

    # ════════════════════════════════════════════════════════
    # 3. SCHEDULE OF BENEFITS  (page 3)
    # ════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section_title("1. Schedule of Benefits")
    pdf.body(
        "The Schedule of Benefits below summarizes the coverage amounts, cost-sharing "
        "obligations, and annual limits applicable to the MediShield Gold Plan for the "
        "2025 policy year. All amounts are in US Dollars (USD). Benefits are subject to "
        "the policy's Definitions, Inclusions, and Exclusions sections."
    )

    # Main benefits table
    cols = ["Benefit Category", "In-Network", "Out-of-Network"]
    widths = [90, 45, 45]
    pdf.table_header(cols, widths)

    rows = [
        ("Lifetime Maximum Benefit", "$5,000,000", "$5,000,000"),
        ("Annual Policy Limit", "$2,000,000", "$2,000,000"),
        ("Individual Deductible", "$1,500", "$3,000"),
        ("Family Deductible", "$3,000", "$6,000"),
        ("Out-of-Pocket Maximum (Individual)", "$7,500", "$15,000"),
        ("Out-of-Pocket Maximum (Family)", "$15,000", "$30,000"),
        ("Primary Care Physician (PCP) Copay", "$25 / visit", "40% coinsurance"),
        ("Specialist Copay", "$60 / visit", "40% coinsurance"),
        ("Emergency Room (ER) Copay", "$250 / visit", "$250 + 20%"),
        ("Urgent Care Copay", "$50 / visit", "$75 / visit"),
        ("Inpatient Hospitalization", "20% after ded.", "40% after ded."),
        ("Outpatient Surgery", "20% after ded.", "40% after ded."),
        ("Diagnostic Lab & Imaging", "20% after ded.", "40% after ded."),
        ("Preventive Care (ACA-mandated)", "$0 copay", "Not covered"),
        ("Mental Health / Substance Use (outpatient)", "$60 / visit", "40% coinsurance"),
        ("Mental Health (inpatient)", "20% after ded.", "40% after ded."),
        ("Prescription Drugs -- Tier 1 (Generic)", "$15 / 30-day", "$15 / 30-day"),
        ("Prescription Drugs -- Tier 2 (Preferred)", "$40 / 30-day", "$60 / 30-day"),
        ("Prescription Drugs -- Tier 3 (Non-Preferred)", "$80 / 30-day", "$120 / 30-day"),
        ("Prescription Drugs -- Tier 4 (Specialty)", "25% (max $320)", "25% (max $400)"),
        ("Home Health Care", "20% after ded.", "Not covered"),
        ("Skilled Nursing Facility (max 60 days/yr)", "20% after ded.", "Not covered"),
        ("Durable Medical Equipment (DME)", "20% after ded.", "40% after ded."),
        ("Ambulance (medically necessary only)", "20% after ded.", "20% after ded."),
    ]
    for i, (label, inn, out) in enumerate(rows):
        pdf.table_row([label, inn, out], widths, alt=(i % 2 == 0))

    pdf.ln(4)
    pdf.set_font("helvetica", "I", 9)
    pdf.set_text_color(100, 100, 120)
    pdf.multi_cell(
        180,
        5.5,
        "* ER copay is waived if the member is admitted to the hospital within 24 hours of "
        "the emergency visit. Out-of-pocket maximum includes deductible, copays, and "
        "coinsurance, but excludes premiums and non-covered services.",
    )

    # ════════════════════════════════════════════════════════
    # 4. DEFINITIONS  (page 4)
    # ════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section_title("2. Definitions")
    pdf.body(
        "The following terms have specific meanings within this policy. Consistent "
        "terminology is used throughout this document. Readers and automated systems "
        "should not substitute synonyms or infer alternate meanings."
    )

    definitions = [
        (
            "Pre-existing Condition",
            "Any illness, injury, or medical condition -- whether diagnosed or undiagnosed -- "
            "for which the Policyholder or a covered dependent received medical advice, "
            "diagnosis, care, or treatment within the 24 months immediately preceding the "
            "Effective Date of this policy. Pre-existing conditions are subject to a 24-month "
            "waiting period before benefits become payable.",
        ),
        (
            "Waiting Period",
            "The specified duration immediately following the Effective Date during which no "
            "benefits are payable for certain conditions: (a) 30-day general illness waiting "
            "period for acute illnesses; (b) 24-month waiting period for pre-existing "
            "conditions; (c) 9-month waiting period for maternity benefits (if Maternity Rider "
            "is elected). The waiting period does not apply to accidents.",
        ),
        (
            "Network Provider",
            "A physician, hospital, specialist, or other healthcare facility that has executed "
            "a participation agreement with MediShield Health Insurance Ltd. to provide "
            "covered services at negotiated rates. In-Network services result in lower "
            "cost-sharing for the Policyholder. A current Network Provider directory is "
            "available at www.medishield-insurance.com/find-a-provider.",
        ),
        (
            "Out-of-Network Provider",
            "A healthcare provider that has NOT executed a participation agreement with "
            "MediShield. Services rendered by Out-of-Network Providers are covered at reduced "
            "rates as specified in the Schedule of Benefits, and higher cost-sharing applies. "
            "Emergency services are always covered regardless of network status.",
        ),
        (
            "Cashless Authorization",
            "The process by which a Network Provider submits a Pre-Authorization Request to "
            "MediShield before or at the time of admission, requesting approval to render "
            "services without requiring the Policyholder to pay at the point of service. "
            "MediShield settles the approved amount directly with the Network Provider. "
            "Cashless Authorization is not available at Out-of-Network Providers.",
        ),
        (
            "Day Care Procedure",
            "A medical or surgical procedure that, due to technological advances, requires "
            "less than 24 hours of continuous hospitalization. Day Care Procedures are covered "
            "under inpatient benefits despite not requiring an overnight stay. Examples include "
            "cataract surgery, chemotherapy sessions, hemodialysis, and laparoscopic procedures "
            "completed within a single day.",
        ),
        (
            "Room and Board Limit",
            "The maximum daily allowance for inpatient hospital room and board charges, "
            "including nursing care, routine medications, and standard meals. Under the "
            "MediShield Gold Plan, this limit is the cost of a standard single private room "
            "at a Network Provider. Charges for suites or premium rooms that exceed this limit "
            "are the Policyholder's responsibility.",
        ),
        (
            "Medically Necessary",
            "A healthcare service, treatment, procedure, equipment, or supply that a licensed "
            "physician determines is required to diagnose or treat a covered illness or injury, "
            "is consistent with the symptoms or diagnosis, is not primarily for the convenience "
            "of the Policyholder or provider, and meets generally accepted standards of medical "
            "practice. MediShield's Medical Review team may verify medical necessity.",
        ),
        (
            "Deductible",
            "The fixed dollar amount the Policyholder must pay out-of-pocket for covered "
            "services before MediShield begins to pay benefits. Deductibles reset on the first "
            "day of each policy year. Preventive care services are not subject to the deductible.",
        ),
        (
            "Coinsurance",
            "The percentage of covered expenses the Policyholder pays after the deductible has "
            "been satisfied. For example, 20% coinsurance means MediShield pays 80% and the "
            "Policyholder pays 20% of covered charges.",
        ),
        (
            "Copay",
            "A fixed dollar amount the Policyholder pays at the time of service for specific "
            "covered services (e.g., $25 PCP copay, $60 Specialist copay). Copays do not "
            "typically count toward the deductible but do count toward the out-of-pocket maximum.",
        ),
        (
            "Out-of-Pocket Maximum",
            "The maximum total amount the Policyholder pays in a policy year for covered "
            "services, including deductibles, copays, and coinsurance. Once this limit is "
            "reached, MediShield pays 100% of covered in-network charges for the remainder "
            "of the policy year. Premiums and non-covered services are excluded.",
        ),
    ]
    for term, text in definitions:
        pdf.definition_entry(term, text)

    # ════════════════════════════════════════════════════════
    # 5. INCLUSIONS AND EXCLUSIONS  (page 5)
    # ════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section_title("3. Inclusions (Covered Services)")
    pdf.body(
        "The following services are covered under the MediShield Gold Plan when Medically "
        "Necessary and not listed under Section 4 (Exclusions). Coverage is subject to the "
        "deductibles, copays, and coinsurance specified in the Schedule of Benefits."
    )
    pdf.bullet(
        [
            "Inpatient hospitalization: room and board (up to the Room and Board Limit), "
            "intensive care unit (ICU), nursing care, and attending physician fees.",
            "Emergency room services, including stabilization and observation.",
            "Outpatient physician visits: Primary Care Physician and Specialist consultations.",
            "Diagnostic services: laboratory tests, blood panels, urinalysis, pathology.",
            "Diagnostic imaging: X-ray, CT scan, MRI, PET scan, echocardiogram, ultrasound.",
            "Surgical services: physician fees, anesthesia, operating room, post-operative care.",
            "Day Care Procedures as defined in Section 2.",
            "Maternity care (labor, delivery, postnatal care) -- subject to Maternity Rider "
            "election and 9-month waiting period.",
            "Newborn care for the first 31 days of life (added to policy within 31 days of birth).",
            "Mental health and substance use disorder treatment (inpatient and outpatient), "
            "as required by the Mental Health Parity and Addiction Equity Act (MHPAEA).",
            "Preventive care services as mandated by the Affordable Care Act (ACA) at $0 cost-sharing.",
            "Prescription drugs: Formulary Tier 1-4 medications dispensed by a licensed pharmacist.",
            "Home health care: skilled nursing, physical therapy, occupational therapy (up to 60 visits/year).",
            "Durable medical equipment (DME): prosthetics, orthotics, and medically required devices.",
            "Ambulance services: ground and air transport when Medically Necessary.",
            "Rehabilitation services: physical, occupational, and speech therapy (up to 60 visits/year).",
            "Organ transplants: listed transplants at designated Centers of Excellence.",
            "Chemotherapy, radiation therapy, and cancer-related infusion services.",
            "Dialysis (in-center and home hemodialysis).",
            "Telemedicine consultations with Network Providers.",
        ]
    )

    pdf.section_title("4. Exclusions (Non-Covered Services)", level=1)
    pdf.body(
        "The following services are NOT covered under the MediShield Gold Plan. Claims "
        "submitted for excluded services will be denied. Optional riders may extend coverage "
        "for certain items marked with [Rider Available]."
    )
    pdf.bullet(
        [
            "Cosmetic surgery or aesthetic treatments, including rhinoplasty, liposuction, "
            "blepharoplasty (eyelid surgery), genioplasty, facelifts, and breast augmentation, "
            "unless required for functional reconstruction following an accident or cancer surgery.",
            "Fertility and infertility treatments: ovulation induction, IUI, IVF, egg freezing, "
            "embryo storage, donor sperm or eggs -- unless covered under the Maternity Rider.  "
            "[Rider Available: Maternity Rider]",
            "Experimental or Investigational treatments and procedures not approved by the "
            "US Food and Drug Administration (FDA) or not recognized by generally accepted "
            "medical standards at the time of service.",
            "Self-inflicted injuries, suicide attempts, or intentional acts of self-harm.",
            "Injuries sustained while under the influence of alcohol, narcotics, or illegal drugs.",
            "Treatment for injuries sustained during participation in professional sports, "
            "extreme sports, or high-risk recreational activities (e.g., skydiving, BASE jumping, "
            "motor racing).",
            "Injuries sustained during the commission of a felony or illegal activity.",
            "War, terrorism, riot, or civil unrest -- whether declared or undeclared.",
            "Routine dental services: cleanings, fillings, extractions, orthodontics, dental implants. "
            "(Emergency dental treatment following an accident is covered.)",
            "Routine vision services: eye exams for refractive errors, prescription glasses, "
            "contact lenses, LASIK or PRK surgery.",
            "Hearing aids and routine audiological exams.",
            "Long-term care, custodial care, or non-skilled nursing home care.",
            "Complementary and alternative medicine: acupuncture, homeopathy, naturopathy, "
            "chiropractic (beyond 20 visits/year), massage therapy.",
            "Weight loss programs, bariatric surgery, or treatments for obesity unless required "
            "for a covered comorbid condition and pre-authorized by MediShield.",
            "Sleep studies or treatment for sleep disorders unless Medically Necessary and "
            "pre-authorized.",
            "Travel health services, vaccinations not mandated by ACA, or international emergency "
            "coverage beyond the $50,000 emergency-only benefit.",
            "Surrogacy-related services or expenses.",
            "Services provided by non-licensed practitioners or outside the United States "
            "(except emergency stabilization).",
        ]
    )

    # ── 4.1 Machine-readable CPT exclusion table ────────────
    pdf.ln(4)
    pdf.set_font("helvetica", "B", 12)
    pdf.set_text_color(*BRAND_BLUE)
    pdf.cell(0, 8, "4.1 Excluded CPT Code Ranges (Machine-Readable)", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_text_color(*BODY_GRAY)
    pdf.set_font("helvetica", "", 10)
    pdf.multi_cell(
        180,
        5.5,
        "The table below lists CPT code ranges explicitly excluded from the MediShield Gold Plan. "
        "Claims with codes in these ranges are automatically denied unless a qualifying rider is active. "
        "Codes not listed here are subject to medical necessity review per Section 5.",
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

    # ════════════════════════════════════════════════════════
    # 6. OPTIONAL RIDERS  (page 6)
    # ════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section_title("5. Optional Riders")
    pdf.body(
        "The following optional coverage riders may be attached to the MediShield Gold Plan "
        "for an additional premium. Riders must be elected at policy inception or at the "
        "annual renewal date. Mid-term rider additions are subject to Medical Review approval. "
        "Each rider's benefits are subject to its own sub-limit and waiting period, "
        "independent of the base policy."
    )

    riders = [
        (
            "5.1 Maternity Rider",
            "$10,000 per pregnancy (lifetime maximum: 2 pregnancies per policy)",
            "9 months from rider effective date",
            [
                "Prenatal consultations and routine prenatal diagnostic tests.",
                "Labor, normal vaginal delivery, and Cesarean section (C-section).",
                "Hospital room and board during delivery admission.",
                "Anesthesia (epidural or general) during delivery.",
                "Postnatal care for mother: up to 6 weeks post-delivery.",
                "Newborn care from birth through 31 days (must add infant to policy within 31 days).",
                "Medically necessary fertility workup (diagnosis only, not treatment).",
            ],
            [
                "Infertility treatment and assisted reproductive technology (IVF, IUI).",
                "Elective abortion (therapeutic abortion for medical necessity is covered).",
                "Maternity expenses beyond the $10,000 sub-limit.",
            ],
        ),
        (
            "5.2 Critical Illness Rider",
            "$50,000 lump-sum upon first diagnosis (per covered condition, lifetime)",
            "90 days from rider effective date",
            [
                "Invasive cancer (excluding skin cancer unless melanoma).",
                "Acute myocardial infarction (heart attack) of specified severity.",
                "Stroke resulting in permanent neurological deficit.",
                "Coronary artery bypass graft (CABG) surgery.",
                "Kidney failure requiring permanent dialysis.",
                "Major organ transplant (heart, lung, liver, kidney, pancreas).",
                "Coma of specified severity lasting >96 continuous hours.",
                "Loss of limbs (permanent loss of use of two or more limbs).",
                "Blindness (permanent and irrecoverable loss of sight in both eyes).",
                "Alzheimer's disease (resulting in total dependency) -- subject to 6-month survival.",
            ],
            [
                "Conditions diagnosed before the waiting period expires.",
                "Non-invasive cancer or carcinoma in situ.",
                "Alcohol- or drug-induced conditions.",
                "Any condition arising from pre-existing conditions within the first 90 days.",
            ],
        ),
        (
            "5.3 Outpatient Department (OPD) Rider",
            "$2,000 per policy year",
            "30 days from rider effective date",
            [
                "Outpatient physician and specialist consultations not requiring hospitalization.",
                "Diagnostic tests ordered on an outpatient basis (lab, imaging).",
                "Outpatient prescription drugs up to the OPD sub-limit.",
                "Outpatient physiotherapy, occupational therapy, and speech therapy sessions.",
                "Minor outpatient procedures not requiring a Day Care designation.",
                "Dental emergency treatment (accidental injury to teeth only).",
            ],
            [
                "Cosmetic or aesthetic outpatient procedures.",
                "Vitamins, supplements, and over-the-counter medications.",
                "Outpatient services covered under the base policy (no double-dipping).",
                "Services in excess of the $2,000 OPD sub-limit.",
            ],
        ),
    ]

    for rname, sublimit, wait, inclusions, exclusions in riders:
        pdf.section_title(rname, level=2)
        pdf.set_font("helvetica", "B", 10)
        pdf.set_text_color(*BODY_GRAY)
        pdf.set_x(15)
        pdf.cell(60, 7, "Sub-Limit:")
        pdf.set_font("helvetica", "", 10)
        pdf.cell(0, 7, sublimit, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("helvetica", "B", 10)
        pdf.set_x(15)
        pdf.cell(60, 7, "Waiting Period:")
        pdf.set_font("helvetica", "", 10)
        pdf.cell(0, 7, wait, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        pdf.set_font("helvetica", "B", 10)
        pdf.set_x(15)
        pdf.cell(0, 7, "Covered under this Rider:", new_x="LMARGIN", new_y="NEXT")
        pdf.bullet(inclusions, indent=8)
        pdf.set_font("helvetica", "B", 10)
        pdf.set_x(15)
        pdf.cell(0, 7, "Excluded under this Rider:", new_x="LMARGIN", new_y="NEXT")
        pdf.bullet(exclusions, indent=8)
        pdf.ln(3)

    # ════════════════════════════════════════════════════════
    # 7. CLAIMS PROCEDURE  (page 7)
    # ════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section_title("6. Claims Procedure")
    pdf.body(
        "MediShield processes claims via two workflows depending on whether the Provider is "
        "a Network Provider (Cashless Authorization) or an Out-of-Network Provider "
        "(Reimbursement). Claims must be submitted within the timelines specified below. "
        "Late submissions will be denied unless the delay was due to circumstances beyond "
        "the Policyholder's reasonable control."
    )

    pdf.section_title("6.1 Cashless Authorization Workflow (Network Providers)", level=2)
    pdf.bullet(
        [
            "Present your MediShield Gold Plan ID Card at the Network Provider's insurance / "
            "billing desk at the time of admission or registration.",
            "The Network Provider submits a Pre-Authorization Request (PAR) to MediShield via the "
            "Provider Portal or MediShield's 24/7 authorization hotline (1-800-MEDI-PRE).",
            "MediShield will review and issue a Cashless Authorization decision within 2 hours for "
            "planned admissions and within 30 minutes for emergency admissions.",
            "For planned elective procedures, submit the PAR at least 5 business days in advance.",
            "Upon discharge, review the final itemized bill, sign the Policyholder Discharge "
            "Acknowledgment form, and retain a copy for your records.",
            "MediShield will settle the approved amount directly with the Network Provider within "
            "15 business days of receiving the complete final bill.",
            "Any charges not covered or in excess of approved amounts remain the "
            "Policyholder's responsibility and are due directly to the Provider.",
        ]
    )

    pdf.section_title("6.2 Reimbursement Workflow (Out-of-Network Providers)", level=2)
    pdf.bullet(
        [
            "Pay all hospital and physician bills at the time of service or discharge.",
            "Collect original versions of all documents listed in the Document Checklist below.",
            "Submit a completed MediShield Claim Form (Form MS-1500) along with all supporting "
            "documents to MediShield within 15 days of discharge date.",
            "Claims may be submitted via: (a) MediShield Member Portal (preferred); "
            "(b) email to claims@medishield-insurance.com; or (c) mail to MediShield Claims "
            "Department, P.O. Box 5000, Chicago, IL 60690.",
            "MediShield will acknowledge receipt of the claim within 3 business days.",
            "MediShield will process and settle the approved reimbursement amount within a "
            "30-day Turn-Around Time (TAT) from receipt of a complete claim package.",
            "Incomplete claims will be returned with a Deficiency Notice within 10 business days; "
            "the Policyholder has 30 days to resubmit the complete package.",
        ]
    )

    pdf.section_title("6.3 Document Checklist (Reimbursement Claims)", level=2)
    checklist = [
        "Completed and signed MediShield Claim Form (MS-1500) -- all fields mandatory",
        "Original Hospital Discharge Summary signed by Attending Physician",
        "Original itemized hospital bill and all payment receipts",
        "Original pharmacy bills with prescription copies",
        "All diagnostic test reports (lab, imaging, pathology)",
        "Physician's referral letter or consultation notes (for specialist visits)",
        "Copy of Policyholder's government-issued photo ID (Driver's License or Passport)",
        "Copy of MediShield Gold Plan ID Card (front and back)",
        "Bank account details for reimbursement transfer (cancelled check or bank statement)",
        "Pre-Authorization approval letter (if pre-authorization was obtained)",
        "For accidental injuries: First Information Report (FIR) or police report (if applicable)",
        "For critical illness claims: Specialist's diagnosis report on institutional letterhead",
    ]
    pdf.set_font("helvetica", "", 10)
    pdf.set_text_color(*BODY_GRAY)
    for i, item in enumerate(checklist, 1):
        pdf.set_x(15)
        pdf.cell(8, 7, f"{i}.")
        pdf.multi_cell(172, 7, item)
    pdf.ln(3)

    pdf.section_title("6.4 Grievance Redressal", level=2)
    pdf.body(
        "MediShield is committed to resolving all policyholder grievances fairly and promptly. "
        "If you are dissatisfied with a claim decision or the quality of service received, "
        "you may file a formal grievance through the following channels:"
    )
    pdf.bullet(
        [
            "Email: grievances@medishield-insurance.com (response within 5 business days)",
            "Phone: 1-800-MED-HELP (1-800-633-4357) -- Grievance Helpline, Mon-Fri 8am-8pm CT",
            "Mail: MediShield Grievance Redressal Officer, 123 Healthcare Blvd Suite 500, "
            "Chicago, IL 60601",
            "Online Portal: www.medishield-insurance.com/grievance",
        ]
    )
    pdf.body(
        "MediShield will issue a written acknowledgment within 3 business days and a final "
        "resolution decision within 30 calendar days of receiving a complete grievance. "
        "If you remain unsatisfied, you may escalate to the Illinois Department of Insurance "
        "(IDOI) at www.insurance.illinois.gov or 1-866-445-5364."
    )

    # ════════════════════════════════════════════════════════
    # 8. HIPAA COMPLIANCE & ATTESTATION  (page 8)
    # ════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section_title("7. HIPAA Compliance -- Notice of Privacy Practices")
    pdf.body(
        "MediShield Health Insurance Ltd. ('MediShield') is required by law to maintain the "
        "privacy and security of your Protected Health Information (PHI) and to provide you "
        "with this Notice of Privacy Practices. This notice describes how medical information "
        "about you may be used and disclosed, and how you can access this information."
    )
    pdf.section_title("7.1 Uses and Disclosures Permitted Without Authorization", level=2)
    pdf.bullet(
        [
            "Treatment: We may use or disclose your PHI to facilitate medical treatment or "
            "services by your healthcare providers.",
            "Payment: We may use or disclose your PHI to process claims, obtain reimbursement, "
            "and coordinate benefits with other insurers.",
            "Healthcare Operations: We may use your PHI for quality assessment, underwriting, "
            "premium rating, fraud detection, and compliance activities.",
            "Public Health Activities: As required by law for reporting communicable diseases, "
            "adverse drug events, or product safety issues.",
            "Law Enforcement: In response to a valid court order, subpoena, or law enforcement "
            "request as permitted under HIPAA.",
            "Business Associates: We share PHI with vendors and service providers ("
            "Business Associates) who assist us in operating our business, subject to a "
            "Business Associate Agreement (BAA) requiring them to protect your PHI.",
        ]
    )
    pdf.section_title("7.2 Uses and Disclosures Requiring Your Authorization", level=2)
    pdf.bullet(
        [
            "Marketing communications not related to your current health plan.",
            "Sale of your PHI to third parties.",
            "Disclosure of psychotherapy notes (with limited exceptions).",
            "Any use or disclosure not described in this Notice.",
        ]
    )
    pdf.section_title("7.3 Your Rights Regarding Your PHI", level=2)
    pdf.bullet(
        [
            "Right to Access: Request copies of your medical records and claims history.",
            "Right to Amend: Request corrections to inaccurate or incomplete information.",
            "Right to an Accounting of Disclosures: Request a list of disclosures made without "
            "your authorization.",
            "Right to Restrict Disclosures: Request limitations on how we use your PHI.",
            "Right to Confidential Communications: Request that we communicate with you through "
            "a specific method or at a specific location.",
            "Right to Opt Out: Opt out of receiving marketing materials.",
            "Right to File a Complaint: File a complaint with MediShield's Privacy Officer or "
            "the US Department of Health and Human Services (HHS) at www.hhs.gov/hipaa/complaints.",
        ]
    )
    pdf.body(
        "To exercise any of these rights, contact our Privacy Officer: "
        "privacy@medishield-insurance.com | 1-800-MEDISHIELD | "
        "MediShield Privacy Officer, 123 Healthcare Blvd Suite 500, Chicago IL 60601."
    )
    pdf.body(
        "MediShield maintains physical, administrative, and technical safeguards to protect "
        "your PHI, including encryption of electronic PHI (ePHI) at rest and in transit, "
        "role-based access controls, and annual HIPAA compliance training for all staff. "
        "In the event of a breach of unsecured PHI, we will notify you within 60 days as "
        "required by the HIPAA Breach Notification Rule (45 CFR Part 164, Subpart D)."
    )

    # ════════════════════════════════════════════════════════
    # 8. ERISA DISCLOSURE  (continues after HIPAA)
    # ════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.section_title("8. ERISA Disclosure")
    pdf.body(
        "If this policy is offered through an employer-sponsored group health plan, it may be "
        "subject to the Employee Retirement Income Security Act of 1974 (ERISA), as amended, "
        "29 U.S.C. S 1001 et seq. ERISA provides certain rights and protections to participants "
        "and beneficiaries in employer-sponsored health plans."
    )
    pdf.section_title("8.1 ERISA Rights of Plan Participants", level=2)
    pdf.bullet(
        [
            "Right to examine plan documents and Summary Plan Description (SPD) without charge "
            "at the plan administrator's office.",
            "Right to obtain copies of plan documents upon written request to the plan administrator "
            "(a reasonable charge may apply).",
            "Right to receive a Summary of Benefits and Coverage (SBC) prior to enrollment and "
            "at each annual renewal.",
            "Right to appeal denied claims through the plan's internal appeals process and, "
            "if unsatisfied, to pursue external review under applicable state or federal law.",
            "Right to file a complaint or lawsuit under ERISA Section 502(a) if benefits are "
            "denied or rights under the plan are violated.",
        ]
    )
    pdf.section_title("8.2 Plan Administrator Contact", level=2)
    pdf.body(
        "For employer-sponsored plans, the plan administrator is identified in the group "
        "enrollment documentation provided by the sponsoring employer. For individually "
        "purchased policies, ERISA does not apply; this policy is governed solely by "
        "Illinois state insurance law."
    )
    pdf.body(
        "IMPORTANT: If you believe the plan administrator has failed to provide required "
        "information, you may contact the U.S. Department of Labor, Employee Benefits Security "
        "Administration (EBSA) at www.dol.gov/ebsa or 1-866-444-3272."
    )

    # ════════════════════════════════════════════════════════
    # 9. ILLINOIS DEPARTMENT OF INSURANCE -- REGULATORY NOTICE
    # ════════════════════════════════════════════════════════
    pdf.section_title("9. Illinois Department of Insurance -- Regulatory Notice")
    pdf.body(
        "This policy is issued in the State of Illinois and is subject to the regulatory "
        "oversight of the Illinois Department of Insurance (IDOI). MediShield Health Insurance "
        "Ltd. is licensed to transact insurance business in Illinois under License No. IL-HLT-2025."
    )
    pdf.bullet(
        [
            "Illinois DOI Consumer Hotline: 1-866-445-5364 (toll-free)",
            "Illinois DOI Website: www.insurance.illinois.gov",
            "Illinois DOI Mailing Address: Illinois Department of Insurance, "
            "320 W. Washington St., Springfield, IL 62767",
            "Online Complaint Filing: www.insurance.illinois.gov/consumer/complaint.asp",
        ]
    )
    pdf.body(
        "Illinois residents have the right to file a complaint with the IDOI if they believe "
        "MediShield has violated any provision of the Illinois Insurance Code (215 ILCS 5), "
        "including improper claims denial, misrepresentation, or failure to provide required "
        "disclosures. The IDOI may investigate complaints and take regulatory action including "
        "fines, license suspension, or revocation."
    )
    pdf.body(
        "This policy complies with all applicable Illinois insurance statutes and administrative "
        "rules, including the Illinois Life and Health Insurance Guaranty Association Act "
        "(215 ILCS 105), which provides limited protection to policyholders in the event of "
        "insurer insolvency (up to $500,000 for health insurance claims)."
    )

    # ── Attestation — always starts on its own page ──────────
    pdf.add_page()
    pdf.section_title("10. Policyholder Attestation")
    pdf.body("By signing below, the Policyholder acknowledges and agrees that:")
    pdf.bullet(
        [
            "I have received, read, and understood this MediShield Gold Plan policy document, "
            "including the Schedule of Benefits, Definitions, Inclusions, Exclusions, Optional "
            "Riders, Claims Procedure, and Notice of Privacy Practices.",
            "All information provided in my insurance application is true, accurate, and complete "
            "to the best of my knowledge. Misrepresentation or omission of material facts may "
            "result in rescission of this policy.",
            "I authorize MediShield Health Insurance Ltd. to obtain, use, and disclose my "
            "Protected Health Information (PHI) as described in the Notice of Privacy Practices "
            "for the purposes of administering this policy.",
            "I agree to notify MediShield within 30 days of any changes to my household "
            "composition, address, or other material information that may affect this policy.",
            "I understand that this policy is governed by the laws of the State of Illinois and "
            "subject to the regulatory oversight of the Illinois Department of Insurance.",
        ]
    )

    # Disable auto-page-break so the signature block + office-use box
    # never get split across pages by FPDF.
    pdf.set_auto_page_break(False)
    pdf.ln(14)
    pdf.set_font("helvetica", "", 11)
    pdf.set_text_color(*BODY_GRAY)

    # Row 1: Policyholder Signature | Date
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

    # Row 2: Printed Name | Policy Number
    pdf.ln(14)
    sig_y2 = pdf.get_y()
    pdf.line(15, sig_y2, 90, sig_y2)
    pdf.line(110, sig_y2, 195, sig_y2)
    pdf.ln(2)
    pdf.set_x(15)
    pdf.cell(75, 6, "Printed Name of Policyholder")
    pdf.set_x(110)
    pdf.cell(85, 6, "Policy Number (MED-GLD-XXXXXXX)", new_x="LMARGIN", new_y="NEXT")

    # FOR OFFICE USE ONLY box — all drawn at absolute Y, no page-break risk
    pdf.ln(14)
    box_y = pdf.get_y()
    pdf.set_fill_color(240, 241, 250)
    pdf.set_draw_color(*BRAND_BLUE)
    pdf.rect(15, box_y, 180, 30, "FD")

    pdf.set_font("helvetica", "B", 8)
    pdf.set_text_color(*BRAND_BLUE)
    pdf.set_xy(18, box_y + 3)
    pdf.cell(60, 5, "FOR OFFICE USE ONLY")

    pdf.set_draw_color(160, 165, 200)
    pdf.line(15, box_y + 11, 195, box_y + 11)

    pdf.set_font("helvetica", "", 8)
    pdf.set_text_color(80, 80, 100)

    pdf.set_xy(18, box_y + 14)
    pdf.cell(58, 4, "Authorized MediShield Officer:")
    pdf.set_x(80)
    pdf.cell(38, 4, "Approval Date:")
    pdf.set_x(130)
    pdf.cell(62, 4, "Policy Issuance Ref #:")

    pdf.set_draw_color(120, 120, 145)
    pdf.line(18, box_y + 26, 76, box_y + 26)
    pdf.line(80, box_y + 26, 126, box_y + 26)
    pdf.line(130, box_y + 26, 193, box_y + 26)

    # Restore auto-page-break for any subsequent content
    pdf.set_auto_page_break(True, margin=20)

    # ── Save ──────────────────────────────────────────────────
    out_dir = os.environ.get(
        "POLICY_OUT_DIR",
        os.path.join(os.environ.get("DOC_OUT_DIR", "dataset"), "policies"),
    )
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "medishield_gold_plan.pdf")
    pdf.output(out_path)
    return out_path


if __name__ == "__main__":
    path = create_policy_document()
    print(f"Policy document generated: {path}")
