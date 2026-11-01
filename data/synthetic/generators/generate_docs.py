import json
import os
import random
from datetime import datetime, timedelta
from decimal import Decimal

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

random.seed(42)
np.random.seed(42)
TRUTH = {}
rng = random.Random(42)


# ──────────────────────────────────────────────
# Font helpers
# ──────────────────────────────────────────────
def fnt(name, size):
    for candidate in [name, f"C:\\Windows\\Fonts\\{name}"]:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            pass
    return ImageFont.load_default()


FONT_REG = "arial.ttf"
FONT_BOLD = "arialbd.ttf"
FONT_ITAL = "ariali.ttf"
FONT_MONO = "cour.ttf"

_SIG_CANDIDATES = [
    r"C:\Windows\Fonts\segoesc.ttf",
    r"C:\Windows\Fonts\BRADHITC.TTF",
    r"C:\Windows\Fonts\segoepr.ttf",
]


def signature_fnt(size):
    for p in _SIG_CANDIDATES:
        try:
            if os.path.exists(p):
                return ImageFont.truetype(p, size)
        except Exception:
            pass
    return fnt(FONT_ITAL, size)


SIG_INK = (18, 18, 80)


# ──────────────────────────────────────────────
# Pillow drawing utilities
# ──────────────────────────────────────────────
def gradient_rect(draw, x0, y0, x1, y1, c0, c1, vertical=True):
    steps = (y1 - y0) if vertical else (x1 - x0)
    for i in range(max(steps, 1)):
        t = i / max(steps - 1, 1)
        color = tuple(int(c0[k] + (c1[k] - c0[k]) * t) for k in range(3))
        if vertical:
            draw.line([(x0, y0 + i), (x1, y0 + i)], fill=color)
        else:
            draw.line([(x0 + i, y0), (x0 + i, y1)], fill=color)


def draw_barcode(draw, x, y, w=180, h=40, color=(20, 20, 20)):
    cx = x
    r = random.Random(x * 31 + y)
    while cx < x + w:
        bw = r.randint(1, 3)
        if r.random() > 0.45:
            draw.rectangle([cx, y, cx + bw - 1, y + h], fill=color)
        cx += bw + r.randint(0, 2)


def draw_qr_stub(draw, x, y, size=60, color=(10, 10, 10)):
    cell = max(1, size // 7)
    r = random.Random(x + y * 1000)
    for row in range(7):
        for col in range(7):
            filled = r.random() > 0.45
            if (row < 3 and col < 3) or (row < 3 and col > 3) or (row > 3 and col < 3):
                filled = True
            if filled:
                draw.rectangle(
                    [
                        x + col * cell,
                        y + row * cell,
                        x + col * cell + cell - 2,
                        y + row * cell + cell - 2,
                    ],
                    fill=color,
                )


def draw_checkbox(draw, x, y, size=14, checked=False, color=(50, 50, 80)):
    draw.rectangle([x, y, x + size, y + size], outline=color, width=1)
    if checked:
        draw.line([x + 2, y + 7, x + 5, y + size - 2], fill=color, width=2)
        draw.line([x + 5, y + size - 2, x + size - 1, y + 2], fill=color, width=2)


def draw_rounded_rect(draw, x0, y0, x1, y1, radius=8, fill=None, outline=None, width=1):
    if fill:
        draw.rectangle([x0 + radius, y0, x1 - radius, y1], fill=fill)
        draw.rectangle([x0, y0 + radius, x1, y1 - radius], fill=fill)
        for cx, cy in [
            (x0, y0),
            (x1 - 2 * radius, y0),
            (x0, y1 - 2 * radius),
            (x1 - 2 * radius, y1 - 2 * radius),
        ]:
            draw.ellipse([cx, cy, cx + 2 * radius, cy + 2 * radius], fill=fill)
    if outline:
        draw.arc([x0, y0, x0 + 2 * radius, y0 + 2 * radius], 180, 270, fill=outline, width=width)
        draw.arc([x1 - 2 * radius, y0, x1, y0 + 2 * radius], 270, 360, fill=outline, width=width)
        draw.arc([x0, y1 - 2 * radius, x0 + 2 * radius, y1], 90, 180, fill=outline, width=width)
        draw.arc([x1 - 2 * radius, y1 - 2 * radius, x1, y1], 0, 90, fill=outline, width=width)
        draw.line([x0 + radius, y0, x1 - radius, y0], fill=outline, width=width)
        draw.line([x0 + radius, y1, x1 - radius, y1], fill=outline, width=width)
        draw.line([x0, y0 + radius, x0, y1 - radius], fill=outline, width=width)
        draw.line([x1, y0 + radius, x1, y1 - radius], fill=outline, width=width)


def add_scan_effect(img, blur=False):
    angle = random.uniform(-2.0, 2.0)
    img = img.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=(255, 255, 255))
    arr = np.array(img).astype(np.float32)
    arr = np.clip(arr + np.random.normal(0, 3.5, arr.shape), 0, 255)
    img2 = Image.fromarray(arr.astype(np.uint8))
    if blur:
        img2 = img2.filter(ImageFilter.GaussianBlur(radius=random.uniform(0.8, 2.0)))
    return ImageEnhance.Contrast(img2).enhance(1.05)


# ──────────────────────────────────────────────
# US synthetic data pools
# ──────────────────────────────────────────────
NAMES_M = [
    "James Smith",
    "John Johnson",
    "Robert Williams",
    "Michael Brown",
    "William Jones",
    "David Garcia",
    "Richard Martinez",
    "Joseph Anderson",
    "Thomas Jackson",
    "Charles White",
    "Christopher Harris",
    "Daniel Taylor",
    "Anthony Moore",
    "Kevin Thompson",
    "Steven Lewis",
    "Paul Walker",
]
NAMES_F = [
    "Mary Davis",
    "Patricia Miller",
    "Jennifer Wilson",
    "Linda Moore",
    "Elizabeth Taylor",
    "Barbara Anderson",
    "Susan Thomas",
    "Jessica Jackson",
    "Sarah White",
    "Karen Harris",
    "Nancy Martin",
    "Lisa Thompson",
    "Margaret Lee",
    "Betty Clark",
    "Dorothy Robinson",
    "Sandra Hall",
]
STREETS = [
    "123 Main St",
    "456 Oak Ave",
    "789 Pine Ln",
    "321 Maple Dr",
    "654 Elm St",
    "987 Cedar Ct",
    "246 Birch Blvd",
    "135 Walnut Way",
    "579 Ash Ave",
    "864 Spruce St",
    "417 Willow Rd",
    "732 Poplar Pl",
]
CITIES_IL = [
    "Chicago, IL 60601",
    "Chicago, IL 60605",
    "Chicago, IL 60611",
    "Naperville, IL 60540",
    "Evanston, IL 60201",
    "Peoria, IL 61602",
    "Rockford, IL 61101",
    "Aurora, IL 60505",
    "Joliet, IL 60435",
    "Springfield, IL 62701",
]
STATE_POOL = [
    {
        "state": "Illinois",
        "abbr": "IL",
        "cities": ["Chicago", "Naperville", "Evanston", "Peoria", "Rockford"],
        "dl_prefix": "IL",
    },
    {
        "state": "Indiana",
        "abbr": "IN",
        "cities": ["Indianapolis", "Fort Wayne", "Evansville", "South Bend"],
        "dl_prefix": "IN",
    },
    {
        "state": "Wisconsin",
        "abbr": "WI",
        "cities": ["Milwaukee", "Madison", "Green Bay", "Kenosha"],
        "dl_prefix": "WI",
    },
    {
        "state": "Michigan",
        "abbr": "MI",
        "cities": ["Detroit", "Grand Rapids", "Ann Arbor", "Lansing"],
        "dl_prefix": "MI",
    },
    {
        "state": "Ohio",
        "abbr": "OH",
        "cities": ["Columbus", "Cleveland", "Cincinnati", "Toledo"],
        "dl_prefix": "OH",
    },
    {
        "state": "Minnesota",
        "abbr": "MN",
        "cities": ["Minneapolis", "Saint Paul", "Duluth", "Rochester"],
        "dl_prefix": "MN",
    },
    {
        "state": "Missouri",
        "abbr": "MO",
        "cities": ["St. Louis", "Kansas City", "Springfield", "Columbia"],
        "dl_prefix": "MO",
    },
    {
        "state": "Tennessee",
        "abbr": "TN",
        "cities": ["Nashville", "Memphis", "Knoxville", "Chattanooga"],
        "dl_prefix": "TN",
    },
    {
        "state": "Georgia",
        "abbr": "GA",
        "cities": ["Atlanta", "Augusta", "Savannah", "Macon"],
        "dl_prefix": "GA",
    },
    {
        "state": "Texas",
        "abbr": "TX",
        "cities": ["Houston", "Dallas", "Austin", "San Antonio"],
        "dl_prefix": "TX",
    },
    {
        "state": "Florida",
        "abbr": "FL",
        "cities": ["Miami", "Orlando", "Tampa", "Jacksonville"],
        "dl_prefix": "FL",
    },
    {
        "state": "New York",
        "abbr": "NY",
        "cities": ["New York City", "Buffalo", "Albany", "Rochester"],
        "dl_prefix": "NY",
    },
    {
        "state": "Pennsylvania",
        "abbr": "PA",
        "cities": ["Philadelphia", "Pittsburgh", "Allentown", "Erie"],
        "dl_prefix": "PA",
    },
    {
        "state": "Kentucky",
        "abbr": "KY",
        "cities": ["Louisville", "Lexington", "Bowling Green", "Covington"],
        "dl_prefix": "KY",
    },
]
HOSPITALS = [
    "Northwestern Memorial Hospital",
    "Rush University Medical Center",
    "University of Chicago Medical Center",
    "Advocate Christ Medical Center",
    "Loyola University Medical Center",
    "UI Health – University of Illinois Hospital",
    "Advocate Illinois Masonic Medical Center",
    "OSF Saint Francis Medical Center",
]
HOSPITAL_INFO = {
    "Northwestern Memorial Hospital": {
        "addr": "251 E Huron St, Chicago, IL 60611",
        "phone": "(312) 926-2000",
        "fax": "(312) 926-8111",
    },
    "Rush University Medical Center": {
        "addr": "1620 W Harrison St, Chicago, IL 60612",
        "phone": "(312) 942-5000",
        "fax": "(312) 942-3000",
    },
    "University of Chicago Medical Center": {
        "addr": "5841 S Maryland Ave, Chicago, IL 60637",
        "phone": "(773) 702-1000",
        "fax": "(773) 702-3456",
    },
    "Advocate Christ Medical Center": {
        "addr": "4440 W 95th St, Oak Lawn, IL 60453",
        "phone": "(708) 684-8000",
        "fax": "(708) 684-8100",
    },
    "Loyola University Medical Center": {
        "addr": "2160 S First Ave, Maywood, IL 60153",
        "phone": "(708) 216-9000",
        "fax": "(708) 216-5800",
    },
    "UI Health – University of Illinois Hospital": {
        "addr": "1740 W Taylor St, Chicago, IL 60612",
        "phone": "(312) 996-7000",
        "fax": "(312) 996-7234",
    },
    "Advocate Illinois Masonic Medical Center": {
        "addr": "836 W Wellington Ave, Chicago, IL 60657",
        "phone": "(773) 975-1600",
        "fax": "(773) 975-1700",
    },
    "OSF Saint Francis Medical Center": {
        "addr": "530 NE Glen Oak Ave, Peoria, IL 61637",
        "phone": "(309) 655-2000",
        "fax": "(309) 655-2100",
    },
}

HOSPITAL_DOC_STYLES = {
    "Northwestern Memorial Hospital": 0,
    "Rush University Medical Center": 0,
    "University of Chicago Medical Center": 1,
    "Loyola University Medical Center": 1,
    "UI Health – University of Illinois Hospital": 1,
    "Advocate Christ Medical Center": 2,
    "Advocate Illinois Masonic Medical Center": 2,
    "OSF Saint Francis Medical Center": 2,
}

CONTROLLED_RX = {
    "oxycodone",
    "hydrocodone",
    "alprazolam",
    "diazepam",
    "lorazepam",
    "adderall",
    "amphetamine",
}

DOCTORS = [
    ("Dr. Sarah Jenkins, MD", "NPI-1029384756"),
    ("Dr. Mark Owen, MD", "NPI-2938475610"),
    ("Dr. Emily Chen, MD", "NPI-3847561029"),
    ("Dr. James Patel, DO", "NPI-4756102938"),
    ("Dr. Rachel Kim, MD", "NPI-5610293847"),
    ("Dr. David Nguyen, MD", "NPI-6102938475"),
    ("Dr. Monica Suarez, MD", "NPI-7293847561"),
    ("Dr. Brian Wallace, MD", "NPI-8374651029"),
]

ICD10_POOL = [
    ("E11.9", "Type 2 diabetes mellitus without complications"),
    ("I10", "Essential (primary) hypertension"),
    ("J01.90", "Acute sinusitis, unspecified"),
    ("M54.5", "Low back pain"),
    ("K35.80", "Unspecified acute appendicitis"),
    ("J18.9", "Unspecified pneumonia"),
    ("I25.10", "Coronary artery disease without angina pectoris"),
    ("M17.11", "Primary osteoarthritis, right knee"),
    ("N39.0", "Urinary tract infection, site not specified"),
    ("S52.501A", "Unspecified fracture of lower end of radius, initial encounter"),
    ("F32.1", "Major depressive disorder, single episode, moderate"),
    ("G43.909", "Migraine, unspecified, not intractable"),
    ("K21.0", "Gastro-esophageal reflux disease with esophagitis"),
    ("M75.100", "Unspecified rotator cuff syndrome"),
]
ICD_POOL = ICD10_POOL  # alias used in cluster generation

CPT_POOL = [
    ("99213", "Office/outpatient visit, estab. patient, low complexity", 120.00),
    ("99214", "Office/outpatient visit, estab. patient, mod. complexity", 185.00),
    ("99215", "Office/outpatient visit, estab. patient, high complexity", 260.00),
    ("71046", "Radiologic examination, chest, 2 views", 110.00),
    ("85025", "Blood count, complete (CBC) with auto differential WBC", 55.00),
    ("80053", "Comprehensive metabolic panel", 75.00),
    ("44970", "Laparoscopy, surgical, appendectomy", 8750.00),
    ("27447", "Arthroplasty, knee, condyle & plateau – total knee replacement", 15400.00),
    ("99284", "Emergency department visit, problem of high severity", 680.00),
    ("93000", "Electrocardiogram, routine ECG with at least 12 leads", 95.00),
    ("71250", "CT thorax without contrast material", 1250.00),
    ("70553", "MRI brain with contrast material", 2100.00),
    ("36415", "Collection of venous blood by venipuncture", 35.00),
    ("43239", "Esophagogastroduodenoscopy (EGD) with biopsy", 3400.00),
    ("99291", "Critical care, first 30–74 minutes", 1100.00),
    ("93306", "Echocardiography, transthoracic, complete", 1450.00),
    ("72148", "MRI lumbar spine without contrast", 1800.00),
    ("90837", "Psychotherapy Session, 60 min", 250.00),
    ("33533", "CABG — Arterial, Single Vessel", 85000.00),
    ("27447", "Total Knee Arthroplasty", 42000.00),
    ("43239", "EGD w/ Biopsy (Upper GI Endoscopy)", 3200.00),
    ("47562", "Laparoscopic Cholecystectomy", 18500.00),
    ("29827", "Shoulder Arthroscopy w/ Rotator Cuff Repair", 22000.00),
]

UNCOVERED_CPT = [
    ("15822", "Blepharoplasty, upper eyelid – Cosmetic procedure", 4500.00),
    ("17000", "Destruction, premalignant lesions – Aesthetic/Cosmetic", 1200.00),
    ("58300", "Insertion of intrauterine device (IUD) – Fertility-related", 850.00),
    ("86849", "Unlisted immunology procedure – Investigational/Experimental", 3200.00),
    ("21120", "Genioplasty – Cosmetic craniofacial surgery", 6800.00),
]

RX_POOL = [
    ("Omeprazole", "Prilosec", "Take 1 capsule 30 min before breakfast", 30, "$24/month", 2),
    ("Metformin", "Glucophage", "Take 1 tablet twice daily with meals", 30, "$12/month", 3),
    ("Lisinopril", "Zestril", "Take 1 tablet once daily", 30, "$18/month", 3),
    ("Atorvastatin", "Lipitor", "Take 1 tablet at bedtime", 30, "$45/month", 3),
    ("Amlodipine", "Norvasc", "Take 1 tablet once daily", 30, "$22/month", 3),
    ("Sertraline", "Zoloft", "Take 1 tablet once daily with food", 30, "$35/month", 2),
    ("Albuterol", "ProAir HFA", "Inhale 2 puffs every 4-6 hrs as needed", 30, "$55/month", 1),
    ("Amoxicillin", "Amoxil", "Take 1 capsule three times daily", 10, "$18/course", 0),
    ("Oxycodone", "OxyContin", "Take 1 tablet every 4-6 hrs for pain", 30, "$180/month", 0),
    ("Alprazolam", "Xanax", "Take 0.5 mg tablet three times daily", 30, "$95/month", 0),
    ("Hydrocodone", "Vicodin", "Take 1-2 tablets every 4-6 hrs for pain", 30, "$220/month", 0),
    ("Gabapentin", "Neurontin", "Take 1 capsule three times daily", 30, "$40/month", 2),
    ("Levothyroxine", "Synthroid", "Take 1 tablet once daily on empty stomach", 30, "$28/month", 3),
    ("Montelukast", "Singulair", "Take 1 tablet once daily in the evening", 30, "$65/month", 3),
    ("Prednisone", "Deltasone", "Take 1 tablet once daily (taper schedule)", 10, "$30/course", 0),
]

AMENDMENT_TYPES = [
    ("Change of Address", "Requesting update of mailing address to new residence"),
    ("Add Dependent - Spouse", "Adding legal spouse as covered dependent"),
    ("Add Dependent - Child", "Adding qualifying child as covered dependent"),
    ("Beneficiary Change", "Updating primary beneficiary designation"),
    ("Coverage Tier Upgrade", "Requesting upgrade from Silver to Gold tier"),
    ("Rider Addition - Maternity", "Electing optional Maternity Rider coverage"),
    ("Rider Addition - Critical Illness", "Electing Critical Illness Rider"),
    ("Rider Addition - OPD", "Electing Outpatient Department (OPD) Rider"),
    ("Cancellation", "Requesting policy cancellation -- coverage termination"),
]

# Amendment-type-specific supporting documents
AMEND_DOCS = {
    "Change of Address": [
        "Government-issued Photo ID",
        "Utility bill or Lease Agreement (new address)",
        "Previous Policy Schedule",
    ],
    "Add Dependent - Spouse": [
        "Government-issued Photo ID",
        "Marriage Certificate",
        "Spouse's Government-issued Photo ID",
    ],
    "Add Dependent - Child": [
        "Government-issued Photo ID",
        "Birth Certificate or Adoption Papers",
        "Child's Social Security Card",
    ],
    "Beneficiary Change": [
        "Government-issued Photo ID",
        "Beneficiary's ID / SSN Documentation",
        "Previous Beneficiary Designation Form (if applicable)",
    ],
    "Coverage Tier Upgrade": [
        "Government-issued Photo ID",
        "Previous Policy Schedule",
        "Premium Payment Proof",
    ],
    "Rider Addition - Maternity": [
        "Government-issued Photo ID",
        "Physician Confirmation of Pregnancy (if applicable)",
        "Previous Policy Schedule",
    ],
    "Rider Addition - Critical Illness": [
        "Government-issued Photo ID",
        "Recent Medical History Report",
        "Physician Clearance Letter",
    ],
    "Rider Addition - OPD": [
        "Government-issued Photo ID",
        "Previous OPD Utilization Records (if applicable)",
        "Previous Policy Schedule",
    ],
    "Cancellation": [
        "Government-issued Photo ID",
        "Policy Schedule Document",
        "Written Cancellation Request Form",
    ],
}

# 5 colour themes — one per cluster modulo 5, applied to ALL doc types in that cluster
THEMES = [
    # 0 Navy Blue
    {
        "primary": (12, 40, 110),
        "accent": (30, 100, 200),
        "light": (228, 238, 255),
        "bg": (255, 255, 255),
        "border": (100, 130, 190),
        "name": "Navy",
    },
    # 1 Crimson Red
    {
        "primary": (140, 18, 18),
        "accent": (200, 48, 48),
        "light": (255, 228, 228),
        "bg": (255, 252, 252),
        "border": (190, 90, 90),
        "name": "Crimson",
    },
    # 2 Forest Green
    {
        "primary": (18, 88, 48),
        "accent": (38, 150, 78),
        "light": (225, 248, 232),
        "bg": (250, 255, 252),
        "border": (70, 160, 105),
        "name": "Forest",
    },
    # 3 Royal Purple
    {
        "primary": (72, 32, 118),
        "accent": (128, 68, 178),
        "light": (238, 225, 255),
        "bg": (252, 250, 255),
        "border": (138, 98, 190),
        "name": "Purple",
    },
    # 4 Amber / Gold
    {
        "primary": (118, 62, 8),
        "accent": (178, 108, 18),
        "light": (255, 238, 210),
        "bg": (255, 252, 244),
        "border": (188, 138, 55),
        "name": "Amber",
    },
]

# 5 ID document types, cycling across clusters
ID_TYPES = ["drivers_license", "passport", "state_id", "insurance_card", "medicare_card"]


def _mismatch_name(name, rng):
    """Swap one vowel to another in the first name to create a non-typo mismatch."""
    parts = name.split()
    first = parts[0]
    vowels = "aeiouAEIOU"
    for i, ch in enumerate(first):
        if ch in vowels:
            replacement = rng.choice([v for v in vowels if v != ch and v.islower() == ch.islower()])
            first = first[:i] + replacement + first[i + 1 :]
            break
    return " ".join([first] + parts[1:])


# ──────────────────────────────────────────────
# Patient cluster generation
# ──────────────────────────────────────────────
def generate_patient_clusters(num_clusters=30):
    fraud_types = [
        "duplicate_claim",
        "date_conflict",
        "proc_diag_mismatch",
        "readmission_30d",
        "amount_under_10k",
        "name_mismatch",
    ]
    fraud_types_shuffled = fraud_types[:]
    rng.shuffle(fraud_types_shuffled)

    # Deterministic edge-case indices (none overlap with fraud indices 0-5)
    nonfr = list(range(6, num_clusters))
    expired_id_idx = sorted(rng.sample(nonfr, 5))
    remaining = [i for i in nonfr if i not in expired_id_idx]
    missing_fld_idx = sorted(rng.sample(remaining, 4))
    remaining2 = [i for i in remaining if i not in missing_fld_idx]
    uncovered_idx = sorted(rng.sample(remaining2, 5))
    remaining3 = [i for i in remaining2 if i not in uncovered_idx]
    tampered_idx = sorted(rng.sample(remaining3, 3))
    remaining4 = [i for i in remaining3 if i not in tampered_idx]
    expiring_soon_idx = sorted(rng.sample(remaining4, 5))
    RX_MISSING_FIELD_TYPES = ["dea", "dosage", "refills", "drug_name"]
    rx_missing_idx = sorted(rng.sample(nonfr, 4))
    rx_indices = [i for i in range(150) if i % 5 == 3]
    blurry_doc_idx = sorted(rng.sample(rx_indices, 3))

    MISSING_FIELD_TYPES = ["dob", "npi", "diag_code", "auth_number"]

    clusters = []
    for i in range(num_clusters):
        gender = "M" if rng.random() > 0.5 else "F"
        name = rng.choice(NAMES_M if gender == "M" else NAMES_F)
        name = name + " " + chr(rng.randint(65, 90)) + "."
        dob_dt = datetime(rng.randint(1945, 2000), rng.randint(1, 12), rng.randint(1, 28))
        state_info = rng.choice(STATE_POOL)
        city = rng.choice(state_info["cities"])
        address = f"{rng.choice(STREETS)}, {city}, {state_info['abbr']}"
        ssn = f"{rng.randint(100, 999)}-{rng.randint(10, 99)}-{rng.randint(1000, 9999)}"
        policy = f"MED-GLD-{rng.randint(1000000, 9999999)}"
        group_num = f"GRP-{rng.randint(10000, 99999)}"
        doc, npi = rng.choice(DOCTORS)
        hospital = rng.choice(HOSPITALS)
        year = 2025
        month = rng.randint(1, 12)
        day = rng.randint(1, 28)
        treatment_date = datetime(year, month, day)
        los = rng.randint(2, 5)
        icd_code, icd_desc = rng.choice(ICD_POOL)
        cpt_list = rng.sample(CPT_POOL, k=rng.randint(2, 4))
        rx_list = rng.sample(RX_POOL, k=rng.randint(1, 3))
        amendment = rng.choice(AMENDMENT_TYPES)
        claim_number = f"CLM-2024-{i + 1:05d}"

        # Secondary ICD code (different from primary)
        sec_idx = rng.randint(0, len(ICD_POOL) - 1)
        if ICD_POOL[sec_idx][0] == icd_code:
            sec_idx = (sec_idx + 1) % len(ICD_POOL)
        secondary_icd = ICD_POOL[sec_idx]

        is_fraud = i < 6
        fraud_reason = fraud_types_shuffled[i] if is_fraud else None
        edge_flags = []

        if i in expired_id_idx:
            edge_flags.append("expired_id")
        if i in missing_fld_idx:
            edge_flags.append("missing_fields")
        if i in uncovered_idx:
            edge_flags.append("uncovered_procedure")
            uncov = UNCOVERED_CPT[i % len(UNCOVERED_CPT)]
            cpt_list = [uncov] + cpt_list[:1]
        if i in tampered_idx:
            edge_flags.append("tampered_id")
        if i in expiring_soon_idx:
            edge_flags.append("expiring_soon_id")
        if fraud_reason == "proc_diag_mismatch":
            # maternity procedure billed for non-maternity diagnosis
            cpt_list = [
                ("59400", "Routine obstetric care including antepartum/postpartum care", 3500.00)
            ] + cpt_list[:1]

        # Determine missing_field_type (claim form)
        mft_idx = missing_fld_idx.index(i) if i in missing_fld_idx else None
        missing_field_type = (
            MISSING_FIELD_TYPES[mft_idx % len(MISSING_FIELD_TYPES)] if mft_idx is not None else None
        )

        # Determine rx_missing_field_type (prescription)
        rx_mft_idx = rx_missing_idx.index(i) if i in rx_missing_idx else None
        rx_missing_field_type = (
            RX_MISSING_FIELD_TYPES[rx_mft_idx] if rx_mft_idx is not None else None
        )

        # Determine claim_type (10 out of 30 are UB-04 inpatient)
        claim_type = "UB04" if (i % 3 == 0) else "CMS1500"

        # Name mismatch: compute alternate display name for ID
        id_display_name = _mismatch_name(name, rng) if fraud_reason == "name_mismatch" else name

        clusters.append(
            {
                "cluster_id": f"C_{i + 1:03d}",
                "patient_id": f"PT_{rng.randint(10000, 99999)}",
                "name": name,
                "id_display_name": id_display_name,
                "gender": gender,
                "dob": dob_dt.strftime("%m/%d/%Y"),
                "address": address,
                "city": city,
                "state": state_info["state"],
                "st_abbr": state_info["abbr"],
                "ssn": ssn,
                "policy": policy,
                "group_number": group_num,
                "hospital": hospital,
                "doctor": doc,
                "npi": npi,
                "treatment_date": treatment_date,
                "los": los,
                "icd_code": icd_code,
                "icd_desc": icd_desc,
                "secondary_icd_code": secondary_icd[0],
                "secondary_icd_desc": secondary_icd[1],
                "cpt_list": cpt_list,
                "rx_list": rx_list,
                "amendment": amendment,
                "claim_number": claim_number,
                "theme_idx": HOSPITALS.index(hospital) % len(THEMES),
                **(
                    {"claim_service_date": treatment_date}
                    if fraud_reason == "date_conflict"
                    else {}
                ),
                "id_type": (
                    "drivers_license"
                    if fraud_reason == "name_mismatch" or i in tampered_idx
                    else ID_TYPES[i % len(ID_TYPES)]
                ),
                "is_fraud": is_fraud,
                "fraud_reason": fraud_reason,
                "edge_flags": edge_flags,
                "missing_field_type": missing_field_type,
                "rx_missing_field_type": rx_missing_field_type,
                "claim_type": (
                    "CMS1500"
                    if fraud_reason == "amount_under_10k" or i in missing_fld_idx
                    else claim_type
                ),
            }
        )

    return clusters, blurry_doc_idx


# ──────────────────────────────────────────────
# PDF save with optional scan simulation
# ──────────────────────────────────────────────
def save_image(img, path, scan=True, blur=False):
    r = rng.random()
    if blur or (scan and r < 0.4):
        img = add_scan_effect(img, blur=blur)
    else:
        img = img.convert("RGB")
    if path.endswith(".jpg"):
        img.save(path, "JPEG", quality=88)
    else:
        img.save(path, "PNG")


# ──────────────────────────────────────────────
# Document generators (Pillow)
# ──────────────────────────────────────────────


# ── Helper: shared photo-placeholder ─────────────────
def _photo_box(d, x, y, w, h, border_color):
    draw_rounded_rect(
        d, x, y, x + w, y + h, radius=6, fill=(205, 212, 228), outline=border_color, width=2
    )
    cx = x + w // 2
    # head
    d.ellipse([cx - 38, y + 18, cx + 38, y + 98], fill=(155, 160, 175))
    # shoulders
    d.ellipse([cx - 68, y + 98, cx + 68, y + h - 4], fill=(155, 160, 175))


def _exp_dates(c, expired):
    exp = c["treatment_date"] + timedelta(days=365 * 4)
    if expired:
        exp = c["treatment_date"] - timedelta(days=rng.randint(15, 120))
    elif "expiring_soon_id" in c.get("edge_flags", []):
        exp = c["treatment_date"] + timedelta(days=rng.randint(10, 29))
    return exp, (200, 0, 0) if expired else (0, 0, 0)


def _record_truth(doc_id, c, **fields):
    TRUTH[doc_id] = {
        "patient_id": c["patient_id"],
        "policy_number": c["policy"],
        "cluster_id": c["cluster_id"],
        "reference_date": c["treatment_date"],
        **fields,
    }


# ── 1. Driver's License ─────────────────────
def _id_drivers_license(
    c, expired=False, blur=False, tampered=False, display_name=None, doc_id=None
):
    W, H = 856, 540
    img = Image.new("RGB", (W, H), (240, 248, 255))
    d = ImageDraw.Draw(img)

    state_name = c.get("state", "Illinois").upper()
    city_state = f"{c.get('city', 'Chicago')}, {c.get('st_abbr', 'IL')}"

    gradient_rect(d, 0, 0, W, 90, (20, 48, 150), (38, 78, 200))
    d.text((20, 14), f"STATE OF {state_name}", font=fnt(FONT_BOLD, 14), fill=(190, 215, 255))
    d.text((20, 33), "DRIVER'S LICENSE", font=fnt(FONT_BOLD, 32), fill=(255, 255, 255))
    d.text((W - 230, 28), "* REAL ID *", font=fnt(FONT_BOLD, 20), fill=(255, 215, 0))
    d.rectangle([0, 90, W, 94], fill=(255, 200, 0))

    _photo_box(d, 40, 108, 192, 318, (75, 100, 165))
    d.text((92, 434), "PHOTO ID", font=fnt(FONT_BOLD, 13), fill=(110, 120, 150))

    shown_name = display_name if display_name is not None else c["name"]
    dl_num = f"D{rng.randint(1000, 9999)}-{rng.randint(1000, 9999)}-{rng.randint(1000, 9999)}"
    pairs = [
        ("DLN:", dl_num, FONT_MONO, 16),
        ("NAME:", shown_name.upper(), FONT_BOLD, 21),
        ("ADDRESS:", c["address"].split(",")[0].strip().upper(), FONT_REG, 15),
    ]
    y = 110
    for label, val, fn, sz in pairs:
        d.text((250, y), label, font=fnt(FONT_BOLD, 13), fill=(40, 40, 80))
        d.text((250, y + 20), val, font=fnt(fn, sz), fill=(0, 0, 0))
        y += 65

    d.text((250, y - 30), city_state.upper(), font=fnt(FONT_REG, 14), fill=(0, 0, 0))

    d.text((250, 305), "DOB:", font=fnt(FONT_BOLD, 13), fill=(40, 40, 80))
    d.text((298, 305), c["dob"], font=fnt(FONT_BOLD, 18), fill=(180, 0, 0))
    d.text((490, 305), "SEX:", font=fnt(FONT_BOLD, 13), fill=(40, 40, 80))
    d.text((530, 305), c["gender"], font=fnt(FONT_REG, 18), fill=(0, 0, 0))

    exp_date, exp_color = _exp_dates(c, expired)
    printed_exp_date = exp_date + timedelta(days=365) if tampered else exp_date
    d.text((250, 350), "EXP:", font=fnt(FONT_BOLD, 13), fill=(40, 40, 80))
    if tampered:
        d.text(
            (292 + 8, 350),
            printed_exp_date.strftime("%m/%d/%Y"),
            font=fnt(FONT_BOLD, 22),
            fill=(20, 20, 120),
        )
    else:
        d.text(
            (292, 350),
            printed_exp_date.strftime("%m/%d/%Y"),
            font=fnt(FONT_BOLD, 18),
            fill=exp_color,
        )
    if expired:
        d.text((435, 350), "** EXPIRED **", font=fnt(FONT_BOLD, 15), fill=(200, 0, 0))

    draw_barcode(d, 250, 400, w=350, h=44)
    footer_text = c["policy"]
    if tampered:
        footer_text = f"{c['policy']}  EXP: {exp_date.strftime('%m/%d/%Y')}"
    d.text((250, 453), footer_text, font=fnt(FONT_MONO, 11), fill=(55, 60, 100))
    _record_truth(
        doc_id or f"id_{c['patient_id']}",
        c,
        document_type="drivers_license",
        printed_name=shown_name,
        printed_expiry_date=printed_exp_date,
        expired=exp_date < c["treatment_date"],
        tampered=tampered,
    )
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(radius=random.uniform(1.0, 2.5)))
    return img


# ── 2. US Passport (biographical page) ───────────────
def _id_passport(c, expired=False, blur=False, tampered=False, display_name=None, doc_id=None):
    W, H = 1050, 740
    img = Image.new("RGB", (W, H), (248, 246, 240))
    d = ImageDraw.Draw(img)

    shown_name = display_name if display_name is not None else c["name"]
    city_state = f"{c.get('city', 'Chicago')}, {c.get('state', 'Illinois')}, USA"

    # Navy top band
    gradient_rect(d, 0, 0, W, 110, (20, 30, 90), (40, 55, 130))
    d.text(
        (W // 2, 25),
        "UNITED STATES OF AMERICA",
        font=fnt(FONT_BOLD, 26),
        fill=(255, 255, 255),
        anchor="mm",
    )
    d.text((W // 2, 62), "PASSPORT", font=fnt(FONT_BOLD, 34), fill=(255, 215, 0), anchor="mm")
    d.text(
        (W // 2, 92),
        "PASSEPORT  |  PASAPORTE",
        font=fnt(FONT_ITAL, 14),
        fill=(180, 200, 240),
        anchor="mm",
    )

    # Eagle seal (simplified)
    d.ellipse(
        [W // 2 - 52, 118, W // 2 + 52, 222], fill=(230, 225, 205), outline=(160, 145, 100), width=2
    )
    d.text((W // 2, 163), "USA", font=fnt(FONT_BOLD, 28), fill=(20, 30, 90), anchor="mm")
    d.text((W // 2, 192), "* * * * *", font=fnt(FONT_BOLD, 14), fill=(160, 130, 60), anchor="mm")

    # Gold accent line
    d.rectangle([0, 230, W, 234], fill=(200, 170, 60))

    # Photo box
    _photo_box(d, 40, 250, 190, 270, (80, 70, 140))
    d.text((88, 528), "APPLICANT", font=fnt(FONT_BOLD, 12), fill=(100, 90, 120))

    # Biographical data
    exp_date, exp_color = _exp_dates(c, expired)
    printed_exp_date = exp_date + timedelta(days=365) if tampered else exp_date
    ppt_num = f"P{rng.randint(100000000, 999999999)}"
    fields = [
        (
            "Surname / Nom",
            shown_name.split()[-2] if len(shown_name.split()) > 2 else shown_name.split()[0],
        ),
        (
            "Given Names / Prenoms",
            " ".join(shown_name.split()[:-2]) if len(shown_name.split()) > 2 else "",
        ),
        ("Nationality", "UNITED STATES OF AMERICA"),
        ("Date of Birth / Naissance", c["dob"]),
        ("Sex / Sexe", "M" if c["gender"] == "M" else "F"),
        ("Place of Birth", city_state),
        ("Date of Issue", c["treatment_date"].strftime("%m/%d/%Y")),
        ("Date of Expiration", printed_exp_date.strftime("%m/%d/%Y")),
        ("Passport No.", ppt_num),
    ]
    y = 250
    for label, val in fields:
        d.text((260, y), label, font=fnt(FONT_BOLD, 12), fill=(80, 70, 130))
        color = exp_color if "Expiration" in label and expired else (0, 0, 0)
        d.text((260, y + 16), val.upper(), font=fnt(FONT_MONO, 16), fill=color)
        d.line([(258, y + 38), (W - 35, y + 38)], fill=(200, 195, 180), width=1)
        y += 52

    if expired:
        d.text(
            (260, y + 5),
            "** DOCUMENT EXPIRED -- NOT VALID FOR TRAVEL **",
            font=fnt(FONT_BOLD, 16),
            fill=(200, 0, 0),
        )

    # MRZ zone
    gradient_rect(d, 0, H - 100, W, H, (30, 28, 55), (15, 14, 35))
    mrz_name = shown_name.replace(" ", "<").replace(".", "").upper()[:20].ljust(20, "<")
    mrz1 = f"P<USA{mrz_name}<<<<<<<<<<<<<<<<<<<<<<<<<"[:44]
    dob_digits = datetime.strptime(c["dob"], "%m/%d/%Y").strftime("%y%m%d")
    mrz2 = (f"{ppt_num}1USA{dob_digits}{c['gender']}{exp_date.strftime('%y%m%d')}{'<' * 17}")[:44]
    d.text((20, H - 90), mrz1, font=fnt(FONT_MONO, 15), fill=(180, 220, 180))
    d.text((20, H - 62), mrz2, font=fnt(FONT_MONO, 15), fill=(180, 220, 180))

    _record_truth(
        doc_id or f"id_{c['patient_id']}",
        c,
        document_type="passport",
        printed_name=shown_name,
        printed_expiry_date=printed_exp_date,
        expired=exp_date < c["treatment_date"],
        tampered=tampered,
    )

    if blur:
        img = img.filter(ImageFilter.GaussianBlur(radius=random.uniform(1.0, 2.5)))
    return img


# ── 3. Illinois State ID (Non-Driver) ────────────────
def _id_state_id(c, expired=False, blur=False, doc_id=None):
    W, H = 856, 540
    img = Image.new("RGB", (W, H), (245, 252, 248))
    d = ImageDraw.Draw(img)

    gradient_rect(d, 0, 0, W, 90, (18, 88, 48), (34, 130, 72))
    d.text((20, 10), "STATE OF ILLINOIS", font=fnt(FONT_BOLD, 14), fill=(190, 240, 210))
    d.text((20, 30), "IDENTIFICATION CARD", font=fnt(FONT_BOLD, 28), fill=(255, 255, 255))
    d.text((W - 360, 18), "NON-DRIVER", font=fnt(FONT_BOLD, 18), fill=(180, 255, 200))
    d.text((W - 290, 44), "ID CARD", font=fnt(FONT_BOLD, 18), fill=(180, 255, 200))
    d.rectangle([0, 90, W, 94], fill=(150, 220, 80))

    _photo_box(d, 40, 108, 192, 318, (30, 110, 60))
    d.text((88, 434), "PHOTO ID", font=fnt(FONT_BOLD, 13), fill=(40, 110, 60))

    id_num = f"I{rng.randint(1000, 9999)}-{rng.randint(1000, 9999)}"
    exp_date, exp_color = _exp_dates(c, expired)
    pairs = [
        ("ID NUMBER:", id_num),
        ("NAME:", c["name"].upper()),
        ("ADDRESS:", c["address"].split(",")[0].strip().upper()),
    ]
    y = 108
    for label, val in pairs:
        d.text((250, y), label, font=fnt(FONT_BOLD, 13), fill=(20, 80, 40))
        d.text(
            (250, y + 20),
            val,
            font=fnt(
                FONT_MONO if label == "ID NUMBER:" else FONT_BOLD if label == "NAME:" else FONT_REG,
                16 if label != "NAME:" else 21,
            ),
            fill=(0, 0, 0),
        )
        y += 65

    d.text((250, 305), "DOB:", font=fnt(FONT_BOLD, 13), fill=(20, 80, 40))
    d.text((295, 305), c["dob"], font=fnt(FONT_BOLD, 18), fill=(180, 0, 0))
    d.text((490, 305), "SEX:", font=fnt(FONT_BOLD, 13), fill=(20, 80, 40))
    d.text((530, 305), c["gender"], font=fnt(FONT_REG, 18), fill=(0, 0, 0))
    d.text((250, 350), "EXP:", font=fnt(FONT_BOLD, 13), fill=(20, 80, 40))
    d.text((292, 350), exp_date.strftime("%m/%d/%Y"), font=fnt(FONT_BOLD, 18), fill=exp_color)
    if expired:
        d.text((435, 350), "** EXPIRED **", font=fnt(FONT_BOLD, 15), fill=(200, 0, 0))

    draw_barcode(d, 250, 400, w=350, h=44, color=(18, 88, 48))
    d.text((250, 453), "NOT VALID FOR FEDERAL PURPOSES", font=fnt(FONT_REG, 12), fill=(60, 80, 60))

    _record_truth(
        doc_id or f"id_{c['patient_id']}",
        c,
        document_type="state_id",
        printed_name=c["name"],
        printed_expiry_date=exp_date,
        expired=exp_date < c["treatment_date"],
        tampered=False,
    )

    if blur:
        img = img.filter(ImageFilter.GaussianBlur(radius=random.uniform(1.0, 2.5)))
    return img


# ── 4. Health Insurance Member ID Card ───────────────
def _id_insurance_card(c, expired=False, blur=False, doc_id=None):
    W, H = 856, 540
    img = Image.new("RGB", (W, H), (250, 252, 255))
    d = ImageDraw.Draw(img)

    # Teal gradient header
    gradient_rect(d, 0, 0, W, 130, (0, 110, 140), (0, 160, 200))
    d.text(
        (28, 18), "MediShield Health Insurance Ltd.", font=fnt(FONT_BOLD, 22), fill=(255, 255, 255)
    )
    d.text((28, 52), "GOLD PLAN MEMBER ID CARD", font=fnt(FONT_BOLD, 28), fill=(255, 240, 150))
    d.text(
        (28, 92),
        "MED-GLD  |  Group: " + c["group_number"],
        font=fnt(FONT_REG, 16),
        fill=(200, 240, 255),
    )
    d.rectangle([0, 130, W, 134], fill=(255, 200, 0))

    exp_date, exp_color = _exp_dates(c, expired)

    # Card fields - left column
    left = [
        ("Member Name", c["name"]),
        ("Member ID", c["policy"]),
        ("Group Number", c["group_number"]),
        ("Effective Date", c["treatment_date"].strftime("%m/%d/%Y")),
        ("Expiration Date", exp_date.strftime("%m/%d/%Y")),
    ]
    y = 150
    for label, val in left:
        d.text((28, y), label + ":", font=fnt(FONT_BOLD, 14), fill=(0, 90, 120))
        color = exp_color if "Expiration" in label and expired else (0, 0, 0)
        d.text(
            (28, y + 20),
            val,
            font=fnt(
                FONT_MONO if "ID" in label or "Group" in label or "Date" in label else FONT_BOLD, 17
            ),
            fill=color,
        )
        d.line([(26, y + 42), (410, y + 42)], fill=(200, 215, 225), width=1)
        y += 55

    # Right column - copay summary
    d.rectangle([440, 145, W - 20, 465], fill=(0, 110, 140), outline=(0, 80, 110), width=0)
    draw_rounded_rect(d, 440, 145, W - 20, 465, radius=8, fill=(0, 110, 140))
    d.text((460, 158), "COST SHARING SUMMARY", font=fnt(FONT_BOLD, 15), fill=(255, 240, 150))
    copays = [
        ("PCP Visit", "$25 copay"),
        ("Specialist", "$60 copay"),
        ("Emergency Room", "$250 copay"),
        ("Urgent Care", "$50 copay"),
        ("Deductible (Ind.)", "$1,500"),
        ("Out-of-Pocket Max", "$7,500"),
        ("Rx Tier 1 (Generic)", "$15 / 30-day"),
    ]
    cy = 195
    for label, val in copays:
        d.text((460, cy), label + ":", font=fnt(FONT_REG, 13), fill=(200, 240, 255))
        d.text((680, cy), val, font=fnt(FONT_BOLD, 14), fill=(255, 255, 255))
        cy += 34

    if expired:
        d.rectangle([26, 390, 415, 455], fill=(255, 220, 220), outline=(200, 0, 0), width=2)
        d.text(
            (30, 400), "** CARD EXPIRED — NOT VALID **", font=fnt(FONT_BOLD, 18), fill=(200, 0, 0)
        )

    draw_barcode(d, 28, 475, w=380, h=40, color=(0, 90, 120))
    draw_qr_stub(d, W - 105, 475, size=60, color=(0, 90, 120))

    _record_truth(
        doc_id or f"id_{c['patient_id']}",
        c,
        document_type="insurance_card",
        printed_name=c["name"],
        printed_expiry_date=exp_date,
        expired=exp_date < c["treatment_date"],
        tampered=False,
    )

    if blur:
        img = img.filter(ImageFilter.GaussianBlur(radius=random.uniform(1.0, 2.5)))
    return img


# ── 5. Medicare / Medicaid Card ───────────────────────
def _id_medicare_card(c, expired=False, blur=False, doc_id=None):
    W, H = 856, 540
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)

    # Red top bar
    d.rectangle([0, 0, W, 15], fill=(200, 30, 30))
    # Blue bottom bar
    d.rectangle([0, H - 15, W, H], fill=(20, 70, 150))

    d.text((W // 2, 40), "Medicare", font=fnt(FONT_BOLD, 52), fill=(200, 30, 30), anchor="mm")
    d.text(
        (W // 2, 78), "HEALTH INSURANCE", font=fnt(FONT_BOLD, 18), fill=(20, 70, 150), anchor="mm"
    )
    d.line([(30, 95), (W - 30, 95)], fill=(200, 30, 30), width=3)
    d.line([(30, 100), (W - 30, 100)], fill=(20, 70, 150), width=3)

    mbi = f"{rng.randint(1, 9)}{rng.choice('ACDEFGHJKMNPQRTUVWXY')}{rng.choice('ACDEFGHJKMNPQRTUVWXY')}{rng.randint(1, 9)}-{rng.choice('ACDEFGHJKMNPQRTUVWXY')}{rng.choice('ACDEFGHJKMNPQRTUVWXY')}{rng.randint(1, 9)}-{rng.choice('ACDEFGHJKMNPQRTUVWXY')}{rng.choice('ACDEFGHJKMNPQRTUVWXY')}{rng.randint(10, 99)}"

    exp_date, exp_color = _exp_dates(c, expired)

    fields = [
        ("NAME", c["name"].upper()),
        ("MEDICARE CLAIM NUMBER", mbi),
        ("DATE OF BIRTH", c["dob"]),
        ("SEX", "MALE" if c["gender"] == "M" else "FEMALE"),
    ]
    y = 120
    for label, val in fields:
        d.text((30, y), label, font=fnt(FONT_BOLD, 14), fill=(60, 60, 80))
        d.text((30, y + 20), val, font=fnt(FONT_MONO, 20), fill=(0, 0, 0))
        y += 58

    # Part A / Part B
    d.text((30, y + 10), "IS ENTITLED TO", font=fnt(FONT_BOLD, 14), fill=(60, 60, 80))
    d.text((350, y + 10), "EFFECTIVE DATE", font=fnt(FONT_BOLD, 14), fill=(60, 60, 80))

    d.rectangle([28, y + 35, 340, y + 75], fill=(240, 245, 255), outline=(20, 70, 150), width=1)
    d.text((35, y + 45), "HOSPITAL (PART A)", font=fnt(FONT_BOLD, 16), fill=(20, 70, 150))
    d.text(
        (350, y + 45),
        c["treatment_date"].strftime("%m-%Y"),
        font=fnt(FONT_MONO, 18),
        fill=(0, 0, 0),
    )

    d.rectangle([28, y + 82, 340, y + 122], fill=(240, 255, 245), outline=(20, 70, 150), width=1)
    d.text((35, y + 92), "MEDICAL (PART B)", font=fnt(FONT_BOLD, 16), fill=(18, 88, 48))
    d.text(
        (350, y + 92),
        c["treatment_date"].strftime("%m-%Y"),
        font=fnt(FONT_MONO, 18),
        fill=(0, 0, 0),
    )

    if expired:
        d.rectangle(
            [28, y + 130, W - 28, y + 165], fill=(255, 220, 220), outline=(200, 0, 0), width=2
        )
        d.text(
            (35, y + 140),
            "** CARD EXPIRED — BENEFITS MAY NOT APPLY **",
            font=fnt(FONT_BOLD, 16),
            fill=(200, 0, 0),
        )

    d.text(
        (W // 2, H - 25),
        "DEPARTMENT OF HEALTH & HUMAN SERVICES  |  CMS",
        font=fnt(FONT_REG, 12),
        fill=(20, 70, 150),
        anchor="mm",
    )

    _record_truth(
        doc_id or f"id_{c['patient_id']}",
        c,
        document_type="medicare_card",
        printed_name=c["name"],
        printed_expiry_date=None,
        expired=exp_date < c["treatment_date"],
        tampered=False,
    )

    if blur:
        img = img.filter(ImageFilter.GaussianBlur(radius=random.uniform(1.0, 2.5)))
    return img


# ── Dispatcher ────────────────────────────────────────
_ID_GENERATORS = {
    "drivers_license": _id_drivers_license,
    "passport": _id_passport,
    "state_id": _id_state_id,
    "insurance_card": _id_insurance_card,
    "medicare_card": _id_medicare_card,
}


def generate_id_document(c, expired=False, blur=False, doc_id=None):
    doc_id = doc_id or f"id_{c['patient_id']}"
    generator = _ID_GENERATORS[c["id_type"]]
    if c["id_type"] in ("drivers_license", "passport"):
        return generator(
            c,
            expired=expired,
            blur=blur,
            tampered="tampered_id" in c["edge_flags"],
            display_name=c["id_display_name"],
            doc_id=doc_id,
        )
    return generator(c, expired=expired, blur=blur, doc_id=doc_id)


def generate_claim_form(c, missing_fields=False, th=None, doc_id=None):
    th = th or THEMES[0]
    W, H = 1700, 2400
    img = Image.new("RGB", (W, H), th["bg"])
    d = ImageDraw.Draw(img)

    RED = th["primary"]  # theme drives the form colour
    mft = c.get("missing_field_type")  # one of: "dob","npi","diag_code","auth_number", or None
    d.text((W - 680, 40), "HEALTH INSURANCE CLAIM FORM", font=fnt(FONT_BOLD, 24), fill=RED)
    d.text(
        (W - 680, 72), "CMS-1500 (02-12) / UB-04 Format", font=fnt(FONT_REG, 14), fill=(120, 0, 0)
    )
    d.text(
        (50, 52), "APPROVED BY NATIONAL UNIFORM CLAIM COMMITTEE", font=fnt(FONT_REG, 12), fill=RED
    )
    d.line([(50, 105), (W - 50, 105)], fill=RED, width=3)

    # ─── Block A: Patient & Insured (Fields 1–13) ────────
    MID = W // 2
    F9END = MID - 220  # divider between fields 9/10 columns inside left half

    d.rectangle([50, 120, W - 50, 875], outline=RED, width=2)
    d.line([(MID, 120), (MID, 875)], fill=RED, width=2)

    # Row 1  y=120–230  |  Fields 1 / 1a (left)  +  4 (right)
    d.line([(50, 230), (W - 50, 230)], fill=RED, width=1)
    d.text((60, 128), "1. INSURANCE TYPE:", font=fnt(FONT_BOLD, 13), fill=RED)
    options = ["MEDICARE", "MEDICAID", "TRICARE", "CHAMPVA", "GROUP HEALTH PLAN"]
    ox = 240
    for opt in options:
        is_selected = opt == "GROUP HEALTH PLAN"
        draw_checkbox(d, ox, 126, size=14, checked=is_selected, color=RED)
        d.text((ox + 18, 128), opt, font=fnt(FONT_BOLD if is_selected else FONT_REG, 13), fill=RED)
        ox += len(opt) * 9 + 36
    d.text((60, 160), "1a. INSURED'S I.D. NUMBER (Policy):", font=fnt(FONT_BOLD, 12), fill=RED)
    d.text((60, 180), c["policy"], font=fnt(FONT_MONO, 20), fill=(0, 0, 0))
    d.text((MID + 10, 128), "4. INSURED'S NAME", font=fnt(FONT_BOLD, 13), fill=RED)
    d.text((MID + 10, 152), "SAME AS PATIENT", font=fnt(FONT_MONO, 20), fill=(0, 0, 0))

    # Row 2  y=230–310  |  Fields 2 (left)  +  7 (right)
    d.line([(50, 310), (W - 50, 310)], fill=RED, width=1)
    d.text((60, 238), "2. PATIENT'S NAME (Last, First, MI)", font=fnt(FONT_BOLD, 13), fill=RED)
    d.text((60, 260), c["name"], font=fnt(FONT_MONO, 20), fill=(0, 0, 0))
    d.text((MID + 10, 238), "7. INSURED'S ADDRESS", font=fnt(FONT_BOLD, 13), fill=RED)
    d.text((MID + 10, 260), "SAME AS PATIENT", font=fnt(FONT_MONO, 18), fill=(0, 0, 0))

    # Row 3  y=310–385  |  Fields 3 + 6 (left split)  +  8 (right)
    d.line([(50, 385), (W - 50, 385)], fill=RED, width=1)
    d.line([(F9END, 310), (F9END, 385)], fill=RED, width=1)
    d.text((60, 317), "3. PATIENT'S BIRTH DATE", font=fnt(FONT_BOLD, 12), fill=RED)
    if mft == "dob":
        d.text((60, 337), "[DOB MISSING]", font=fnt(FONT_BOLD, 16), fill=(200, 40, 40))
    else:
        d.text((60, 337), c["dob"], font=fnt(FONT_MONO, 18), fill=(0, 0, 0))
    d.text((60, 363), f"SEX:  {c['gender']}", font=fnt(FONT_REG, 14), fill=(0, 0, 0))
    d.text((F9END + 6, 317), "6. PATIENT RELATIONSHIP", font=fnt(FONT_BOLD, 11), fill=RED)
    rx2 = F9END + 8
    for ri, rel in enumerate(["Self", "Spouse", "Child", "Other"]):
        draw_checkbox(d, rx2, 337, size=13, checked=(ri == 0), color=RED)
        d.text((rx2 + 17, 337), rel, font=fnt(FONT_REG, 13), fill=(0, 0, 0))
        rx2 += len(rel) * 8 + 34
    d.text((MID + 10, 317), "8. RESERVED FOR NUCC USE", font=fnt(FONT_BOLD, 12), fill=RED)

    # Row 4  y=385–460  |  Fields 5 (left)  +  11 (right)
    d.line([(50, 460), (W - 50, 460)], fill=RED, width=1)
    d.text((60, 393), "5. PATIENT'S ADDRESS", font=fnt(FONT_BOLD, 13), fill=RED)
    d.text((60, 413), c["address"], font=fnt(FONT_MONO, 16), fill=(0, 0, 0))
    d.text((MID + 10, 393), "11. INSURED'S GROUP NO.", font=fnt(FONT_BOLD, 13), fill=RED)
    d.text((MID + 10, 413), c["group_number"], font=fnt(FONT_MONO, 18), fill=(0, 0, 0))

    # Row 5  y=460–520  |  Fields 9 + 10a (left split)  +  11a (right)
    d.line([(50, 520), (W - 50, 520)], fill=RED, width=1)
    d.line([(F9END, 460), (F9END, 520)], fill=RED, width=1)
    d.text(
        (60, 467), "9. OTHER INSURED'S NAME (Last, First, MI)", font=fnt(FONT_BOLD, 11), fill=RED
    )
    d.text((60, 487), "________________________", font=fnt(FONT_REG, 13), fill=(80, 80, 80))
    d.text((F9END + 6, 467), "10a. EMPLOYMENT RELATED?", font=fnt(FONT_BOLD, 11), fill=RED)
    draw_checkbox(d, F9END + 6, 487, size=13, checked=False, color=RED)
    d.text((F9END + 23, 487), "YES", font=fnt(FONT_REG, 13), fill=(0, 0, 0))
    draw_checkbox(d, F9END + 72, 487, size=13, checked=False, color=RED)
    d.text((F9END + 89, 487), "NO", font=fnt(FONT_REG, 13), fill=(0, 0, 0))
    d.text((MID + 10, 467), "11a. INSURED'S DATE OF BIRTH / SEX", font=fnt(FONT_BOLD, 11), fill=RED)
    d.text((MID + 10, 487), f"{c['dob']}   SEX: _____", font=fnt(FONT_MONO, 14), fill=(0, 0, 0))

    # Row 6  y=520–580  |  Fields 9a + 10b (left split)  +  11b (right)
    d.line([(50, 580), (W - 50, 580)], fill=RED, width=1)
    d.line([(F9END, 520), (F9END, 580)], fill=RED, width=1)
    d.text(
        (60, 527), "9a. OTHER INSURED'S POLICY OR GROUP NUMBER", font=fnt(FONT_BOLD, 11), fill=RED
    )
    d.text((60, 547), "________________________", font=fnt(FONT_REG, 13), fill=(80, 80, 80))
    d.text((F9END + 6, 527), "10b. AUTO ACCIDENT?", font=fnt(FONT_BOLD, 11), fill=RED)
    draw_checkbox(d, F9END + 6, 547, size=13, checked=False, color=RED)
    d.text((F9END + 23, 547), "YES", font=fnt(FONT_REG, 13), fill=(0, 0, 0))
    draw_checkbox(d, F9END + 72, 547, size=13, checked=False, color=RED)
    d.text((F9END + 89, 547), "NO   PLACE:", font=fnt(FONT_REG, 13), fill=(0, 0, 0))
    d.text(
        (MID + 10, 527), "11b. EMPLOYER'S NAME OR SCHOOL NAME", font=fnt(FONT_BOLD, 11), fill=RED
    )
    d.text((MID + 10, 547), "________________________", font=fnt(FONT_REG, 13), fill=(80, 80, 80))

    # Row 7  y=580–640  |  Fields 9b + 10c (left split)  +  11c (right)
    d.line([(50, 640), (W - 50, 640)], fill=RED, width=1)
    d.line([(F9END, 580), (F9END, 640)], fill=RED, width=1)
    d.text((60, 587), "9b. OTHER INSURED'S DATE OF BIRTH / SEX", font=fnt(FONT_BOLD, 11), fill=RED)
    d.text((60, 607), "________________   SEX: ___", font=fnt(FONT_REG, 13), fill=(80, 80, 80))
    d.text((F9END + 6, 587), "10c. OTHER ACCIDENT?", font=fnt(FONT_BOLD, 11), fill=RED)
    draw_checkbox(d, F9END + 6, 607, size=13, checked=False, color=RED)
    d.text((F9END + 23, 607), "YES", font=fnt(FONT_REG, 13), fill=(0, 0, 0))
    draw_checkbox(d, F9END + 72, 607, size=13, checked=False, color=RED)
    d.text((F9END + 89, 607), "NO", font=fnt(FONT_REG, 13), fill=(0, 0, 0))
    d.text(
        (MID + 10, 587),
        "11c. INSURANCE PLAN NAME OR PROGRAM NAME",
        font=fnt(FONT_BOLD, 11),
        fill=RED,
    )
    d.text((MID + 10, 607), "________________________", font=fnt(FONT_REG, 13), fill=(80, 80, 80))

    # Row 8  y=640–700  |  Fields 9c + 10d (left split)  +  11d (right)
    d.line([(50, 700), (W - 50, 700)], fill=RED, width=1)
    d.line([(F9END, 640), (F9END, 700)], fill=RED, width=1)
    d.text((60, 647), "9c. EMPLOYER'S NAME OR SCHOOL NAME", font=fnt(FONT_BOLD, 11), fill=RED)
    d.text((60, 667), "________________________", font=fnt(FONT_REG, 13), fill=(80, 80, 80))
    d.text((F9END + 6, 647), "10d. CLAIM CODES (NUCC)", font=fnt(FONT_BOLD, 11), fill=RED)
    d.text((F9END + 6, 667), "________________________", font=fnt(FONT_REG, 13), fill=(80, 80, 80))
    d.text(
        (MID + 10, 647),
        "11d. IS THERE ANOTHER HEALTH BENEFIT PLAN?",
        font=fnt(FONT_BOLD, 11),
        fill=RED,
    )
    draw_checkbox(d, MID + 10, 667, size=13, checked=False, color=RED)
    d.text((MID + 27, 667), "YES", font=fnt(FONT_REG, 13), fill=(0, 0, 0))
    draw_checkbox(d, MID + 76, 667, size=13, checked=False, color=RED)
    d.text((MID + 93, 667), "NO", font=fnt(FONT_REG, 13), fill=(0, 0, 0))

    # Row 9  y=700–760  |  Field 9d (left)  +  (right blank continuation)
    d.line([(50, 760), (W - 50, 760)], fill=RED, width=1)
    d.text((60, 707), "9d. INSURANCE PLAN NAME OR PROGRAM NAME", font=fnt(FONT_BOLD, 11), fill=RED)
    d.text((60, 727), "________________________", font=fnt(FONT_REG, 13), fill=(80, 80, 80))

    # Row 10  y=760–875  |  Fields 12 (left)  +  13 (right)
    d.text(
        (60, 767),
        "12. PATIENT'S OR AUTHORIZED PERSON'S SIGNATURE",
        font=fnt(FONT_BOLD, 12),
        fill=RED,
    )
    d.text(
        (60, 787),
        "I authorize release of medical information necessary to process this claim.",
        font=fnt(FONT_REG, 11),
        fill=(60, 60, 60),
    )
    d.text(
        (60, 810),
        "SIGNED: ______________________________",
        font=fnt(FONT_REG, 13),
        fill=(80, 80, 80),
    )
    d.text(
        (60, 842),
        f"DATE: {c['treatment_date'].strftime('%m/%d/%Y')}",
        font=fnt(FONT_REG, 13),
        fill=(0, 0, 0),
    )
    d.text(
        (MID + 10, 767),
        "13. INSURED'S OR AUTHORIZED PERSON'S SIGNATURE",
        font=fnt(FONT_BOLD, 12),
        fill=RED,
    )
    d.text(
        (MID + 10, 787),
        "I authorize payment of medical benefits to the undersigned physician.",
        font=fnt(FONT_REG, 11),
        fill=(60, 60, 60),
    )
    d.text(
        (MID + 10, 810),
        "SIGNED: ______________________________",
        font=fnt(FONT_REG, 13),
        fill=(80, 80, 80),
    )

    # ─── Block B: Claim Number ─────────────────────────
    d.rectangle([50, 890, W - 50, 965], outline=RED, width=2)
    d.text((60, 900), "CLAIM NO.:", font=fnt(FONT_BOLD, 14), fill=RED)
    d.text((250, 900), c["claim_number"], font=fnt(FONT_MONO, 22), fill=(0, 0, 0))
    d.text(
        (W // 2 + 10, 900),
        f"DATE OF SERVICE: {c['treatment_date'].strftime('%m/%d/%Y')}",
        font=fnt(FONT_BOLD, 14),
        fill=RED,
    )

    # ─── Block B2: Condition / Referral Fields (14–20) ───
    col_w3 = (W - 100) // 3
    c14_x = 52
    c15_x = 52 + col_w3
    c16_x = 52 + col_w3 * 2
    c2col_r = 52 + (W - 104) * 2 // 3

    # Row 1 — fields 14, 15, 16
    r1_y = 980
    d.rectangle([50, r1_y, W - 50, r1_y + 90], outline=RED, width=2)
    d.line([(c15_x, r1_y), (c15_x, r1_y + 90)], fill=RED, width=1)
    d.line([(c16_x, r1_y), (c16_x, r1_y + 90)], fill=RED, width=1)
    d.text(
        (c14_x + 6, r1_y + 6),
        "14. DATE OF CURRENT ILLNESS / INJURY / PREGNANCY",
        font=fnt(FONT_BOLD, 11),
        fill=RED,
    )
    d.text((c15_x + 6, r1_y + 6), "15. OTHER DATE", font=fnt(FONT_BOLD, 11), fill=RED)
    d.text(
        (c16_x + 6, r1_y + 6),
        "16. DATES UNABLE TO WORK IN CURRENT OCCUPATION",
        font=fnt(FONT_BOLD, 11),
        fill=RED,
    )
    d.text(
        (c16_x + 6, r1_y + 30),
        "FROM: _______________  TO: _______________",
        font=fnt(FONT_REG, 12),
        fill=(80, 80, 80),
    )

    # Row 2 — fields 17 / 17a / 17b, 18
    r2_y = r1_y + 92
    d.rectangle([50, r2_y, W - 50, r2_y + 90], outline=RED, width=2)
    d.line([(c2col_r, r2_y), (c2col_r, r2_y + 90)], fill=RED, width=1)
    d.text(
        (52 + 6, r2_y + 6),
        "17. NAME OF REFERRING PROVIDER OR OTHER SOURCE",
        font=fnt(FONT_BOLD, 11),
        fill=RED,
    )
    d.text(
        (52 + 6, r2_y + 30),
        "17a. ____________________    17b. NPI: _______________",
        font=fnt(FONT_REG, 12),
        fill=(80, 80, 80),
    )
    d.text(
        (c2col_r + 6, r2_y + 6),
        "18. HOSPITALIZATION DATES RELATED TO CURRENT SERVICES",
        font=fnt(FONT_BOLD, 11),
        fill=RED,
    )
    d.text(
        (c2col_r + 6, r2_y + 30),
        "FROM: _______________  TO: _______________",
        font=fnt(FONT_REG, 12),
        fill=(80, 80, 80),
    )

    # Row 3 — fields 19, 20
    r3_y = r2_y + 92
    d.rectangle([50, r3_y, W - 50, r3_y + 90], outline=RED, width=2)
    d.line([(c2col_r, r3_y), (c2col_r, r3_y + 90)], fill=RED, width=1)
    d.text(
        (52 + 6, r3_y + 6),
        "19. ADDITIONAL CLAIM INFORMATION (Designated by NUCC)",
        font=fnt(FONT_BOLD, 11),
        fill=RED,
    )
    d.text((c2col_r + 6, r3_y + 6), "20. OUTSIDE LAB?", font=fnt(FONT_BOLD, 11), fill=RED)
    draw_checkbox(d, c2col_r + 6, r3_y + 28, size=14, checked=False, color=RED)
    d.text((c2col_r + 24, r3_y + 28), "YES", font=fnt(FONT_REG, 12), fill=(0, 0, 0))
    draw_checkbox(d, c2col_r + 80, r3_y + 28, size=14, checked=False, color=RED)
    d.text((c2col_r + 98, r3_y + 28), "NO", font=fnt(FONT_REG, 12), fill=(0, 0, 0))
    d.text(
        (c2col_r + 6, r3_y + 56),
        "$ CHARGES: _________________",
        font=fnt(FONT_REG, 12),
        fill=(80, 80, 80),
    )

    # ─── Block C: Diagnosis (field 21) ────────────────────
    c_y = r3_y + 106
    d.rectangle([50, c_y, W - 50, c_y + 125], outline=RED, width=2)
    d.text(
        (60, c_y + 10),
        "21. DIAGNOSIS / NATURE OF ILLNESS (ICD-10-CM)",
        font=fnt(FONT_BOLD, 13),
        fill=RED,
    )
    if mft == "diag_code":
        d.text(
            (60, c_y + 35),
            "A.  [DIAGNOSIS CODE MISSING]",
            font=fnt(FONT_MONO, 17),
            fill=(200, 40, 40),
        )
    else:
        d.text(
            (60, c_y + 35),
            f"A.  {c['icd_code']}  |  {c['icd_desc']}",
            font=fnt(FONT_MONO, 17),
            fill=(0, 0, 0),
        )

    # ─── Fields 22–23 ─────────────────────────────────────
    f22_y = c_y + 140
    d.rectangle([50, f22_y, W - 50, f22_y + 90], outline=RED, width=2)
    d.line([(W // 2, f22_y), (W // 2, f22_y + 90)], fill=RED, width=1)
    d.text((60, f22_y + 8), "22. RESUBMISSION CODE", font=fnt(FONT_BOLD, 11), fill=RED)
    d.text(
        (60, f22_y + 30),
        "CODE: _________  ORIGINAL REF. NO.: ___________________",
        font=fnt(FONT_REG, 12),
        fill=(80, 80, 80),
    )
    d.text(
        (W // 2 + 10, f22_y + 8),
        "23. PRIOR AUTHORIZATION NUMBER",
        font=fnt(FONT_BOLD, 11),
        fill=RED,
    )
    if mft == "auth_number":
        d.text(
            (W // 2 + 10, f22_y + 30),
            "[AUTH NUMBER MISSING]",
            font=fnt(FONT_BOLD, 12),
            fill=(200, 40, 40),
        )
    else:
        d.text(
            (W // 2 + 10, f22_y + 30),
            "________________________________",
            font=fnt(FONT_REG, 12),
            fill=(80, 80, 80),
        )

    # ─── Block D: Procedure Table ──────────────────────
    y = f22_y + 105
    d.rectangle([50, y, W - 50, y + 500], outline=RED, width=2)
    # column x positions: line#, date, place, cpt, description, charges, days, npi
    col_x = [60, 110, 300, 460, 610, 990, 1190, 1340]
    hdrs = [
        "#",
        "DATE OF SERVICE",
        "PLACE OF SERVICE",
        "CPT/HCPCS",
        "DESCRIPTION",
        "CHARGES ($)",
        "DAYS/UNITS",
        "RENDERING PROVIDER NPI",
    ]
    d.text((60, y + 8), "24. SERVICES / PROCEDURES", font=fnt(FONT_BOLD, 13), fill=RED)
    for hx, ht in zip(col_x, hdrs):
        d.text((hx, y + 30), ht, font=fnt(FONT_BOLD, 11), fill=RED)
    # divider under header
    d.line([(52, y + 55), (W - 52, y + 55)], fill=RED, width=1)

    total = 0.0
    dt_str = c["treatment_date"].strftime("%m/%d/%Y")
    row_y = y + 62
    for line_no, cpt in enumerate(c["cpt_list"], start=1):
        code, desc, price = cpt
        # alternating row background
        if line_no % 2 == 0:
            d.rectangle([52, row_y - 4, W - 52, row_y + 40], fill=th["light"])
        d.text((col_x[0], row_y), str(line_no), font=fnt(FONT_BOLD, 15), fill=RED)
        d.text((col_x[1], row_y), dt_str, font=fnt(FONT_MONO, 15), fill=(0, 0, 0))
        d.text((col_x[2], row_y), "11 (OFFICE)", font=fnt(FONT_MONO, 15), fill=(0, 0, 0))
        d.text((col_x[3], row_y), code, font=fnt(FONT_MONO, 15), fill=(0, 0, 0))
        d.text((col_x[4], row_y), desc[:36], font=fnt(FONT_MONO, 13), fill=(0, 0, 0))
        d.text((col_x[5], row_y), f"${price:,.2f}", font=fnt(FONT_MONO, 15), fill=(0, 0, 0))
        d.text((col_x[6], row_y), "1", font=fnt(FONT_MONO, 15), fill=(0, 0, 0))
        if mft != "npi" and not missing_fields:
            d.text((col_x[7], row_y), c["npi"], font=fnt(FONT_MONO, 15), fill=(0, 0, 0))
        elif mft == "npi":
            d.text((col_x[7], row_y), "[NPI MISSING]", font=fnt(FONT_MONO, 13), fill=(200, 40, 40))
        total += price
        row_y += 48

    if c["fraud_reason"] == "amount_under_10k":
        total = 9_875.00
        next_line = len(c["cpt_list"]) + 1
        d.text((col_x[0], row_y), str(next_line), font=fnt(FONT_BOLD, 15), fill=RED)
        d.text((col_x[1], row_y), dt_str, font=fnt(FONT_MONO, 15), fill=(0, 0, 0))
        d.text((col_x[3], row_y), "99999", font=fnt(FONT_MONO, 15), fill=(0, 0, 0))
        d.text(
            (col_x[4], row_y),
            "Additional Services (combined)",
            font=fnt(FONT_MONO, 13),
            fill=(0, 0, 0),
        )
        d.text((col_x[5], row_y), f"${total:,.2f}", font=fnt(FONT_MONO, 15), fill=(0, 0, 0))
        d.text((col_x[6], row_y), "1", font=fnt(FONT_MONO, 15), fill=(0, 0, 0))

    total_y = y + 510
    d.text((900, total_y + 10), "28. TOTAL CHARGE:", font=fnt(FONT_BOLD, 14), fill=RED)
    d.text((1150, total_y), f"${total:,.2f}", font=fnt(FONT_BOLD, 28), fill=(0, 0, 0))

    # ─── Block E: Signatures ──────────────────────────
    sig_y = total_y + 100
    d.line([(50, sig_y), (W - 50, sig_y)], fill=RED, width=1)
    d.text(
        (60, sig_y + 10),
        "31. SIGNATURE OF PHYSICIAN OR SUPPLIER",
        font=fnt(FONT_BOLD, 13),
        fill=RED,
    )
    if not missing_fields:
        d.text((60, sig_y + 40), c["doctor"], font=signature_fnt(28), fill=SIG_INK)
        d.text(
            (60, sig_y + 80),
            f"DATE: {c['treatment_date'].strftime('%m/%d/%Y')}",
            font=fnt(FONT_REG, 14),
            fill=(0, 0, 0),
        )
    else:
        d.text((60, sig_y + 40), "[SIGNATURE MISSING]", font=fnt(FONT_BOLD, 18), fill=(200, 50, 50))

    d.text(
        (W // 2 + 10, sig_y + 10),
        "33. BILLING PROVIDER INFO & PH #",
        font=fnt(FONT_BOLD, 13),
        fill=RED,
    )
    d.text((W // 2 + 10, sig_y + 40), c["hospital"], font=fnt(FONT_MONO, 18), fill=(0, 0, 0))
    if mft == "npi" or missing_fields:
        d.text(
            (W // 2 + 10, sig_y + 70), "NPI: [MISSING]", font=fnt(FONT_BOLD, 16), fill=(200, 50, 50)
        )
    else:
        d.text(
            (W // 2 + 10, sig_y + 70), f"NPI: {c['npi']}", font=fnt(FONT_MONO, 16), fill=(0, 0, 0)
        )

    # barcode at bottom
    draw_barcode(d, 60, H - 90, w=400, h=50)
    d.text((60, H - 35), c["claim_number"], font=fnt(FONT_MONO, 14), fill=(60, 60, 100))

    printed_cpt_codes = [item[0] for item in c["cpt_list"]]
    printed_icd10_codes = [] if mft == "diag_code" else [c["icd_code"]]
    if c["fraud_reason"] == "amount_under_10k":
        printed_cpt_codes.append("99999")
    _record_truth(
        doc_id or f"claim_{c['patient_id']}",
        c,
        claim_amount=Decimal(f"{total:.2f}"),
        cpt_codes=printed_cpt_codes,
        icd10_codes=printed_icd10_codes,
        icd10_code=None if mft == "diag_code" else c["icd_code"],
        provider_npi=None if mft == "npi" or missing_fields else c["npi"],
        service_date=c["treatment_date"],
        signature_present=not missing_fields,
        missing_field_type=c.get("missing_field_type"),
    )

    return img


# ──────────────────────────────────────────────
# UB-04 Institutional Claim Form (inpatient)
# ──────────────────────────────────────────────
def generate_ub04_form(c, th=None, doc_id=None):
    th = th or THEMES[0]
    P = th["primary"]
    W, H = 1700, 1600
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    BX = P  # box border colour matches theme

    admit_dt = c["treatment_date"]
    if c["fraud_reason"] == "readmission_30d":
        prior_end = admit_dt - timedelta(days=12)
        admit_dt = prior_end - timedelta(days=3)
    discharge_dt = admit_dt + timedelta(days=3)
    los = (discharge_dt - admit_dt).days

    # ── Form header ─────────────────────────────────────
    d.rectangle([50, 25, W - 50, 105], outline=BX, width=2)
    d.text((62, 34), "UB-04", font=fnt(FONT_BOLD, 32), fill=P)
    d.text((200, 40), "CMS-1450  UNIFORM INSTITUTIONAL CLAIM FORM", font=fnt(FONT_BOLD, 18), fill=P)
    d.text(
        (200, 68),
        "APPROVED OMB NO. 0938-0997  |  TYPE OF BILL: 0111 — Hospital Inpatient Admit-Through-Discharge",
        font=fnt(FONT_REG, 13),
        fill=(80, 80, 80),
    )

    # ── Box 1: Billing provider ──────────────────────────
    hosp = HOSPITAL_INFO.get(
        c["hospital"], {"addr": c["hospital"], "phone": "312-000-0000", "fax": "312-000-0001"}
    )
    d.rectangle([50, 105, 700, 230], outline=BX, width=1)
    d.text((56, 108), "1  BILLING PROVIDER NAME / ADDRESS / PHONE", font=fnt(FONT_BOLD, 10), fill=P)
    d.text((56, 128), c["hospital"], font=fnt(FONT_BOLD, 18), fill=(0, 0, 0))
    d.text((56, 155), hosp["addr"], font=fnt(FONT_REG, 14), fill=(0, 0, 0))
    d.text(
        (56, 178),
        f"Ph: {hosp['phone']}   Fax: {hosp['fax']}",
        font=fnt(FONT_REG, 13),
        fill=(60, 60, 80),
    )
    d.text((56, 200), f"NPI: {c['npi']}", font=fnt(FONT_MONO, 14), fill=(0, 0, 0))

    # ── Box 3b: Medical Record No / Box 4: Type of Bill / Box 6: Dates ─
    d.rectangle([700, 105, 950, 170], outline=BX, width=1)
    d.text((706, 108), "3b  MEDICAL RECORD NO.", font=fnt(FONT_BOLD, 10), fill=P)
    d.text((706, 130), f"MR-{c['patient_id']}", font=fnt(FONT_MONO, 16), fill=(0, 0, 0))

    d.rectangle([950, 105, 1150, 170], outline=BX, width=1)
    d.text((956, 108), "4  TYPE OF BILL", font=fnt(FONT_BOLD, 10), fill=P)
    d.text((956, 130), "0111", font=fnt(FONT_BOLD, 26), fill=(0, 0, 0))

    d.rectangle([1150, 105, W - 50, 170], outline=BX, width=1)
    d.text((1156, 108), "6  STATEMENT COVERS PERIOD", font=fnt(FONT_BOLD, 10), fill=P)
    d.text(
        (1156, 130),
        f"FROM  {admit_dt.strftime('%m/%d/%Y')}   THRU  {discharge_dt.strftime('%m/%d/%Y')}",
        font=fnt(FONT_MONO, 16),
        fill=(0, 0, 0),
    )

    d.rectangle([700, 170, 950, 230], outline=BX, width=1)
    d.text((706, 173), "5  FED. TAX NO.", font=fnt(FONT_BOLD, 10), fill=P)
    d.text((706, 193), "36-4721035", font=fnt(FONT_MONO, 16), fill=(0, 0, 0))

    d.rectangle([950, 170, W - 50, 230], outline=BX, width=1)
    d.text((956, 173), "17  PATIENT DISCHARGE STATUS", font=fnt(FONT_BOLD, 10), fill=P)
    d.text(
        (956, 193), "01 — Discharged to Home / Self-Care", font=fnt(FONT_MONO, 14), fill=(0, 0, 0)
    )

    # ── Patient info row (Boxes 8–14) ───────────────────
    patient_row_y = 230
    row_h = 90
    segments = [
        (50, 500, "8  PATIENT NAME (Last, First, MI)", c["name"]),
        (500, 900, "9  PATIENT ADDRESS", c["address"]),
        (900, 1080, "10  BIRTH DATE", c["dob"]),
        (1080, 1230, "11  SEX", "M" if "M" in c.get("gender", "M") else "F"),
        (1230, 1460, "12  ADMISSION DATE", admit_dt.strftime("%m/%d/%Y")),
        (1460, W - 50, "14  ADMIT TYPE", "1 — Emergency"),
    ]
    for x0, x1, label, val in segments:
        d.rectangle([x0, patient_row_y, x1, patient_row_y + row_h], outline=BX, width=1)
        d.text((x0 + 6, patient_row_y + 4), label, font=fnt(FONT_BOLD, 10), fill=P)
        d.text((x0 + 6, patient_row_y + 28), val, font=fnt(FONT_MONO, 17), fill=(0, 0, 0))

    # ── Condition codes row ──────────────────────────────
    cond_y = patient_row_y + row_h
    d.rectangle([50, cond_y, W - 50, cond_y + 55], outline=BX, width=1)
    d.text((56, cond_y + 4), "18–28  CONDITION CODES", font=fnt(FONT_BOLD, 10), fill=P)
    d.text(
        (56, cond_y + 24),
        "05  Lien                    39  Private Room Medically Necessary",
        font=fnt(FONT_MONO, 14),
        fill=(60, 60, 80),
    )

    # ── Revenue code table ───────────────────────────────
    tbl_y = cond_y + 55
    col_xs = [50, 130, 570, 780, 980, 1060, 1270, 1470, W - 50]
    col_hdrs = [
        "42\nREV CD",
        "43  DESCRIPTION",
        "44  HCPCS/RATE",
        "45  SERVICE DATE",
        "46\nUNITS",
        "47  TOTAL CHARGES",
        "48  NON-COV CHARGES",
        "49",
    ]

    hdr_h = 58
    row_h2 = 48
    table_content_h = (1 + len(c["cpt_list"])) * row_h2  # room & board + CPT rows
    d.rectangle([50, tbl_y, W - 50, tbl_y + hdr_h], fill=(220, 225, 245), outline=BX, width=1)
    for i, hdr in enumerate(col_hdrs):
        d.text((col_xs[i] + 4, tbl_y + 4), hdr, font=fnt(FONT_BOLD, 11), fill=P)
        d.line([(col_xs[i], tbl_y), (col_xs[i], tbl_y + hdr_h + table_content_h)], fill=BX, width=1)

    rev_map = {
        "99": ("0100", "Room & Board (all-inclusive)"),
        "33": ("0360", "Operating Room Services"),
        "27": ("0360", "Operating Room Services"),
        "29": ("0360", "Operating Room Services"),
        "43": ("0360", "Operating Room Services"),
        "47": ("0360", "Operating Room Services"),
        "59": ("0760", "Labor Room & Delivery"),
        "86": ("0300", "Laboratory"),
        "85": ("0300", "Laboratory"),
    }

    row_y = tbl_y + hdr_h
    total = 0.0

    # Room & Board line
    room_charge = los * 1250.0
    total += room_charge
    d.rectangle([50, row_y, W - 50, row_y + row_h2], outline=BX, width=1)
    vals = [
        "0120",
        f"Room & Board — Semi-Private  ({los} days)",
        "1250.00",
        admit_dt.strftime("%m/%d/%Y"),
        str(los),
        f"${room_charge:,.2f}",
        "$0.00",
        "",
    ]
    for i, v in enumerate(vals):
        d.text((col_xs[i] + 4, row_y + 14), v, font=fnt(FONT_MONO, 14), fill=(0, 0, 0))
    row_y += row_h2

    for cpt in c["cpt_list"]:
        pfx = cpt[0][:2]
        rev_code, rev_desc = rev_map.get(pfx, ("0490", "Other Therapeutic Services"))
        total += cpt[2]
        d.rectangle([50, row_y, W - 50, row_y + row_h2], outline=BX, width=1)
        vals = [
            rev_code,
            cpt[1][:55],
            cpt[0],
            c["treatment_date"].strftime("%m/%d/%Y"),
            "1",
            f"${cpt[2]:,.2f}",
            "$0.00",
            "",
        ]
        for i, v in enumerate(vals):
            d.text(
                (col_xs[i] + 4, row_y + 14),
                v,
                font=fnt(FONT_MONO, 13 if i == 1 else 14),
                fill=(0, 0, 0),
            )
        row_y += row_h2

    # Totals line
    row_y += 6
    d.line([(50, row_y), (W - 50, row_y)], fill=BX, width=2)
    d.text((col_xs[1] + 4, row_y + 10), "PAGE TOTALS", font=fnt(FONT_BOLD, 15), fill=P)
    d.text((col_xs[5] + 4, row_y + 10), f"${total:,.2f}", font=fnt(FONT_BOLD, 20), fill=(0, 0, 0))
    row_y += 55

    # ── Payer / insured ──────────────────────────────────
    pay_y = row_y
    d.rectangle([50, pay_y, W - 50, pay_y + 120], outline=BX, width=1)
    d.line([(700, pay_y), (700, pay_y + 120)], fill=BX, width=1)
    d.line([(1200, pay_y), (1200, pay_y + 120)], fill=BX, width=1)
    d.text((56, pay_y + 4), "50  PAYER NAME", font=fnt(FONT_BOLD, 10), fill=P)
    d.text((56, pay_y + 22), "MediShield Health Ins. Ltd.", font=fnt(FONT_BOLD, 16), fill=(0, 0, 0))
    d.text((56, pay_y + 50), "58  INSURED'S NAME", font=fnt(FONT_BOLD, 10), fill=P)
    d.text((56, pay_y + 66), c["name"], font=fnt(FONT_MONO, 16), fill=(0, 0, 0))
    d.text((56, pay_y + 90), "60  INSURED UNIQUE ID", font=fnt(FONT_BOLD, 10), fill=P)
    d.text((56, pay_y + 105), c["policy"], font=fnt(FONT_MONO, 15), fill=(0, 0, 0))
    d.text((706, pay_y + 4), "56  BILLING NPI", font=fnt(FONT_BOLD, 10), fill=P)
    d.text((706, pay_y + 22), c["npi"], font=fnt(FONT_MONO, 18), fill=(0, 0, 0))
    d.text((706, pay_y + 55), "57  GROUP NUMBER", font=fnt(FONT_BOLD, 10), fill=P)
    d.text((706, pay_y + 70), c["group_number"], font=fnt(FONT_MONO, 16), fill=(0, 0, 0))
    d.text((1206, pay_y + 4), "55  ESTIMATED AMT DUE", font=fnt(FONT_BOLD, 10), fill=P)
    d.text((1206, pay_y + 28), f"${total:,.2f}", font=fnt(FONT_BOLD, 28), fill=(10, 100, 10))
    row_y = pay_y + 135

    # ── Diagnoses ─────────────────────────────────────────
    dx_y = row_y
    d.rectangle([50, dx_y, W - 50, dx_y + 95], outline=BX, width=1)
    d.text((56, dx_y + 4), "67  PRINCIPAL DIAGNOSIS (ICD-10-CM)", font=fnt(FONT_BOLD, 10), fill=P)
    d.text(
        (56, dx_y + 22),
        f"{c['icd_code']}  —  {c['icd_desc']}",
        font=fnt(FONT_MONO, 17),
        fill=(0, 0, 0),
    )
    d.text((56, dx_y + 55), "69  ADMITTING DIAGNOSIS", font=fnt(FONT_BOLD, 10), fill=P)
    d.text(
        (56, dx_y + 72),
        f"{c['secondary_icd_code']}  —  {c['secondary_icd_desc']}",
        font=fnt(FONT_MONO, 15),
        fill=(60, 60, 80),
    )
    row_y = dx_y + 110

    # ── Attending physician ──────────────────────────────
    phy_y = row_y
    d.rectangle([50, phy_y, W - 50, phy_y + 100], outline=BX, width=1)
    d.line([(900, phy_y), (900, phy_y + 100)], fill=BX, width=1)
    d.text((56, phy_y + 4), "76  ATTENDING PHYSICIAN", font=fnt(FONT_BOLD, 10), fill=P)
    d.text((56, phy_y + 22), c["doctor"], font=fnt(FONT_BOLD, 18), fill=(0, 0, 0))
    d.text((56, phy_y + 52), f"NPI: {c['npi']}", font=fnt(FONT_MONO, 16), fill=(0, 0, 0))
    d.text((906, phy_y + 4), "74  PRINCIPAL PROCEDURE (CPT)", font=fnt(FONT_BOLD, 10), fill=P)
    d.text(
        (906, phy_y + 22),
        f"CPT {c['cpt_list'][0][0]}  —  {c['cpt_list'][0][1][:60]}",
        font=fnt(FONT_MONO, 15),
        fill=(0, 0, 0),
    )
    d.text(
        (906, phy_y + 52),
        f"Procedure Date: {c['treatment_date'].strftime('%m/%d/%Y')}",
        font=fnt(FONT_MONO, 14),
        fill=(60, 60, 80),
    )
    row_y = phy_y + 115

    # ── Physician signature ───────────────────────────────
    d.text((56, row_y + 8), c["doctor"], font=signature_fnt(32), fill=SIG_INK)
    d.line([(56, row_y + 52), (650, row_y + 52)], fill=(0, 0, 0), width=1)
    d.text(
        (56, row_y + 58), "Attending Physician Signature", font=fnt(FONT_REG, 12), fill=(80, 80, 80)
    )
    d.text(
        (56, row_y + 78),
        f"Date: {c['treatment_date'].strftime('%m/%d/%Y')}",
        font=fnt(FONT_REG, 13),
        fill=(0, 0, 0),
    )

    barcode_y = row_y + 120
    draw_barcode(d, 60, barcode_y, w=400, h=50)
    d.text(
        (60, barcode_y + 55),
        f"UB04-{c['claim_number']}",
        font=fnt(FONT_MONO, 14),
        fill=(60, 60, 100),
    )

    final_h = barcode_y + 85
    img = img.crop((0, 0, W, final_h))
    add_scan_effect(img)
    _record_truth(
        doc_id or f"claim_{c['patient_id']}",
        c,
        claim_amount=Decimal(f"{total:.2f}"),
        cpt_codes=[item[0] for item in c["cpt_list"]],
        icd10_codes=[c["icd_code"], c["secondary_icd_code"]],
        icd10_code=c["icd_code"],
        provider_npi=c["npi"],
        service_date=c["treatment_date"],
        signature_present=True,
        missing_field_type=c.get("missing_field_type"),
    )
    return img


def _wrap(text, max_chars):
    words = text.split()
    line, lines = "", []
    for w in words:
        if len(line) + len(w) + 1 > max_chars:
            lines.append(line)
            line = w
        else:
            line = (line + " " + w).strip()
    if line:
        lines.append(line)
    return lines


def generate_discharge_summary(c, th=None, doc_id=None):
    th = th or THEMES[0]
    P = th["primary"]
    W, H = 1700, 2200
    style = HOSPITAL_DOC_STYLES.get(c["hospital"], 0)
    hosp = HOSPITAL_INFO.get(
        c["hospital"], {"addr": c["hospital"], "phone": "312-000-0000", "fax": "312-000-0001"}
    )

    dt = c["treatment_date"]
    admit_dt = dt
    prior_discharge_days_before_admit = None
    if c["fraud_reason"] == "readmission_30d":
        prior_end_offset = rng.randint(5, 25)
        prior_discharge_days_before_admit = 5 + (prior_end_offset - 5) % 16
        prior_end = dt - timedelta(days=prior_end_offset)
        admit_dt = prior_end - timedelta(days=rng.randint(2, 5))
    discharge_dt = admit_dt + timedelta(days=rng.randint(2, 5))
    los = (discharge_dt - admit_dt).days
    if c["fraud_reason"] == "readmission_30d":
        c["prior_discharge_date"] = admit_dt - timedelta(days=prior_discharge_days_before_admit)

    course = (
        f"Patient {c['name']} was admitted on {admit_dt.strftime('%m/%d/%Y')} presenting "
        f"with symptoms consistent with {c['icd_desc'].lower()}. "
        "Complete diagnostic workup including laboratory evaluation and imaging studies was "
        "performed. The patient was commenced on appropriate pharmacological therapy and "
        "responded favorably. Vital signs remained stable throughout the hospitalization. "
        "No significant adverse events were recorded during the inpatient stay. "
        f"The patient was cleared for discharge on {discharge_dt.strftime('%m/%d/%Y')} "
        "with outpatient follow-up instructions."
    )

    # ── Style 0: Academic gradient (Northwestern, Rush) ──────────────────────
    if style == 0:
        img = Image.new("RGB", (W, H), th["bg"])
        d = ImageDraw.Draw(img)

        gradient_rect(d, 0, 0, W, 140, P, tuple(min(255, v + 30) for v in P))
        d.text(
            (W // 2, 40),
            c["hospital"].upper(),
            font=fnt(FONT_BOLD, 34),
            fill=(255, 255, 255),
            anchor="mm",
        )
        d.text(
            (W // 2, 90),
            "DISCHARGE SUMMARY",
            font=fnt(FONT_BOLD, 26),
            fill=(200, 220, 255),
            anchor="mm",
        )
        d.text(
            (W // 2, 120),
            "CONFIDENTIAL — FOR AUTHORIZED USE ONLY",
            font=fnt(FONT_ITAL, 14),
            fill=(180, 200, 240),
            anchor="mm",
        )
        d.line([(80, 160), (W - 80, 160)], fill=(0, 0, 0), width=2)

        for label, val, fx, fy in [
            ("Patient Name:", c["name"], 80, 190),
            ("DOB:", c["dob"], 800, 190),
            ("Patient ID:", c["patient_id"], 80, 230),
            ("Policy No.:", c["policy"], 800, 230),
            ("Attending Physician:", c["doctor"], 80, 270),
            ("NPI:", c["npi"], 800, 270),
        ]:
            d.text((fx, fy), label, font=fnt(FONT_BOLD, 16), fill=P)
            d.text((fx + len(label) * 10 + 5, fy), val, font=fnt(FONT_REG, 16), fill=(0, 0, 0))

        d.text((80, 315), "Admit Date:", font=fnt(FONT_BOLD, 16), fill=P)
        d.text((250, 315), admit_dt.strftime("%m/%d/%Y"), font=fnt(FONT_REG, 18), fill=(0, 0, 0))
        d.text((600, 315), "Discharge Date:", font=fnt(FONT_BOLD, 16), fill=P)
        d.text(
            (800, 315), discharge_dt.strftime("%m/%d/%Y"), font=fnt(FONT_BOLD, 18), fill=(0, 0, 0)
        )
        d.text((1100, 315), "LOS:", font=fnt(FONT_BOLD, 16), fill=P)
        d.text((1150, 315), f"{los} days", font=fnt(FONT_REG, 18), fill=(0, 0, 0))
        d.line([(80, 360), (W - 80, 360)], fill=(180, 180, 180), width=1)

        y = 390
        d.text((80, y), "FINAL DIAGNOSES:", font=fnt(FONT_BOLD, 22), fill=P)
        y += 42
        d.text(
            (100, y),
            f"Primary:    {c['icd_desc']}  (ICD-10: {c['icd_code']})",
            font=fnt(FONT_REG, 20),
            fill=(0, 0, 0),
        )
        y += 40
        d.text(
            (100, y),
            f"Secondary:  {c['secondary_icd_desc']}  (ICD-10: {c['secondary_icd_code']})",
            font=fnt(FONT_REG, 18),
            fill=(60, 60, 80),
        )
        y += 48

        d.text((80, y), "PROCEDURES PERFORMED:", font=fnt(FONT_BOLD, 22), fill=P)
        y += 42
        for cpt in c["cpt_list"]:
            d.text(
                (100, y),
                f"-- {cpt[1]}  (CPT: {cpt[0]})  |  Billed: ${cpt[2]:,.2f}",
                font=fnt(FONT_REG, 19),
                fill=(0, 0, 0),
            )
            y += 42

        y += 40
        d.text((80, y), "HOSPITAL COURSE:", font=fnt(FONT_BOLD, 22), fill=P)
        y += 42
        for ln in _wrap(course, 100):
            d.text((100, y), ln, font=fnt(FONT_REG, 19), fill=(0, 0, 0))
            y += 34

        y += 50
        d.text((80, y), "DISCHARGE DISPOSITION:", font=fnt(FONT_BOLD, 20), fill=P)
        d.text((450, y), "Home / Self-care", font=fnt(FONT_REG, 20), fill=(0, 0, 0))
        y += 60

        d.text((80, y), "DISCHARGE MEDICATIONS:", font=fnt(FONT_BOLD, 20), fill=P)
        y += 38
        for rx in c["rx_list"]:
            d.text(
                (100, y),
                f"—  {rx[0]} ({rx[1]})  •  Sig: {rx[2]}  •  Est. Cost: {rx[4]}",
                font=fnt(FONT_REG, 17),
                fill=(0, 0, 0),
            )
            y += 32

        y += 60
        d.text((82, y - 60), c["doctor"], font=signature_fnt(44), fill=SIG_INK)
        d.line([(80, y), (560, y)], fill=(0, 0, 0), width=1)
        d.text(
            (82, y + 10), "Attending Physician Signature", font=fnt(FONT_REG, 14), fill=(60, 60, 60)
        )
        d.text(
            (82, y + 34),
            f"Date: {discharge_dt.strftime('%m/%d/%Y')}",
            font=fnt(FONT_REG, 14),
            fill=(0, 0, 0),
        )

    # ── Style 1: Letterhead with left sidebar (U Chicago, Loyola, UI Health) ─
    elif style == 1:
        img = Image.new("RGB", (W, H), (255, 255, 255))
        d = ImageDraw.Draw(img)

        # Left colour bar
        d.rectangle([0, 0, 25, H], fill=P)
        # Hospital letterhead
        d.text((55, 36), c["hospital"], font=fnt(FONT_BOLD, 30), fill=P)
        d.text((55, 78), hosp["addr"], font=fnt(FONT_REG, 14), fill=(90, 90, 90))
        d.text(
            (55, 100),
            f"Tel: {hosp['phone']}  |  Fax: {hosp['fax']}",
            font=fnt(FONT_REG, 13),
            fill=(110, 110, 110),
        )
        # Document title badge (top-right)
        d.rectangle([W - 390, 28, W - 40, 125], fill=P)
        d.text(
            (W - 215, 60),
            "DISCHARGE SUMMARY",
            font=fnt(FONT_BOLD, 20),
            fill=(255, 255, 255),
            anchor="mm",
        )
        d.text(
            (W - 215, 92),
            "CONFIDENTIAL MEDICAL RECORD",
            font=fnt(FONT_REG, 12),
            fill=(200, 220, 255),
            anchor="mm",
        )
        d.text(
            (W - 215, 112),
            discharge_dt.strftime("%B %d, %Y"),
            font=fnt(FONT_REG, 13),
            fill=(180, 210, 255),
            anchor="mm",
        )
        # Dividers
        d.line([(38, 138), (W - 38, 138)], fill=P, width=3)
        d.line([(38, 143), (W - 38, 143)], fill=(210, 210, 210), width=1)

        # Patient info 2-column bordered table
        tbl_x, tbl_y, tbl_h = 40, 160, 188
        mid = W // 2
        d.rectangle([tbl_x, tbl_y, W - 40, tbl_y + tbl_h], outline=(180, 180, 180), width=1)
        d.line([(mid, tbl_y), (mid, tbl_y + tbl_h)], fill=(180, 180, 180), width=1)
        for ry in [tbl_y + 47, tbl_y + 94, tbl_y + 141]:
            d.line([(tbl_x, ry), (W - 40, ry)], fill=(205, 205, 205), width=1)

        left_cells = [
            ("Patient Name", c["name"]),
            ("Date of Birth", c["dob"]),
            ("Patient ID", c["patient_id"]),
            ("Attending Physician", c["doctor"]),
        ]
        right_cells = [
            ("Admission Date", admit_dt.strftime("%m/%d/%Y")),
            ("Discharge Date", discharge_dt.strftime("%m/%d/%Y")),
            ("Length of Stay", f"{los} days"),
            ("Policy Number", c["policy"]),
        ]
        for i, (lbl, val) in enumerate(left_cells):
            cy = tbl_y + i * 47 + 6
            d.text((tbl_x + 10, cy), lbl, font=fnt(FONT_BOLD, 12), fill=P)
            d.text((tbl_x + 10, cy + 20), val, font=fnt(FONT_REG, 15), fill=(0, 0, 0))
        for i, (lbl, val) in enumerate(right_cells):
            cy = tbl_y + i * 47 + 6
            d.text((mid + 10, cy), lbl, font=fnt(FONT_BOLD, 12), fill=P)
            d.text((mid + 10, cy + 20), val, font=fnt(FONT_REG, 15), fill=(0, 0, 0))

        y = tbl_y + tbl_h + 32

        def sec1(label, yy):
            lp = tuple(min(255, v + 175) for v in P)
            d.rectangle([40, yy, W - 40, yy + 36], fill=lp)
            d.text((55, yy + 8), label, font=fnt(FONT_BOLD, 17), fill=P)
            return yy + 46

        y = sec1("FINAL DIAGNOSES", y)
        d.text((60, y), "Primary Diagnosis:", font=fnt(FONT_BOLD, 15), fill=(40, 40, 40))
        y += 25
        d.text(
            (80, y),
            f"{c['icd_desc']}  (ICD-10: {c['icd_code']})",
            font=fnt(FONT_REG, 16),
            fill=(0, 0, 0),
        )
        y += 32
        d.text((60, y), "Secondary Diagnosis:", font=fnt(FONT_BOLD, 15), fill=(40, 40, 40))
        y += 25
        d.text(
            (80, y),
            f"{c['secondary_icd_desc']}  (ICD-10: {c['secondary_icd_code']})",
            font=fnt(FONT_REG, 15),
            fill=(55, 55, 75),
        )
        y += 40

        y = sec1("PROCEDURES PERFORMED", y)
        for cpt in c["cpt_list"]:
            d.text(
                (60, y),
                f"{cpt[1]}  (CPT {cpt[0]})  —  Billed: ${cpt[2]:,.2f}",
                font=fnt(FONT_REG, 16),
                fill=(0, 0, 0),
            )
            y += 34
        y += 10

        y = sec1("HOSPITAL COURSE", y)
        for ln in _wrap(course, 110):
            d.text((60, y), ln, font=fnt(FONT_REG, 16), fill=(0, 0, 0))
            y += 30
        y += 22

        y = sec1("DISCHARGE INFORMATION", y)
        d.text((60, y), "Disposition:", font=fnt(FONT_BOLD, 15), fill=(40, 40, 40))
        d.text((230, y), "Home / Self-care", font=fnt(FONT_REG, 15), fill=(0, 0, 0))
        y += 34
        d.text((60, y), "Medications at Discharge:", font=fnt(FONT_BOLD, 15), fill=(40, 40, 40))
        y += 30
        for rx in c["rx_list"]:
            d.text(
                (80, y),
                f"{rx[0]} ({rx[1]})  |  {rx[2]}  |  {rx[4]}",
                font=fnt(FONT_REG, 15),
                fill=(0, 0, 0),
            )
            y += 28
        y += 44

        d.text((60, y), c["doctor"], font=signature_fnt(40), fill=SIG_INK)
        y += 52
        d.line([(60, y), (500, y)], fill=(0, 0, 0), width=1)
        y += 8
        d.text((60, y), "Attending Physician Signature", font=fnt(FONT_REG, 13), fill=(70, 70, 70))
        y += 24
        d.text(
            (60, y),
            f"Date: {discharge_dt.strftime('%m/%d/%Y')}",
            font=fnt(FONT_REG, 13),
            fill=(0, 0, 0),
        )
        d.text((W - 400, y - 16), f"NPI: {c['npi']}", font=fnt(FONT_MONO, 13), fill=(130, 130, 130))

    # ── Style 2: Clinical numbered-section form (Advocate, OSF) ──────────────
    else:
        img = Image.new("RGB", (W, H), (240, 242, 246))
        d = ImageDraw.Draw(img)

        # White card
        d.rectangle(
            [28, 28, W - 28, H - 28], fill=(255, 255, 255), outline=(200, 202, 208), width=1
        )
        # Coloured header bar
        d.rectangle([28, 28, W - 28, 162], fill=P)
        d.text((58, 46), c["hospital"], font=fnt(FONT_BOLD, 28), fill=(255, 255, 255))
        d.text((58, 86), hosp["addr"], font=fnt(FONT_REG, 14), fill=(200, 220, 255))
        d.text(
            (58, 110),
            f"Tel: {hosp['phone']}  |  NPI: {c['npi']}",
            font=fnt(FONT_REG, 13),
            fill=(175, 200, 240),
        )
        # White badge top-right
        d.rectangle([W - 370, 44, W - 48, 148], fill=(255, 255, 255))
        d.text((W - 209, 70), "PATIENT DISCHARGE", font=fnt(FONT_BOLD, 17), fill=P, anchor="mm")
        d.text((W - 209, 100), "REPORT", font=fnt(FONT_BOLD, 24), fill=P, anchor="mm")
        d.text(
            (W - 209, 128),
            discharge_dt.strftime("%B %d, %Y"),
            font=fnt(FONT_REG, 13),
            fill=(110, 110, 130),
            anchor="mm",
        )

        # Alternating-row patient info table
        py = 178
        info_rows = [
            ("Patient Name", c["name"], "Date of Birth", c["dob"]),
            ("Patient ID", c["patient_id"], "Policy Number", c["policy"]),
            ("Attending Physician", c["doctor"], "Physician NPI", c["npi"]),
            (
                "Admission Date",
                admit_dt.strftime("%m/%d/%Y"),
                "Discharge Date",
                f"{discharge_dt.strftime('%m/%d/%Y')}  (LOS: {los} days)",
            ),
        ]
        mid = W // 2
        for i, (l1, v1, l2, v2) in enumerate(info_rows):
            bg = (248, 249, 252) if i % 2 == 0 else (255, 255, 255)
            d.rectangle([46, py, W - 46, py + 46], fill=bg)
            d.text((58, py + 5), l1, font=fnt(FONT_BOLD, 12), fill=(100, 100, 120))
            d.text((58, py + 23), v1, font=fnt(FONT_REG, 16), fill=(10, 10, 30))
            d.text((mid + 8, py + 5), l2, font=fnt(FONT_BOLD, 12), fill=(100, 100, 120))
            d.text((mid + 8, py + 23), v2, font=fnt(FONT_REG, 16), fill=(10, 10, 30))
            d.line([(46, py + 46), (W - 46, py + 46)], fill=(218, 220, 228), width=1)
            py += 46

        y = py + 28

        def sec2(num, label, yy):
            d.rectangle(
                [46, yy, W - 46, yy + 40], fill=(246, 247, 250), outline=(218, 220, 228), width=1
            )
            d.rectangle([46, yy, 84, yy + 40], fill=P)
            d.text((65, yy + 10), str(num), font=fnt(FONT_BOLD, 16), fill=(255, 255, 255))
            d.text((94, yy + 10), label, font=fnt(FONT_BOLD, 18), fill=(25, 25, 50))
            return yy + 54

        y = sec2(1, "FINAL DIAGNOSES", y)
        d.text((66, y), "Primary:", font=fnt(FONT_BOLD, 14), fill=(80, 80, 105))
        d.text(
            (186, y),
            f"{c['icd_desc']}  (ICD-10: {c['icd_code']})",
            font=fnt(FONT_REG, 16),
            fill=(10, 10, 30),
        )
        y += 32
        d.text((66, y), "Secondary:", font=fnt(FONT_BOLD, 14), fill=(80, 80, 105))
        d.text(
            (206, y),
            f"{c['secondary_icd_desc']}  (ICD-10: {c['secondary_icd_code']})",
            font=fnt(FONT_REG, 15),
            fill=(50, 50, 80),
        )
        y += 40

        y = sec2(2, "PROCEDURES PERFORMED", y)
        for cpt in c["cpt_list"]:
            d.rectangle(
                [66, y, W - 56, y + 38], fill=(252, 252, 255), outline=(225, 225, 238), width=1
            )
            d.text((78, y + 5), f"CPT {cpt[0]}", font=fnt(FONT_BOLD, 14), fill=P)
            d.text((200, y + 5), cpt[1], font=fnt(FONT_REG, 15), fill=(10, 10, 30))
            d.text(
                (W - 290, y + 5),
                f"Billed: ${cpt[2]:,.2f}",
                font=fnt(FONT_BOLD, 14),
                fill=(10, 110, 10),
            )
            y += 44
        y += 8

        y = sec2(3, "HOSPITAL COURSE", y)
        for ln in _wrap(course, 108):
            d.text((66, y), ln, font=fnt(FONT_REG, 16), fill=(18, 18, 28))
            y += 30
        y += 20

        y = sec2(4, "DISCHARGE INFORMATION", y)
        d.text((66, y), "Disposition:", font=fnt(FONT_BOLD, 14), fill=(80, 80, 105))
        d.text((230, y), "Home / Self-care", font=fnt(FONT_REG, 16), fill=(10, 10, 30))
        y += 34
        d.text((66, y), "Medications:", font=fnt(FONT_BOLD, 14), fill=(80, 80, 105))
        y += 28
        for rx in c["rx_list"]:
            d.text(
                (86, y),
                f"{rx[0]} ({rx[1]})  —  {rx[2]}  —  {rx[4]}",
                font=fnt(FONT_REG, 15),
                fill=(18, 18, 28),
            )
            y += 28
        y += 44

        d.text((68, y), c["doctor"], font=signature_fnt(40), fill=SIG_INK)
        y += 50
        d.line([(68, y), (520, y)], fill=(70, 70, 70), width=1)
        y += 8
        d.text((68, y), "Attending Physician Signature", font=fnt(FONT_REG, 13), fill=(80, 80, 80))
        y += 24
        d.text(
            (68, y),
            f"Signed: {discharge_dt.strftime('%m/%d/%Y')}",
            font=fnt(FONT_REG, 13),
            fill=(30, 30, 30),
        )

    _record_truth(
        doc_id or f"discharge_{c['patient_id']}",
        c,
        admit_date=admit_dt,
        discharge_date=discharge_dt,
        icd10_code=c["icd_code"],
        icd10_codes=[c["icd_code"], c["secondary_icd_code"]],
        cpt_codes=[item[0] for item in c["cpt_list"]],
        **(
            {"prior_discharge_date": c["prior_discharge_date"]}
            if c["fraud_reason"] == "readmission_30d"
            else {}
        ),
    )
    add_scan_effect(img)
    return img


def _clinic_stamp(d, cx, cy, hospital, color, rx=120, ry=52):
    """Draw an oval clinic stamp with hospital abbreviation."""
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], outline=color, width=2)
    d.ellipse([cx - rx + 4, cy - ry + 4, cx + rx - 4, cy + ry - 4], outline=color, width=1)
    abbrev = "".join(w[0] for w in hospital.split() if w[0].isupper())[:5]
    d.text((cx, cy - 12), abbrev, font=fnt(FONT_BOLD, 18), fill=color, anchor="mm")
    d.text((cx, cy + 12), "CLINIC", font=fnt(FONT_REG, 10), fill=color, anchor="mm")


def generate_prescription(c, th=None, missing_field=None, doc_id=None):
    th = th or THEMES[0]
    P = th["primary"]
    mf = missing_field
    W, H = 1200, 1650
    style = HOSPITAL_DOC_STYLES.get(c["hospital"], 0)
    hosp = HOSPITAL_INFO.get(
        c["hospital"],
        {"addr": "Chicago, IL 60601", "phone": "(312) 000-0000", "fax": "(312) 000-0001"},
    )

    parts = c["doctor"].replace(",", "").split()
    last_init = parts[1][0].upper() if len(parts) > 1 else "X"
    dea_digits = c["npi"].replace("NPI-", "")
    dea_num = f"B{last_init}{dea_digits[:7]}"
    il_license = f"IL{dea_digits[:5]}"
    is_controlled = any(cs in rx[0].lower() for rx in c["rx_list"] for cs in CONTROLLED_RX)

    rx_date = c["treatment_date"] + timedelta(days=c.get("los", 2))
    if c["fraud_reason"] == "date_conflict":
        rx_date = c["treatment_date"] + timedelta(days=rng.randint(46, 60))
        c["claim_service_date"] = c["treatment_date"]

    def _refills_row(d, y, x0=60):
        d.text((x0, y), "Refills:", font=fnt(FONT_BOLD, 15), fill=(0, 0, 0))
        rx2 = x0 + 110
        for lbl in ["0", "1", "2", "3", "PRN"]:
            draw_checkbox(d, rx2, y + 3, size=15, checked=False, color=(0, 0, 0))
            d.text((rx2 + 20, y + 1), lbl, font=fnt(FONT_REG, 15), fill=(0, 0, 0))
            rx2 += 68

    def _dispense_row(d, y, x0=60):
        draw_checkbox(d, x0, y + 2, size=15, checked=True, color=(0, 0, 0))
        d.text((x0 + 20, y), "Dispense as Written (DAW)", font=fnt(FONT_BOLD, 14), fill=(0, 0, 0))
        draw_checkbox(d, x0 + 290, y + 2, size=15, checked=False, color=(0, 0, 0))
        d.text((x0 + 310, y), "Brand Medically Necessary", font=fnt(FONT_REG, 14), fill=(0, 0, 0))
        draw_checkbox(d, x0 + 580, y + 2, size=15, checked=False, color=(0, 0, 0))
        d.text((x0 + 600, y), "May Substitute", font=fnt(FONT_REG, 14), fill=(0, 0, 0))

    def _controlled_box(d, y, x0=50):
        d.rectangle([x0, y, W - x0, y + 52], fill=(255, 238, 238), outline=(200, 40, 40), width=2)
        d.text(
            (x0 + 18, y + 8),
            "! SCHEDULE II/III CONTROLLED SUBSTANCE",
            font=fnt(FONT_BOLD, 14),
            fill=(180, 0, 0),
        )
        d.text(
            (x0 + 18, y + 30),
            "Illinois law: this prescription must be dispensed exactly as written.",
            font=fnt(FONT_REG, 12),
            fill=(140, 0, 0),
        )

    # ── Style 0: Standard letterhead (Northwestern, Rush) ────────────────────
    if style == 0:
        img = Image.new("RGB", (W, H), (255, 255, 255))
        d = ImageDraw.Draw(img)

        d.rectangle([0, 0, W, 6], fill=P)
        d.text((60, 18), c["hospital"], font=fnt(FONT_BOLD, 26), fill=P)
        d.text((60, 54), hosp["addr"], font=fnt(FONT_REG, 14), fill=(60, 60, 80))
        d.text(
            (60, 74),
            f"Phone: {hosp['phone']}   Fax: {hosp['fax']}",
            font=fnt(FONT_REG, 14),
            fill=(60, 60, 80),
        )
        d.text((640, 18), c["doctor"], font=fnt(FONT_BOLD, 18), fill=(0, 0, 0))
        d.text((640, 44), f"NPI:        {c['npi']}", font=fnt(FONT_MONO, 13), fill=(60, 60, 80))
        dea_str0 = "[MISSING]" if mf == "dea" else dea_num
        d.text(
            (640, 62),
            f"DEA:        {dea_str0}",
            font=fnt(FONT_MONO, 13),
            fill=((200, 40, 40) if mf == "dea" else (60, 60, 80)),
        )
        d.text((640, 80), f"IL License: {il_license}", font=fnt(FONT_MONO, 13), fill=(60, 60, 80))
        d.line([(50, 108), (W - 50, 108)], fill=P, width=3)
        d.line([(50, 112), (W - 50, 112)], fill=(220, 220, 220), width=1)

        d.rectangle([50, 122, W - 50, 272], outline=(180, 185, 205), width=1)
        d.text((68, 132), "Patient:", font=fnt(FONT_BOLD, 13), fill=(80, 80, 100))
        d.text((160, 130), c["name"], font=fnt(FONT_BOLD, 18), fill=(0, 0, 0))
        d.text((720, 132), "DOB:", font=fnt(FONT_BOLD, 13), fill=(80, 80, 100))
        d.text((764, 130), c["dob"], font=fnt(FONT_MONO, 16), fill=(0, 0, 0))
        d.text((980, 132), "Sex:", font=fnt(FONT_BOLD, 13), fill=(80, 80, 100))
        d.text((1018, 130), c["gender"], font=fnt(FONT_BOLD, 16), fill=(0, 0, 0))
        d.line([(50, 162), (W - 50, 162)], fill=(220, 220, 225), width=1)
        d.text((68, 170), "Address:", font=fnt(FONT_BOLD, 13), fill=(80, 80, 100))
        d.text((160, 168), c["address"], font=fnt(FONT_REG, 15), fill=(0, 0, 0))
        d.line([(50, 202), (W - 50, 202)], fill=(220, 220, 225), width=1)
        d.text((68, 210), "Policy ID:", font=fnt(FONT_BOLD, 13), fill=(80, 80, 100))
        d.text((170, 208), c["policy"], font=fnt(FONT_MONO, 15), fill=(40, 40, 80))
        d.text((720, 210), "Rx Date:", font=fnt(FONT_BOLD, 13), fill=(80, 80, 100))
        d.text((808, 208), rx_date.strftime("%m/%d/%Y"), font=fnt(FONT_BOLD, 16), fill=(0, 0, 0))
        if c["fraud_reason"] == "date_conflict":
            d.text(
                (980, 208), "** EXCEEDS CLAIM DATE **", font=fnt(FONT_BOLD, 12), fill=(200, 0, 0)
            )
        d.line([(50, 242), (W - 50, 242)], fill=(220, 220, 225), width=1)
        d.text((68, 250), "Diagnosis:", font=fnt(FONT_BOLD, 13), fill=(80, 80, 100))
        d.text((170, 248), f"{c['icd_code']} — {c['icd_desc']}", font=fnt(FONT_REG, 15), fill=P)

        d.line([(50, 284), (W - 50, 284)], fill=(200, 200, 200), width=1)
        y = 295
        for idx, rx in enumerate(c["rx_list"], start=1):
            cs_flag = any(cs in rx[0].lower() for cs in CONTROLLED_RX)
            d.text((60, y), "Rx", font=fnt(FONT_ITAL, 18), fill=P)
            d.text((60, y + 22), f"{idx}.", font=fnt(FONT_BOLD, 13), fill=P)
            drug_label = "[DRUG NAME MISSING]" if mf == "drug_name" else f"{rx[0]}  ({rx[1]})"
            d.text(
                (100, y),
                drug_label,
                font=fnt(FONT_BOLD, 22),
                fill=((200, 40, 40) if mf == "drug_name" else (10, 20, 100)),
            )
            if cs_flag and mf != "drug_name":
                d.text(
                    (100 + int(fnt(FONT_BOLD, 22).getlength(drug_label)) + 14, y + 4),
                    "[C-II/III CONTROLLED]",
                    font=fnt(FONT_BOLD, 13),
                    fill=(180, 0, 0),
                )
            sig_text = "[ILLEGIBLE]" if mf == "dosage" else rx[2]
            d.text(
                (100, y + 30),
                f"Sig:  {sig_text}",
                font=fnt(FONT_ITAL, 16),
                fill=((200, 40, 40) if mf == "dosage" else (40, 40, 60)),
            )
            qty = rng.randint(20, 90)
            d.text(
                (100, y + 58),
                f"Qty: #{qty}     Days Supply: {rx[3]}",
                font=fnt(FONT_REG, 14),
                fill=(60, 60, 80),
            )
            d.text(
                (100, y + 78), f"Est. Cost: {rx[4]}", font=fnt(FONT_REG, 13), fill=(110, 110, 110)
            )
            d.line([(50, y + 100), (W - 50, y + 100)], fill=(225, 225, 230), width=1)
            y += 110

        y += 12
        if mf != "refills":
            _refills_row(d, y)
        y += 44
        _dispense_row(d, y)
        if is_controlled:
            y += 40
            _controlled_box(d, y)
            y += 52
        y += 70
        d.line([(50, y), (W - 50, y)], fill=(180, 185, 205), width=1)
        d.text((62, y + 10), c["doctor"], font=signature_fnt(44), fill=SIG_INK)
        d.line([(60, y + 68), (500, y + 68)], fill=(0, 0, 0), width=1)
        d.text((62, y + 74), "Prescriber's Signature", font=fnt(FONT_REG, 13), fill=(80, 80, 80))
        d.text(
            (62, y + 94),
            f"Date: {rx_date.strftime('%m/%d/%Y')}",
            font=fnt(FONT_REG, 13),
            fill=(0, 0, 0),
        )
        cbox_y = y + 68
        d.rectangle([540, cbox_y, W - 55, cbox_y + 115], outline=(190, 195, 215), width=1)
        dea_str0b = "[MISSING]" if mf == "dea" else dea_num
        d.text(
            (556, cbox_y + 10),
            f"DEA #:        {dea_str0b}",
            font=fnt(FONT_MONO, 13),
            fill=((200, 40, 40) if mf == "dea" else (0, 0, 0)),
        )
        d.text(
            (556, cbox_y + 30), f"NPI #:        {c['npi']}", font=fnt(FONT_MONO, 13), fill=(0, 0, 0)
        )
        d.text(
            (556, cbox_y + 50),
            f"IL License:   {il_license}",
            font=fnt(FONT_MONO, 13),
            fill=(0, 0, 0),
        )
        d.text(
            (556, cbox_y + 70),
            f"Phone:        {hosp['phone']}",
            font=fnt(FONT_MONO, 13),
            fill=(0, 0, 0),
        )
        d.text(
            (556, cbox_y + 90),
            f"Fax:          {hosp['fax']}",
            font=fnt(FONT_MONO, 13),
            fill=(0, 0, 0),
        )
        _clinic_stamp(d, W - 130, cbox_y + 56, c["hospital"], P)

    # ── Style 1: Prescription pad (U Chicago, Loyola, UI Health) ─────────────
    elif style == 1:
        img = Image.new("RGB", (W, H), (252, 252, 255))
        d = ImageDraw.Draw(img)

        # Large faded "Rx" watermark
        d.text(
            (W // 2, H // 2 - 80), "Rx", font=fnt(FONT_BOLD, 380), fill=(235, 237, 248), anchor="mm"
        )

        # Header band
        d.rectangle([0, 0, W, 110], fill=P)
        d.text((30, 18), c["hospital"], font=fnt(FONT_BOLD, 24), fill=(255, 255, 255))
        d.text((30, 52), hosp["addr"], font=fnt(FONT_REG, 13), fill=(200, 215, 255))
        d.text((30, 72), f"Tel: {hosp['phone']}", font=fnt(FONT_REG, 13), fill=(180, 200, 245))
        # Doctor credential box top-right
        d.rectangle([W - 340, 10, W - 10, 100], fill=(255, 255, 255))
        d.text((W - 326, 16), c["doctor"], font=fnt(FONT_BOLD, 14), fill=P)
        d.text((W - 326, 38), f"NPI: {c['npi']}", font=fnt(FONT_MONO, 11), fill=(60, 60, 80))
        dea_str1 = "[MISSING]" if mf == "dea" else dea_num
        d.text(
            (W - 326, 56),
            f"DEA: {dea_str1}",
            font=fnt(FONT_MONO, 11),
            fill=((200, 40, 40) if mf == "dea" else (60, 60, 80)),
        )
        d.text((W - 326, 74), f"Lic: {il_license}", font=fnt(FONT_MONO, 11), fill=(60, 60, 80))

        # Patient info — two-column compact
        y = 128
        d.rectangle(
            [20, y, W - 20, y + 108], outline=(200, 202, 218), width=1, fill=(255, 255, 255)
        )
        d.line([(20, y + 54), (W - 20, y + 54)], fill=(210, 212, 228), width=1)
        mid = W // 2
        d.line([(mid, y), (mid, y + 108)], fill=(210, 212, 228), width=1)
        for lbl, val, cx, cy in [
            ("Patient", c["name"], 26, y + 6),
            ("Address", c["address"], 26, y + 62),
            ("DOB", c["dob"], mid + 8, y + 6),
            ("Policy ID", c["policy"], mid + 8, y + 62),
        ]:
            d.text((cx, cy), lbl, font=fnt(FONT_BOLD, 11), fill=P)
            d.text((cx, cy + 18), val, font=fnt(FONT_REG, 15), fill=(0, 0, 0))
        d.text((mid + 8, y + 62), "Policy ID:", font=fnt(FONT_BOLD, 11), fill=P)
        d.text((mid + 8, y + 80), c["policy"], font=fnt(FONT_MONO, 14), fill=(30, 30, 80))
        # Rx date + diagnosis below table
        y += 120
        d.text(
            (26, y),
            f"Rx Date: {rx_date.strftime('%m/%d/%Y')}",
            font=fnt(FONT_BOLD, 14),
            fill=(0, 0, 0),
        )
        if c["fraud_reason"] == "date_conflict":
            d.text((260, y), "** EXCEEDS CLAIM DATE **", font=fnt(FONT_BOLD, 12), fill=(200, 0, 0))
        d.text((700, y), f"Dx: {c['icd_code']} — {c['icd_desc']}", font=fnt(FONT_REG, 13), fill=P)
        y += 32

        d.line([(20, y), (W - 20, y)], fill=P, width=2)
        y += 14

        # Medications — each in a bordered card
        for idx, rx in enumerate(c["rx_list"], start=1):
            cs_flag = any(cs in rx[0].lower() for cs in CONTROLLED_RX)
            card_h = 110
            d.rectangle(
                [20, y, W - 20, y + card_h], fill=(255, 255, 255), outline=(210, 212, 225), width=1
            )
            d.rectangle([20, y, 28, y + card_h], fill=P)
            d.ellipse([34, y + 10, 58, y + 34], fill=P)
            d.text(
                (46, y + 22), str(idx), font=fnt(FONT_BOLD, 14), fill=(255, 255, 255), anchor="mm"
            )
            drug_label = "[DRUG NAME MISSING]" if mf == "drug_name" else f"{rx[0]}  ({rx[1]})"
            d.text(
                (66, y + 8),
                drug_label,
                font=fnt(FONT_BOLD, 20),
                fill=((200, 40, 40) if mf == "drug_name" else (10, 20, 100)),
            )
            if cs_flag and mf != "drug_name":
                d.text(
                    (66 + int(fnt(FONT_BOLD, 20).getlength(drug_label)) + 12, y + 11),
                    "CONTROLLED",
                    font=fnt(FONT_BOLD, 12),
                    fill=(180, 0, 0),
                )
            sig_text = "[ILLEGIBLE]" if mf == "dosage" else rx[2]
            d.text(
                (66, y + 36),
                f"Sig: {sig_text}",
                font=fnt(FONT_ITAL, 15),
                fill=((200, 40, 40) if mf == "dosage" else (40, 40, 60)),
            )
            qty = rng.randint(20, 90)
            d.text(
                (66, y + 62),
                f"Qty: #{qty}   Days Supply: {rx[3]}",
                font=fnt(FONT_REG, 13),
                fill=(60, 60, 80),
            )
            d.text(
                (66, y + 82), f"Est. Cost: {rx[4]}", font=fnt(FONT_REG, 13), fill=(100, 100, 100)
            )
            y += card_h + 10

        y += 10
        if mf != "refills":
            _refills_row(d, y, x0=26)
        y += 40
        _dispense_row(d, y, x0=26)
        if is_controlled:
            y += 36
            _controlled_box(d, y, x0=20)
            y += 52
        y += 54
        d.line([(20, y), (W - 20, y)], fill=(190, 192, 210), width=1)
        y += 10
        d.text((26, y + 6), c["doctor"], font=signature_fnt(42), fill=SIG_INK)
        y += 56
        d.line([(26, y), (460, y)], fill=(0, 0, 0), width=1)
        y += 6
        d.text((26, y + 2), "Prescriber's Signature", font=fnt(FONT_REG, 12), fill=(80, 80, 80))
        d.text(
            (26, y + 20),
            f"Date: {rx_date.strftime('%m/%d/%Y')}",
            font=fnt(FONT_REG, 12),
            fill=(0, 0, 0),
        )
        dea_str1b = "[MISSING]" if mf == "dea" else dea_num
        d.text(
            (W - 340, y - 48),
            f"DEA: {dea_str1b}",
            font=fnt(FONT_MONO, 12),
            fill=((200, 40, 40) if mf == "dea" else (80, 80, 100)),
        )
        d.text((W - 340, y - 28), f"NPI: {c['npi']}", font=fnt(FONT_MONO, 12), fill=(80, 80, 100))
        d.text((W - 340, y - 8), f"Lic: {il_license}", font=fnt(FONT_MONO, 12), fill=(80, 80, 100))
        _clinic_stamp(d, W - 130, y + 50, c["hospital"], P)

    # ── Style 2: Clinical table form (Advocate, OSF) ─────────────────────────
    else:
        img = Image.new("RGB", (W, H), (238, 240, 245))
        d = ImageDraw.Draw(img)

        d.rectangle([0, 0, W, H], fill=(238, 240, 245))
        d.rectangle(
            [18, 18, W - 18, H - 18], fill=(255, 255, 255), outline=(205, 207, 215), width=1
        )
        # Header
        d.rectangle([18, 18, W - 18, 130], fill=P)
        d.text((38, 30), c["hospital"], font=fnt(FONT_BOLD, 24), fill=(255, 255, 255))
        d.text((38, 66), hosp["addr"], font=fnt(FONT_REG, 13), fill=(200, 215, 255))
        d.text((38, 88), f"Tel: {hosp['phone']}", font=fnt(FONT_REG, 13), fill=(180, 200, 245))
        # "PRESCRIPTION" badge top-right
        d.rectangle([W - 290, 28, W - 28, 120], fill=(255, 255, 255))
        d.text((W - 159, 52), "PRESCRIPTION", font=fnt(FONT_BOLD, 17), fill=P, anchor="mm")
        d.text(
            (W - 159, 78),
            rx_date.strftime("%m/%d/%Y"),
            font=fnt(FONT_MONO, 14),
            fill=(40, 40, 60),
            anchor="mm",
        )
        d.text((W - 159, 100), c["doctor"], font=fnt(FONT_REG, 11), fill=(90, 90, 110), anchor="mm")

        # Patient info alternating rows
        py = 148
        for i, (l1, v1, l2, v2) in enumerate(
            [
                ("Patient Name", c["name"], "Date of Birth", c["dob"]),
                ("Address", c["address"], "Sex", c["gender"]),
                ("Policy ID", c["policy"], "Rx Date", rx_date.strftime("%m/%d/%Y")),
                ("Diagnosis", f"{c['icd_code']}", "Description", c["icd_desc"]),
            ]
        ):
            bg = (248, 249, 252) if i % 2 == 0 else (255, 255, 255)
            d.rectangle([28, py, W - 28, py + 42], fill=bg)
            d.text((38, py + 4), l1, font=fnt(FONT_BOLD, 11), fill=(100, 100, 120))
            d.text((38, py + 20), v1, font=fnt(FONT_REG, 15), fill=(10, 10, 30))
            d.text((W // 2 + 10, py + 4), l2, font=fnt(FONT_BOLD, 11), fill=(100, 100, 120))
            d.text((W // 2 + 10, py + 20), v2, font=fnt(FONT_REG, 15), fill=(10, 10, 30))
            d.line([(28, py + 42), (W - 28, py + 42)], fill=(215, 217, 225), width=1)
            py += 42
        if c["fraud_reason"] == "date_conflict":
            d.text(
                (W // 2 + 10, py - 22),
                "** EXCEEDS CLAIM DATE **",
                font=fnt(FONT_BOLD, 11),
                fill=(200, 0, 0),
            )

        y = py + 16
        # Medications table header
        d.rectangle([28, y, W - 28, y + 32], fill=P)
        d.text((38, y + 7), "MEDICATIONS PRESCRIBED", font=fnt(FONT_BOLD, 14), fill=(255, 255, 255))
        d.text((W - 200, y + 7), f"NPI: {c['npi']}", font=fnt(FONT_MONO, 11), fill=(200, 215, 255))
        y += 38

        _RX_LTRS = ["A", "B", "C", "D", "E"]
        for idx, rx in enumerate(c["rx_list"], start=1):
            cs_flag = any(cs in rx[0].lower() for cs in CONTROLLED_RX)
            lp = tuple(min(255, v + 195) for v in P)
            drug_label = "[DRUG NAME MISSING]" if mf == "drug_name" else f"{rx[0]}  ({rx[1]})"
            d.rectangle([28, y, W - 28, y + 34], fill=lp, outline=(215, 217, 225), width=1)
            d.text((38, y + 7), f"Rx {_RX_LTRS[idx - 1]}.", font=fnt(FONT_BOLD, 15), fill=P)
            d.text(
                (102, y + 7),
                drug_label,
                font=fnt(FONT_BOLD, 15),
                fill=((200, 40, 40) if mf == "drug_name" else (10, 20, 100)),
            )
            if cs_flag and mf != "drug_name":
                d.text((W - 200, y + 9), "CONTROLLED", font=fnt(FONT_BOLD, 12), fill=(180, 0, 0))
            bg = (248, 249, 252) if idx % 2 == 0 else (255, 255, 255)
            qty = rng.randint(20, 90)
            d.rectangle([28, y + 34, W - 28, y + 96], fill=bg, outline=(215, 217, 225), width=1)
            sig_text = "[ILLEGIBLE]" if mf == "dosage" else rx[2]
            d.text(
                (42, y + 42),
                f"Sig: {sig_text}",
                font=fnt(FONT_ITAL, 14),
                fill=((200, 40, 40) if mf == "dosage" else (40, 40, 60)),
            )
            d.text(
                (42, y + 68),
                f"Qty #{qty}  |  {rx[3]} days supply  |  Est. Cost: {rx[4]}",
                font=fnt(FONT_REG, 13),
                fill=(60, 60, 80),
            )
            y += 96 + 4

        y += 14
        d.rectangle([28, y, W - 28, y + 50], fill=(248, 249, 252), outline=(215, 217, 225), width=1)
        if mf != "refills":
            _refills_row(d, y + 8, x0=38)
        y += 56
        d.rectangle([28, y, W - 28, y + 38], fill=(248, 249, 252), outline=(215, 217, 225), width=1)
        _dispense_row(d, y + 10, x0=38)
        y += 44

        if is_controlled:
            y += 8
            _controlled_box(d, y, x0=28)
            y += 52

        y += 20
        d.line([(28, y), (W - 28, y)], fill=(200, 202, 212), width=1)
        y += 10
        d.text((38, y + 6), c["doctor"], font=signature_fnt(40), fill=SIG_INK)
        y += 52
        d.line([(38, y), (460, y)], fill=(60, 60, 80), width=1)
        y += 6
        d.text((38, y + 2), "Prescriber's Signature", font=fnt(FONT_REG, 12), fill=(80, 80, 90))
        d.text(
            (38, y + 20),
            f"Signed: {rx_date.strftime('%m/%d/%Y')}",
            font=fnt(FONT_REG, 12),
            fill=(20, 20, 30),
        )
        d.rectangle([W - 310, y - 2, W - 28, y + 42], outline=(205, 207, 215), width=1)
        dea_str2 = "[MISSING]" if mf == "dea" else dea_num
        d.text(
            (W - 300, y + 4),
            f"DEA: {dea_str2}",
            font=fnt(FONT_MONO, 12),
            fill=((200, 40, 40) if mf == "dea" else (60, 60, 80)),
        )
        d.text((W - 300, y + 22), f"NPI: {c['npi']}", font=fnt(FONT_MONO, 12), fill=(60, 60, 80))
        d.text((W - 300, y + 40), f"Lic: {il_license}", font=fnt(FONT_MONO, 12), fill=(60, 60, 80))
        _clinic_stamp(d, W - 130, y + 60, c["hospital"], P)

    # ── Bottom barcode + ID (all styles) ─────────────────────────────────────
    draw_barcode(d, 60, H - 80, w=350, h=40)
    draw_qr_stub(d, W - 130, H - 88, size=70)
    d.text(
        (60, H - 32),
        f"Prescription ID: RX-{c['claim_number']}",
        font=fnt(FONT_MONO, 12),
        fill=(80, 80, 100),
    )

    _record_truth(
        doc_id or f"rx_{c['patient_id']}",
        c,
        rx_date=rx_date,
        drug_names=[item[0] for item in c["rx_list"]],
        missing_field=mf,
        **(
            {"claim_service_date": c["treatment_date"]}
            if c["fraud_reason"] == "date_conflict"
            else {}
        ),
    )
    return img


def generate_policy_amendment(c, th=None, handwritten=False, has_support=False):
    th = th or THEMES[0]
    P = th["primary"]
    W, H = 1700, 2200
    bg_color = (255, 252, 235) if handwritten else th["bg"]
    img = Image.new("RGB", (W, H), bg_color)
    d = ImageDraw.Draw(img)

    if handwritten:
        # Simpler header: no gradient, just a ruled line with hand-stamped look
        d.rectangle([0, 0, W, 8], fill=P)
        d.text((90, 22), "MediShield Health Insurance Ltd.", font=signature_fnt(42), fill=P)
        d.text(
            (90, 72),
            "123 Healthcare Blvd, Suite 500 • Chicago, IL 60601",
            font=fnt(FONT_REG, 15),
            fill=(80, 70, 50),
        )
        d.text((90, 96), "1-800-MEDISHIELD", font=fnt(FONT_REG, 14), fill=(100, 90, 60))
        d.line([(90, 128), (W - 90, 128)], fill=P, width=2)
        d.text(
            (90, 148),
            "Policy Amendment / Endorsement Request",
            font=signature_fnt(36),
            fill=(30, 30, 60),
        )
        d.line([(90, 200), (W - 90, 200)], fill=(160, 150, 120), width=1)
        # Policyholder info in signature font
        d.text((90, 222), "Policy No.:", font=fnt(FONT_BOLD, 17), fill=(80, 70, 50))
        d.text((280, 218), c["policy"], font=signature_fnt(32), fill=SIG_INK)
        d.text((90, 262), "Group No.:", font=fnt(FONT_BOLD, 17), fill=(80, 70, 50))
        d.text((280, 258), c["group_number"], font=signature_fnt(32), fill=SIG_INK)
        d.text((90, 302), "Policyholder:", font=fnt(FONT_BOLD, 17), fill=(80, 70, 50))
        d.text((310, 298), c["name"], font=signature_fnt(32), fill=SIG_INK)
        d.text((90, 342), "Date of Birth:", font=fnt(FONT_BOLD, 17), fill=(80, 70, 50))
        d.text((330, 338), c["dob"], font=signature_fnt(30), fill=SIG_INK)
        d.text((90, 382), "Address:", font=fnt(FONT_BOLD, 17), fill=(80, 70, 50))
        d.text((230, 378), c["address"], font=signature_fnt(28), fill=SIG_INK)
        d.line([(90, 425), (W - 90, 425)], fill=(160, 150, 120), width=1)
    else:
        gradient_rect(d, 0, 0, W, 155, P, tuple(min(255, v + 28) for v in P))
        d.text(
            (90, 30),
            "MEDISHIELD HEALTH INSURANCE LTD.",
            font=fnt(FONT_BOLD, 38),
            fill=(255, 255, 255),
        )
        d.text(
            (90, 80),
            "123 Healthcare Blvd, Suite 500 • Chicago, IL 60601",
            font=fnt(FONT_REG, 16),
            fill=(180, 205, 245),
        )
        d.text(
            (90, 108),
            "1-800-MEDISHIELD  |  www.medishield-insurance.com",
            font=fnt(FONT_REG, 14),
            fill=(160, 190, 240),
        )
        d.text((90, 180), "POLICY AMENDMENT / ENDORSEMENT REQUEST", font=fnt(FONT_BOLD, 30), fill=P)
        d.line([(90, 225), (W - 90, 225)], fill=P, width=3)
        d.text(
            (90, 250), f"Policy Number:   {c['policy']}", font=fnt(FONT_MONO, 20), fill=(0, 0, 0)
        )
        d.text(
            (90, 288),
            f"Group Number:    {c['group_number']}",
            font=fnt(FONT_MONO, 20),
            fill=(0, 0, 0),
        )
        d.text((90, 326), f"Policyholder:    {c['name']}", font=fnt(FONT_MONO, 20), fill=(0, 0, 0))
        d.text((90, 364), f"Date of Birth:   {c['dob']}", font=fnt(FONT_MONO, 20), fill=(0, 0, 0))
        d.text(
            (90, 402), f"Address:         {c['address']}", font=fnt(FONT_MONO, 18), fill=(0, 0, 0)
        )
        d.line([(90, 445), (W - 90, 445)], fill=(180, 180, 200), width=1)

    # Amendment type selection
    amend_type, amend_desc = c["amendment"]
    type_section_y = 445 if handwritten else 465
    d.text((90, type_section_y), "AMENDMENT TYPE:", font=fnt(FONT_BOLD, 22), fill=P)
    y = type_section_y + 45
    for atype, _ in AMENDMENT_TYPES:
        selected = atype == amend_type
        if handwritten and selected:
            # Hand-drawn X mark
            d.line([(90, y + 2), (112, y + 22)], fill=P, width=3)
            d.line([(112, y + 2), (90, y + 22)], fill=P, width=3)
        else:
            draw_checkbox(d, 90, y, size=22, checked=selected, color=P)
        d.text(
            (125, y),
            atype,
            font=fnt(FONT_BOLD if selected else FONT_REG, 19),
            fill=P if selected else (0, 0, 0),
        )
        y += 50

    y += 20
    d.line([(90, y), (W - 90, y)], fill=(180, 180, 200), width=1)
    y += 25
    d.text((90, y), "DESCRIPTION OF REQUEST:", font=fnt(FONT_BOLD, 20), fill=P)
    y += 40
    if handwritten:
        # No box, just lines with handwritten text
        d.text((110, y), amend_desc, font=signature_fnt(28), fill=SIG_INK)
        d.line([(90, y + 50), (W - 90, y + 50)], fill=(180, 170, 140), width=1)
        d.text(
            (110, y + 60),
            f"Effective Date: {c['treatment_date'].strftime('%m/%d/%Y')}",
            font=signature_fnt(26),
            fill=SIG_INK,
        )
        d.line([(90, y + 108), (W - 90, y + 108)], fill=(180, 170, 140), width=1)
    else:
        draw_rounded_rect(
            d,
            90,
            y,
            W - 90,
            y + 120,
            radius=6,
            fill=(248, 250, 252),
            outline=(180, 190, 210),
            width=1,
        )
        d.text((110, y + 18), amend_desc, font=signature_fnt(26), fill=SIG_INK)
        d.text(
            (110, y + 60),
            f"Effective Date Requested: {c['treatment_date'].strftime('%m/%d/%Y')}",
            font=fnt(FONT_REG, 18),
            fill=(0, 0, 0),
        )

    y += 180
    d.text(
        (90, y), "REQUIRED SUPPORTING DOCUMENTS ENCLOSED:", font=fnt(FONT_BOLD, 18), fill=(0, 0, 0)
    )
    if has_support:
        docs = AMEND_DOCS.get(
            amend_type,
            [
                "Government-issued Photo ID",
                "Proof of Address (utility bill / lease)",
                "Previous Policy Schedule (if applicable)",
            ],
        )
    else:
        docs = [
            "Government-issued Photo ID",
            "Proof of Address (utility bill / lease)",
            "Previous Policy Schedule (if applicable)",
        ]
    y += 36
    for doc_item in docs:
        if handwritten:
            d.line([(90, y + 2), (112, y + 22)], fill=(12, 40, 110), width=2)
            d.line([(112, y + 2), (90, y + 22)], fill=(12, 40, 110), width=2)
            d.text((130, y), doc_item, font=signature_fnt(26), fill=(30, 20, 10))
        else:
            draw_checkbox(d, 90, y, size=18, checked=True, color=(12, 40, 110))
            d.text((120, y), doc_item, font=fnt(FONT_REG, 18), fill=(0, 0, 0))
        y += 38

    y += 90
    # Left: policyholder signature — text drawn well above the underline so the line doesn't cross it
    d.text((92, y - 82), c["name"].split()[0], font=signature_fnt(46), fill=SIG_INK)
    d.line([(90, y), (600, y)], fill=(0, 0, 0), width=1)
    d.text((92, y + 10), "Policyholder Signature", font=fnt(FONT_REG, 14), fill=(60, 60, 60))
    d.text(
        (92, y + 34),
        f"Date: {c['treatment_date'].strftime('%m/%d/%Y')}",
        font=fnt(FONT_REG, 14),
        fill=(0, 0, 0),
    )
    d.text((92, y + 58), c["name"], font=fnt(FONT_REG, 14), fill=(0, 0, 0))
    d.text((92, y + 76), "Printed Name", font=fnt(FONT_REG, 12), fill=(110, 110, 110))
    d.text((92, y + 98), f"Policy No.: {c['policy']}", font=fnt(FONT_MONO, 13), fill=(0, 0, 0))

    # Right: authorized officer (blank, to be filled)
    d.line([(W // 2 + 100, y), (W - 90, y)], fill=(0, 0, 0), width=1)
    d.text(
        (W // 2 + 102, y + 10),
        "Authorized Officer Signature",
        font=fnt(FONT_REG, 14),
        fill=(60, 60, 60),
    )
    d.text((W // 2 + 102, y + 34), "Date: _______________", font=fnt(FONT_REG, 14), fill=(0, 0, 0))
    d.text(
        (W // 2 + 102, y + 58),
        "___________________________",
        font=fnt(FONT_REG, 14),
        fill=(0, 0, 0),
    )
    d.text((W // 2 + 102, y + 76), "Printed Name", font=fnt(FONT_REG, 12), fill=(110, 110, 110))

    # FOR OFFICE USE ONLY
    y += 140
    d.rectangle([90, y, W - 90, y + 130], fill=(240, 241, 250), outline=(160, 165, 200), width=1)
    d.text((106, y + 10), "FOR OFFICE USE ONLY", font=fnt(FONT_BOLD, 16), fill=(12, 40, 110))
    d.line([(90, y + 42), (W - 90, y + 42)], fill=(160, 165, 200), width=1)

    col1_x, col2_x, col3_x = 110, 660, 1150
    fy = y + 72

    d.text(
        (col1_x, fy - 20),
        "Authorized MediShield Officer:",
        font=fnt(FONT_REG, 13),
        fill=(80, 80, 90),
    )
    d.line([(col1_x, fy), (col1_x + 470, fy)], fill=(130, 130, 145), width=1)

    d.text((col2_x, fy - 20), "Approval Date:", font=fnt(FONT_REG, 13), fill=(80, 80, 90))
    d.line([(col2_x, fy), (col2_x + 400, fy)], fill=(130, 130, 145), width=1)

    d.text((col3_x, fy - 20), "Policy Issuance Ref #:", font=fnt(FONT_REG, 13), fill=(80, 80, 90))
    d.line([(col3_x, fy), (W - 110, fy)], fill=(130, 130, 145), width=1)

    d.text((col1_x + 5, fy + 10), "Signature / Stamp", font=fnt(FONT_REG, 11), fill=(140, 140, 155))
    d.text((col2_x + 5, fy + 10), "DD / MM / YYYY", font=fnt(FONT_REG, 11), fill=(140, 140, 155))
    d.text((col3_x + 5, fy + 10), "Internal Use Only", font=fnt(FONT_REG, 11), fill=(140, 140, 155))

    return img


# ──────────────────────────────────────────────
# Dataset summary generator
# ──────────────────────────────────────────────
# Which single document category carries the fraud signal for each fraud type.
# duplicate_claim: only the _dup file is fraud; the original claim is clean.
FRAUD_DOC_TYPE = {
    "date_conflict": "prescriptions",
    "proc_diag_mismatch": "claim_forms",
    "readmission_30d": "discharge_summaries",
    "amount_under_10k": "claim_forms",
    "name_mismatch": "id_documents",
    # duplicate_claim → handled explicitly on the _dup file; not in this map
}

FRAUD_SIGNAL_DESC = {
    "duplicate_claim": "Two claim files submitted with the same claim number and identical service date, indicating a re-submitted or double-billed claim.",
    "date_conflict": "Prescription date is 45+ days after the claim/discharge date, creating a temporal impossibility.",
    "proc_diag_mismatch": "Maternity/obstetric CPT code (59400) billed against a non-maternity primary diagnosis (e.g., diabetes, hypertension).",
    "readmission_30d": "Discharge summary shows a prior hospitalization ending fewer than 30 days before the current admission — trigger for readmission fraud review.",
    "amount_under_10k": "Total billed amount set to $9,875.00 — just below the $10,000 automated review threshold (structuring behavior).",
    "uncovered_procedure": "Cosmetic/experimental CPT code (e.g., Blepharoplasty 15822) billed under standard medical coverage with a non-cosmetic diagnosis.",
}


def _expected_decision(entry, cluster=None, truth_entry=None):
    category = entry.get("category")
    if category == "unknown":
        return "ESCALATE", []

    issues = []
    if category not in (
        "id_documents",
        "claim_forms",
        "discharge_summaries",
        "prescriptions",
        "policy_amendments",
    ):
        issues.append(f"unsupported or missing category: {category!r}")
    if cluster is None:
        issues.append("cluster data is missing")
    if truth_entry is None:
        issues.append("truth data is missing")
    if issues:
        return None, issues

    is_fraud = cluster.get("is_fraud")
    fraud_reason = cluster.get("fraud_reason")
    if not isinstance(is_fraud, bool):
        issues.append("cluster is_fraud is missing or is not boolean")
    if is_fraud and fraud_reason not in (*FRAUD_DOC_TYPE, "duplicate_claim"):
        issues.append(f"fraud scenario is missing or unsupported: {fraud_reason!r}")
    if not is_fraud and fraud_reason is not None:
        issues.append(f"non-fraud cluster has fraud scenario {fraud_reason!r}")

    expected_doc_fraud = is_fraud and (
        (
            fraud_reason == "duplicate_claim"
            and category == "claim_forms"
            and entry.get("doc_id", "").endswith("_dup")
        )
        or FRAUD_DOC_TYPE.get(fraud_reason) == category
    )
    if entry.get("fraud_label") is not expected_doc_fraud:
        issues.append(
            f"metadata fraud_label={entry.get('fraud_label')!r}, expected {expected_doc_fraud!r} from cluster scenario"
        )
    expected_reason = fraud_reason if expected_doc_fraud else None
    if entry.get("fraud_reason") != expected_reason:
        issues.append(
            f"metadata fraud_reason={entry.get('fraud_reason')!r}, expected {expected_reason!r}"
        )

    edge_flags = set(cluster.get("edge_flags", []))
    metadata_flags = set(entry.get("edge_flags", []))
    tampered = False
    expired = False
    missing_field_type = None
    uncovered = "uncovered_procedure" in edge_flags

    if category == "id_documents":
        tampered_flag = "tampered_id" in edge_flags
        expired_flag = "expired_id" in edge_flags
        if ("tampered_id" in metadata_flags) != tampered_flag:
            issues.append("metadata tampered flag contradicts the cluster edge flags")
        if ("expired_id" in metadata_flags) != expired_flag:
            issues.append("metadata expired flag contradicts the cluster edge flags")
        if "tampered" not in truth_entry or not isinstance(truth_entry.get("tampered"), bool):
            issues.append("truth tampered flag is missing or is not boolean")
        elif truth_entry["tampered"] != tampered_flag:
            issues.append("truth tampered flag contradicts the cluster edge flags")
        if "expired" not in truth_entry or not isinstance(truth_entry.get("expired"), bool):
            issues.append("truth expired flag is missing or is not boolean")
        elif truth_entry["expired"] != expired_flag:
            issues.append("truth expired flag contradicts the cluster edge flags")
        if cluster.get("id_type") not in _ID_GENERATORS:
            issues.append(f"unsupported or missing ID type: {cluster.get('id_type')!r}")
        tampered = tampered_flag
        expired = expired_flag

    elif category == "claim_forms":
        missing_field_type = cluster.get("missing_field_type")
        if "missing_field_type" not in cluster:
            issues.append("cluster missing_field_type is absent")
        elif "missing_field_type" not in truth_entry:
            issues.append("truth missing_field_type is absent")
        elif truth_entry.get("missing_field_type") != missing_field_type:
            issues.append("truth missing_field_type contradicts the cluster")
        if ("missing_fields" in edge_flags) != bool(missing_field_type):
            issues.append("claim missing-field type contradicts the missing_fields edge flag")
        if ("missing_fields" in metadata_flags) != ("missing_fields" in edge_flags):
            issues.append("metadata missing_fields flag contradicts the cluster edge flags")
        if ("uncovered_procedure" in metadata_flags) != uncovered:
            issues.append("metadata uncovered_procedure flag contradicts the cluster edge flags")

    elif category == "prescriptions":
        missing_field_type = cluster.get("rx_missing_field_type")
        if "rx_missing_field_type" not in cluster:
            issues.append("cluster rx_missing_field_type is absent")
        elif "missing_field" not in truth_entry:
            issues.append("truth prescription missing_field is absent")
        elif truth_entry.get("missing_field") != missing_field_type:
            issues.append("truth prescription missing_field contradicts the cluster")
        if ("missing_fields" in entry.get("edge_flags", [])) != bool(missing_field_type):
            issues.append("prescription missing-field type contradicts the metadata edge flag")

    if issues:
        return None, issues

    if category == "policy_amendments" or expected_doc_fraud:
        return "ESCALATE", []
    if category == "id_documents":
        if tampered:
            return "ESCALATE", []
        if expired:
            return "REJECT", []
    if category == "claim_forms" and (uncovered or missing_field_type):
        return "REJECT", []
    if category == "prescriptions" and missing_field_type:
        return "REJECT", []
    return "APPROVE", []


def generate_dataset_summary(metadata, clusters, out_dir, policy_sections=None):
    from collections import defaultdict

    counts = defaultdict(int)
    for m in metadata:
        counts[m["category"]] += 1
    total = sum(counts.values())

    cluster_map = defaultdict(list)
    for m in metadata:
        if m.get("case_cluster_id") is not None:
            cluster_map[m["case_cluster_id"]].append(m["doc_id"])

    fraud_clusters = [c for c in clusters if c["is_fraud"]]

    # Edge case lists
    expired_ids = [c for c in clusters if "expired_id" in c["edge_flags"]]
    missing_fld = [c for c in clusters if "missing_fields" in c["edge_flags"]]
    uncovered_proc = [
        c for c in clusters if "uncovered_procedure" in c["edge_flags"] and not c["is_fraud"]
    ]
    blurry_docs = [m for m in metadata if m.get("blur_simulated")]

    policy_sections = policy_sections or [
        ("Cover Page", 1),
        ("1. Schedule of Benefits", 2),
        ("2. Definitions", 3),
        ("3. Inclusions and Exclusions", 4),
        ("   3.1 Inclusions", 4),
        ("   3.2 Exclusions", 4),
        ("4. Optional Riders", 5),
        ("5. Claims Procedure", 6),
        ("   5.1 Cashless Workflow", 6),
        ("   5.2 Reimbursement Workflow", 6),
        ("   5.3 Document Checklist", 6),
        ("   5.4 Grievance Contacts", 7),
        ("6. HIPAA Compliance", 8),
        ("7. Policyholder Attestation", 8),
    ]

    lines = [
        "# MediShield Synthetic Dataset Summary",
        "",
        "**Generated:** deterministic dataset seed 42",
        f"**Total documents:** {total}  |  **Categories:** {len(counts)}  |  "
        f"**Case clusters:** {len(cluster_map)}  |  **Fraud clusters:** {len(fraud_clusters)}",
        "",
        "---",
        "",
        "## 1. Document Counts per Category",
        "",
        "| Category             | Count |",
        "|----------------------|-------|",
    ]
    for cat in [
        "claim_forms",
        "id_documents",
        "discharge_summaries",
        "prescriptions",
        "policy_amendments",
        "unknown",
    ]:
        lines.append(f"| {cat:<20} | {counts.get(cat, 0):>5} |")
    lines += [f"| **TOTAL**            | {total:>5} |", ""]

    lines += [
        "---",
        "",
        "## 2. Case Cluster Map",
        "",
        "Each cluster ID maps to one document per category linked to the same patient, ",
        "policy number, and treatment episode.",
        "",
    ]
    for cid in sorted(cluster_map.keys()):
        docs_str = ", ".join(cluster_map[cid])
        lines.append(f"- **{cid}**: {docs_str}")
    lines.append("")

    lines += [
        "---",
        "",
        "## 3. Fraud-Positive Clusters",
        "",
        "Six clusters contain deliberately injected fraud signals for pipeline testing.",
        "",
        "| Cluster | Patient ID | Fraud Type | Signal Description |",
        "|---------|------------|------------|-------------------|",
    ]
    for c in fraud_clusters:
        sig = FRAUD_SIGNAL_DESC.get(c["fraud_reason"], "See metadata.")
        lines.append(f"| {c['cluster_id']} | {c['patient_id']} | `{c['fraud_reason']}` | {sig} |")
    lines.append("")

    lines += [
        "---",
        "",
        "## 4. Edge Case Inventory",
        "",
        "### 4.1 Expired ID Documents (5 clusters)",
        "",
    ]
    for c in expired_ids:
        lines.append(
            f"- **{c['cluster_id']}** ({c['patient_id']}): ID expiry date set before treatment date."
        )
    lines += [
        "",
        "### 4.2 Claims with Missing Mandatory Fields (4 clusters)",
        "",
    ]
    for c in missing_fld:
        lines.append(
            f"- **{c['cluster_id']}** ({c['patient_id']}): Physician signature and rendering NPI omitted."
        )
    lines += [
        "",
        "### 4.3 Uncovered Procedures (5 edge-case clusters, not fraud-labeled)",
        "",
    ]
    for c in uncovered_proc:
        cpt = c["cpt_list"][0]
        lines.append(
            f"- **{c['cluster_id']}** ({c['patient_id']}): CPT {cpt[0]} — {cpt[1]} (not covered under standard plan)."
        )
    lines += [
        "",
        "### 4.4 Blurry / Low-Quality Scan Simulation (3 documents)",
        "",
        "GaussianBlur applied at generation time; see `blur_simulated` flag in metadata.json.",
        "",
    ]

    lines += [
        "---",
        "",
        "## 5. Policy PDF Section Index (`policy/medishield_gold_plan.pdf`)",
        "",
        "| Section | Page |",
        "|---------|------|",
    ]
    for sec, pg in policy_sections:
        lines.append(f"| {sec} | {pg} |")
    lines += [
        "",
        "---",
        "",
        "## 6. Metadata Schema (`dataset/metadata.json`)",
        "",
        "```json",
        "{",
        '  "doc_id":          "claim_PT_12345",',
        '  "category":        "claim_forms",',
        '  "case_cluster_id": "C_001",',
        '  "fraud_label":     true,',
        '  "fraud_reason":    "duplicate_claim",',
        '  "edge_flags":      [],',
        '  "patient_id":      "PT_12345",',
        '  "policy_number":   "MED-GLD-1234567",',
        '  "blur_simulated":  false,',
        '  "file_path":       "dataset/claim_forms/claim_PT_12345.png"',
        "}",
        "```",
        "",
    ]

    path = os.path.join(out_dir, "dataset_summary.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


# ──────────────────────────────────────────────
# Main orchestration
# ──────────────────────────────────────────────
if __name__ == "__main__":
    OUT = os.environ.get("DOC_OUT_DIR", os.path.join(os.getcwd(), "dataset"))
    os.makedirs(OUT, exist_ok=True)
    TRUTH.clear()

    CATS = [
        "claim_forms",
        "id_documents",
        "discharge_summaries",
        "prescriptions",
        "policy_amendments",
    ]
    import glob as _glob

    for cat in CATS:
        cat_dir = os.path.join(OUT, cat)
        os.makedirs(cat_dir, exist_ok=True)
        for old in _glob.glob(os.path.join(cat_dir, "*.png")) + _glob.glob(
            os.path.join(cat_dir, "*.pdf")
        ):
            os.remove(old)

    print("Generating 30 US patient clusters ...")
    clusters, blurry_doc_idx = generate_patient_clusters(30)

    metadata = []
    doc_counter = 0

    def filter_edge_flags(flags, category):
        if category == "id_documents":
            return [f for f in flags if f in ("expired_id", "expiring_soon_id", "tampered_id")]
        elif category == "claim_forms":
            return [f for f in flags if f in ("missing_fields", "uncovered_procedure")]
        return []

    amend_with_support_idx = set(rng.sample(range(30), 10))
    amend_handwritten_idx = set(rng.sample(range(30), 10))

    print("Rendering documents ...")
    for idx, c in enumerate(clusters):
        th = THEMES[c["theme_idx"]]

        # ── ID Document ──────────────────────────────────────
        is_blur = doc_counter in blurry_doc_idx
        is_expired = "expired_id" in c["edge_flags"]
        id_doc_id = f"id_{c['patient_id']}"
        id_img = generate_id_document(c, expired=is_expired, blur=is_blur, doc_id=id_doc_id)
        img = id_img
        path = os.path.join(OUT, "id_documents", f"{id_doc_id}.png")
        save_image(img, path, scan=(not is_blur), blur=False)
        _fl = c["is_fraud"] and FRAUD_DOC_TYPE.get(c["fraud_reason"]) == "id_documents"
        metadata.append(
            {
                "doc_id": f"id_{c['patient_id']}",
                "category": "id_documents",
                "case_cluster_id": c["cluster_id"],
                "fraud_label": _fl,
                "fraud_reason": c["fraud_reason"] if _fl else None,
                "edge_flags": filter_edge_flags(c["edge_flags"], "id_documents"),
                "patient_id": c["patient_id"],
                "policy_number": c["policy"],
                "blur_simulated": is_blur,
                "file_path": path,
            }
        )
        doc_counter += 1

        # ── Claim Form (CMS-1500 for outpatient, UB-04 for inpatient) ────
        is_blur = doc_counter in blurry_doc_idx
        is_missing = "missing_fields" in c["edge_flags"]
        claim_doc_id = f"claim_{c['patient_id']}"
        if c.get("claim_type") == "UB04":
            img = generate_ub04_form(c, th=th, doc_id=claim_doc_id)
        else:
            img = generate_claim_form(c, missing_fields=is_missing, th=th, doc_id=claim_doc_id)
        path = os.path.join(OUT, "claim_forms", f"{claim_doc_id}.png")
        save_image(img, path, scan=True, blur=is_blur)
        _fl = c["is_fraud"] and FRAUD_DOC_TYPE.get(c["fraud_reason"]) == "claim_forms"
        metadata.append(
            {
                "doc_id": claim_doc_id,
                "category": "claim_forms",
                "claim_form_type": c.get("claim_type", "CMS1500"),
                "case_cluster_id": c["cluster_id"],
                "fraud_label": _fl,
                "fraud_reason": c["fraud_reason"] if _fl else None,
                "edge_flags": filter_edge_flags(c["edge_flags"], "claim_forms"),
                "patient_id": c["patient_id"],
                "policy_number": c["policy"],
                "blur_simulated": is_blur,
                "file_path": path,
            }
        )
        doc_counter += 1

        # Duplicate claim file for duplicate_claim fraud cluster
        if c["fraud_reason"] == "duplicate_claim":
            path_dup = os.path.join(OUT, "claim_forms", f"claim_{c['patient_id']}_dup.png")
            save_image(img, path_dup, scan=True, blur=False)
            TRUTH[f"claim_{c['patient_id']}_dup"] = dict(TRUTH[claim_doc_id])
            metadata.append(
                {
                    "doc_id": f"claim_{c['patient_id']}_dup",
                    "category": "claim_forms",
                    "case_cluster_id": c["cluster_id"],
                    "fraud_label": True,
                    "fraud_reason": "duplicate_claim",
                    "edge_flags": ["duplicate_of_" + f"claim_{c['patient_id']}"],
                    "patient_id": c["patient_id"],
                    "policy_number": c["policy"],
                    "blur_simulated": False,
                    "file_path": path_dup,
                }
            )

        # ── Discharge Summary ────────────────────────────────
        is_blur = doc_counter in blurry_doc_idx
        discharge_doc_id = f"discharge_{c['patient_id']}"
        img = generate_discharge_summary(c, th=th, doc_id=discharge_doc_id)
        path = os.path.join(OUT, "discharge_summaries", f"{discharge_doc_id}.png")
        save_image(img, path, scan=True, blur=is_blur)
        _fl = c["is_fraud"] and FRAUD_DOC_TYPE.get(c["fraud_reason"]) == "discharge_summaries"
        metadata.append(
            {
                "doc_id": discharge_doc_id,
                "category": "discharge_summaries",
                "case_cluster_id": c["cluster_id"],
                "fraud_label": _fl,
                "fraud_reason": c["fraud_reason"] if _fl else None,
                "edge_flags": filter_edge_flags(c["edge_flags"], "discharge_summaries"),
                "patient_id": c["patient_id"],
                "policy_number": c["policy"],
                "blur_simulated": is_blur,
                "file_path": path,
            }
        )
        doc_counter += 1

        # ── Prescription ──────────────────────────────────────
        is_blur = doc_counter in blurry_doc_idx
        rx_mf = c.get("rx_missing_field_type")
        rx_doc_id = f"rx_{c['patient_id']}"
        img = generate_prescription(c, th=th, missing_field=rx_mf, doc_id=rx_doc_id)
        path = os.path.join(OUT, "prescriptions", f"{rx_doc_id}.png")
        save_image(img, path, scan=True, blur=is_blur)
        _fl = c["is_fraud"] and FRAUD_DOC_TYPE.get(c["fraud_reason"]) == "prescriptions"
        rx_edge = filter_edge_flags(c["edge_flags"], "prescriptions")
        if rx_mf:
            rx_edge = rx_edge + ["missing_fields"]
        metadata.append(
            {
                "doc_id": rx_doc_id,
                "category": "prescriptions",
                "case_cluster_id": c["cluster_id"],
                "fraud_label": _fl,
                "fraud_reason": c["fraud_reason"] if _fl else None,
                "edge_flags": rx_edge,
                "patient_id": c["patient_id"],
                "policy_number": c["policy"],
                "blur_simulated": is_blur,
                "file_path": path,
            }
        )
        doc_counter += 1

        # ── Policy Amendment ──────────────────────────────────
        is_blur = doc_counter in blurry_doc_idx
        amend_img = generate_policy_amendment(
            c,
            th=th,
            handwritten=(idx in amend_handwritten_idx),
            has_support=(idx in amend_with_support_idx),
        )
        if idx in amend_with_support_idx:
            combined = Image.new(
                "RGB",
                (max(amend_img.width, id_img.width), amend_img.height + id_img.height + 50),
                (255, 255, 255),
            )
            combined.paste(amend_img, (0, 0))
            combined.paste(id_img, (0, amend_img.height + 50))
            img = combined
        else:
            img = amend_img
        path = os.path.join(OUT, "policy_amendments", f"amend_{c['patient_id']}.png")
        save_image(img, path, scan=True, blur=is_blur)
        amendment_doc_id = f"amend_{c['patient_id']}"
        _record_truth(amendment_doc_id, c)
        metadata.append(
            {
                "doc_id": amendment_doc_id,
                "category": "policy_amendments",
                "case_cluster_id": c["cluster_id"],
                "fraud_label": False,
                "fraud_reason": None,
                "edge_flags": filter_edge_flags(c["edge_flags"], "policy_amendments")
                + (["has_supporting_docs"] if idx in amend_with_support_idx else []),
                "patient_id": c["patient_id"],
                "policy_number": c["policy"],
                "blur_simulated": is_blur,
                "file_path": path,
            }
        )
        doc_counter += 1

        print(
            f"  [{c['cluster_id']}] {c['name']:<30}  fraud={c['is_fraud']}  "
            f"flags={c['edge_flags'] or '–'}"
        )

    label_report = []
    clusters_by_id = {cluster["cluster_id"]: cluster for cluster in clusters}
    for entry in metadata:
        entry["file_path"] = os.path.relpath(entry["file_path"], OUT)
        if entry["doc_id"] not in TRUTH:
            matching_cluster = clusters_by_id.get(entry.get("case_cluster_id"))
            if matching_cluster is not None:
                _record_truth(entry["doc_id"], matching_cluster)

        label, issues = _expected_decision(
            entry,
            clusters_by_id.get(entry.get("case_cluster_id")),
            TRUTH.get(entry["doc_id"]),
        )
        if issues:
            entry.pop("expected_decision", None)
            label_report.append({"doc_id": entry["doc_id"], "issues": issues})
        else:
            entry["expected_decision"] = label

    # Save metadata.json
    meta_path = os.path.join(OUT, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=4, default=str)

    truth_path = os.path.join(OUT, "truth.json")
    with open(truth_path, "w", encoding="utf-8") as f:
        json.dump(TRUTH, f, indent=4, default=str)

    clusters_path = os.path.join(OUT, "clusters.json")
    with open(clusters_path, "w", encoding="utf-8") as f:
        json.dump(clusters, f, indent=4, default=str)

    label_report_path = os.path.join(OUT, "label_report.json")
    with open(label_report_path, "w", encoding="utf-8") as f:
        json.dump(label_report, f, indent=4)
    print(
        f"Expected-decision labels unset for {len(label_report)} documents; report -> {label_report_path}"
    )

    # Generate summary markdown
    summary_path = generate_dataset_summary(metadata, clusters, os.getcwd())

    from collections import Counter

    cat_counts = Counter(m["category"] for m in metadata)
    total_docs = sum(cat_counts.values())

    print(f"\n{'=' * 60}")
    print(f"Done!  {total_docs} documents generated in {OUT}/")
    for cat, cnt in sorted(cat_counts.items()):
        print(f"  {cat:<25} {cnt:>3} files")
    print(f"  metadata  -> {meta_path}")
    print(f"  summary   -> {summary_path}")
