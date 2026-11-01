"""
Generates UNKNOWN-category documents for the MediShield dataset.
These are documents the classifier should not recognise as any of the 5 standard types.
Saves PNGs to dataset/unknown/ and appends entries to dataset/metadata.json.
"""

import json
import os
import random

from generate_docs import generate_dataset_summary
from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = os.path.join("dataset", "unknown")
DATASET_ROOT = os.path.dirname(OUT)
os.makedirs(OUT, exist_ok=True)

rng = random.Random(99)  # separate seed so main dataset RNG is unaffected

# ── Font helpers (same paths as generate_docs.py) ────────────────────────────
FONT_BOLD = "arialbd.ttf"
FONT_REG = "arial.ttf"
FONT_MONO = "cour.ttf"


def fnt(name, size):
    try:
        return ImageFont.truetype(name, size)
    except Exception:
        return ImageFont.load_default()


# ── 1. Heavily blurred unreadable scan ───────────────────────────────────────
def gen_blurry_scan():
    W, H = 1200, 1600
    img = Image.new("RGB", (W, H), (245, 242, 238))
    d = ImageDraw.Draw(img)

    # Draw some form-like content that will be blurred beyond recognition
    for y in range(60, H - 60, 38):
        line_w = rng.randint(300, W - 120)
        d.line([(60, y), (60 + line_w, y)], fill=(30, 30, 30), width=rng.randint(1, 3))
    for _ in range(12):
        x = rng.randint(60, W - 200)
        y = rng.randint(60, H - 100)
        d.rectangle([x, y, x + rng.randint(80, 300), y + rng.randint(16, 32)], fill=(20, 20, 20))
    # Rectangles simulating text blocks
    for _ in range(6):
        x, y = rng.randint(60, 400), rng.randint(80, H - 200)
        d.rectangle(
            [x, y, x + rng.randint(200, 600), y + rng.randint(60, 120)],
            outline=(80, 80, 80),
            width=2,
        )

    # Heavy blur — radius 14 makes everything illegible
    img = img.filter(ImageFilter.GaussianBlur(radius=14))

    # Add scanner noise / slight yellowing
    import numpy as np

    arr = np.array(img).astype(float)
    noise = rng.gauss(0, 8)
    arr += noise
    arr = arr.clip(0, 255).astype("uint8")
    img = Image.fromarray(arr)

    # Coffee-stain ring in corner
    d2 = ImageDraw.Draw(img)
    d2.ellipse([W - 220, H - 220, W - 80, H - 80], outline=(190, 160, 110), width=6)
    d2.ellipse([W - 210, H - 210, W - 90, H - 90], outline=(200, 175, 130), width=2)

    return img


# ── 2. Bank statement ─────────────────────────────────────────────────────────
def gen_bank_statement():
    W, H = 1200, 1650
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)

    # Header band
    d.rectangle([0, 0, W, 130], fill=(0, 48, 120))
    d.text((50, 22), "FIRST NATIONAL BANK", font=fnt(FONT_BOLD, 34), fill=(255, 255, 255))
    d.text(
        (50, 72),
        "Member FDIC  |  firstnationalbank.com  |  1-800-555-0100",
        font=fnt(FONT_REG, 14),
        fill=(160, 195, 255),
    )
    d.text((W - 260, 42), "ACCOUNT STATEMENT", font=fnt(FONT_BOLD, 18), fill=(200, 220, 255))

    # Account info block
    d.rectangle([50, 150, W - 50, 290], fill=(240, 244, 252), outline=(180, 190, 220), width=1)
    d.text(
        (70, 165), f"Account Holder:   Robert J. Caldwell", font=fnt(FONT_REG, 16), fill=(0, 0, 0)
    )
    d.text(
        (70, 195), f"Account Number:   ****  ****  4872", font=fnt(FONT_MONO, 16), fill=(0, 0, 0)
    )
    d.text(
        (70, 225), f"Account Type:     Checking — Premium", font=fnt(FONT_REG, 16), fill=(0, 0, 0)
    )
    d.text(
        (70, 255),
        f"Statement Period: 01 Apr 2025 – 30 Apr 2025",
        font=fnt(FONT_REG, 16),
        fill=(0, 0, 0),
    )

    # Summary bar
    d.rectangle([50, 308, W - 50, 370], fill=(0, 48, 120))
    for label, val, x in [
        ("Opening Balance", "$  4,218.33", 70),
        ("Total Credits", "+ $12,540.00", 390),
        ("Total Debits", "- $ 9,876.45", 680),
        ("Closing Balance", "$  6,881.88", 940),
    ]:
        d.text((x, 316), label, font=fnt(FONT_REG, 11), fill=(160, 200, 255))
        d.text((x, 338), val, font=fnt(FONT_BOLD, 14), fill=(255, 255, 255))

    # Transactions table
    d.text((50, 390), "TRANSACTION HISTORY", font=fnt(FONT_BOLD, 16), fill=(0, 48, 120))
    d.line([(50, 415), (W - 50, 415)], fill=(0, 48, 120), width=2)

    headers = ["Date", "Description", "Reference", "Debit", "Credit", "Balance"]
    col_x = [50, 160, 560, 750, 890, 1020]
    for h, x in zip(headers, col_x):
        d.text((x, 422), h, font=fnt(FONT_BOLD, 13), fill=(0, 48, 120))
    d.line([(50, 444), (W - 50, 444)], fill=(180, 190, 220), width=1)

    txns = [
        ("01 Apr", "Opening Balance Brought Forward", "OB-2025", "", "", "4,218.33"),
        ("02 Apr", "Direct Deposit — Acme Corp Payroll", "DD-884421", "", "6,250.00", "10,468.33"),
        ("03 Apr", "Amazon Marketplace Purchase", "POS-33871", "94.17", "", "10,374.16"),
        ("05 Apr", "Whole Foods Market #4421", "POS-44109", "187.62", "", "10,186.54"),
        ("07 Apr", "AT&T Wireless AutoPay", "ACH-77203", "145.00", "", "10,041.54"),
        ("08 Apr", "Zelle Transfer — M. Caldwell", "ZLL-29011", "500.00", "", "9,541.54"),
        ("10 Apr", "Direct Deposit — Acme Corp Payroll", "DD-884588", "", "6,290.00", "15,831.54"),
        ("11 Apr", "ComEd Electric AutoPay", "ACH-88341", "214.33", "", "15,617.21"),
        ("14 Apr", "Chase Mortgage Payment", "ACH-10042", "2,100.00", "", "13,517.21"),
        ("18 Apr", "Trader Joe's #0812", "POS-55671", "63.44", "", "13,453.77"),
        ("21 Apr", "United Airlines — Ticket", "POS-99210", "487.90", "", "12,965.87"),
        ("22 Apr", "ATM Withdrawal — Chicago Loop", "ATM-03312", "300.00", "", "12,665.87"),
        ("24 Apr", "Starbucks #4409", "POS-22189", "8.75", "", "12,657.12"),
        ("25 Apr", "IRS Tax Refund", "GOV-55001", "", "4,750.00", "17,407.12"),
        ("26 Apr", "Nordstrom — Online Purchase", "POS-71122", "342.18", "", "17,064.94"),
        ("28 Apr", "Rent — 400 N Michigan Ave", "ACH-20019", "3,800.00", "", "13,264.94"),
        ("29 Apr", "Netflix Monthly Subscription", "POS-88001", "22.99", "", "13,241.95"),
        ("30 Apr", "Venmo Transfer — J. Park", "ZLL-41003", "2,060.00", "", "11,181.95"),
        ("30 Apr", "Interest Credit", "INT-APR25", "", "16.03", "11,197.98"),
        ("30 Apr", "Monthly Service Fee Waived", "FEE-WAV25", "", "", "11,197.98"),
    ]
    y = 455
    for i, row in enumerate(txns):
        bg = (248, 250, 255) if i % 2 == 0 else (255, 255, 255)
        d.rectangle([50, y, W - 50, y + 26], fill=bg)
        for val, x in zip(row, col_x):
            d.text((x, y + 5), val, font=fnt(FONT_MONO, 12), fill=(20, 20, 20))
        y += 26

    d.line([(50, y + 2), (W - 50, y + 2)], fill=(180, 190, 220), width=1)

    # Closing balance box
    y += 16
    d.rectangle([700, y, W - 50, y + 48], fill=(0, 48, 120))
    d.text(
        (720, y + 8),
        "Closing Balance as of 30 Apr 2025:",
        font=fnt(FONT_BOLD, 13),
        fill=(200, 220, 255),
    )
    d.text((720, y + 26), "$ 11,197.98", font=fnt(FONT_BOLD, 18), fill=(255, 255, 255))

    # Footer
    y += 80
    d.line([(50, y), (W - 50, y)], fill=(200, 205, 220), width=1)
    d.text(
        (50, y + 10),
        "This statement is produced for informational purposes only. Report discrepancies within 30 days.",
        font=fnt(FONT_REG, 11),
        fill=(120, 120, 140),
    )
    d.text(
        (50, y + 28),
        "First National Bank is a member of FDIC. Accounts insured up to $250,000.",
        font=fnt(FONT_REG, 11),
        fill=(120, 120, 140),
    )

    return img


# ── 3. Utility bill ───────────────────────────────────────────────────────────
def gen_utility_bill():
    W, H = 1200, 1600
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)

    # Header
    d.rectangle([0, 0, W, 110], fill=(237, 28, 36))
    d.text((50, 20), "ComEd", font=fnt(FONT_BOLD, 48), fill=(255, 255, 255))
    d.text(
        (50, 78),
        "An Exelon Company  |  comed.com  |  1-800-334-7661",
        font=fnt(FONT_REG, 13),
        fill=(255, 200, 200),
    )
    d.text((W - 280, 30), "ELECTRIC BILL", font=fnt(FONT_BOLD, 20), fill=(255, 255, 255))
    d.text((W - 280, 62), "Residential Rate", font=fnt(FONT_REG, 13), fill=(255, 200, 200))

    # Account summary box
    d.rectangle([50, 128, 580, 300], fill=(252, 242, 242), outline=(237, 28, 36), width=2)
    d.text((70, 142), "Account Number:", font=fnt(FONT_BOLD, 14), fill=(100, 0, 0))
    d.text((260, 142), "71-2204-8831-03", font=fnt(FONT_MONO, 14), fill=(0, 0, 0))
    d.text((70, 170), "Service Address:", font=fnt(FONT_BOLD, 14), fill=(100, 0, 0))
    d.text(
        (260, 170), "400 N Michigan Ave, Chicago, IL 60601", font=fnt(FONT_REG, 14), fill=(0, 0, 0)
    )
    d.text((70, 198), "Billing Period:", font=fnt(FONT_BOLD, 14), fill=(100, 0, 0))
    d.text((260, 198), "Mar 14 – Apr 13, 2025 (30 days)", font=fnt(FONT_REG, 14), fill=(0, 0, 0))
    d.text((70, 226), "Account Holder:", font=fnt(FONT_BOLD, 14), fill=(100, 0, 0))
    d.text((260, 226), "Linda A. Morrison", font=fnt(FONT_REG, 14), fill=(0, 0, 0))
    d.text((70, 254), "Rate Code:", font=fnt(FONT_BOLD, 14), fill=(100, 0, 0))
    d.text((260, 254), "DS — Residential Single-Phase", font=fnt(FONT_REG, 14), fill=(0, 0, 0))

    # Amount due box
    d.rectangle([620, 128, W - 50, 300], fill=(237, 28, 36))
    d.text((640, 144), "AMOUNT DUE", font=fnt(FONT_BOLD, 20), fill=(255, 255, 255))
    d.text((640, 182), "$  214.33", font=fnt(FONT_BOLD, 40), fill=(255, 255, 255))
    d.text((640, 238), "Due Date: May 5, 2025", font=fnt(FONT_REG, 16), fill=(255, 200, 200))
    d.text(
        (640, 264),
        "Auto-Pay enrolled — will auto-debit",
        font=fnt(FONT_REG, 12),
        fill=(255, 180, 180),
    )

    # Usage bar chart (simple)
    d.text((50, 320), "12-MONTH USAGE HISTORY (kWh)", font=fnt(FONT_BOLD, 14), fill=(237, 28, 36))
    months = ["May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr"]
    kwh_vals = [480, 620, 890, 940, 810, 520, 430, 510, 560, 490, 470, 608]
    bar_w, gap = 60, 18
    bx = 60
    max_kwh = max(kwh_vals)
    chart_top, chart_bot = 350, 530
    for mo, kw in zip(months, kwh_vals):
        bar_h = int((kw / max_kwh) * (chart_bot - chart_top))
        color = (237, 28, 36) if mo == "Apr" else (180, 50, 50)
        d.rectangle([bx, chart_bot - bar_h, bx + bar_w, chart_bot], fill=color)
        d.text(
            (bx + bar_w // 2, chart_bot - bar_h - 18),
            str(kw),
            font=fnt(FONT_REG, 10),
            fill=(60, 60, 60),
            anchor="mm",
        )
        d.text(
            (bx + bar_w // 2, chart_bot + 8),
            mo,
            font=fnt(FONT_REG, 11),
            fill=(60, 60, 60),
            anchor="mm",
        )
        bx += bar_w + gap
    d.line([(55, chart_bot), (bx - gap + 10, chart_bot)], fill=(180, 180, 180), width=1)

    # Charge breakdown
    y = 570
    d.text((50, y), "CHARGE DETAILS", font=fnt(FONT_BOLD, 15), fill=(237, 28, 36))
    d.line([(50, y + 24), (W - 50, y + 24)], fill=(237, 28, 36), width=2)
    y += 34
    charges = [
        ("Distribution Charge", "608 kWh × $0.0892", "$ 54.23"),
        ("Transmission Charge", "608 kWh × $0.0318", "$ 19.33"),
        ("Generation Supply Charge", "608 kWh × $0.0712", "$ 43.29"),
        ("Renewable Energy Charge", "608 kWh × $0.0024", "$  1.46"),
        ("Energy Infrastructure Fund", "608 kWh × $0.0014", "$  0.85"),
        ("Illinois Electricity Tax", "608 kWh × $0.0050", "$  3.04"),
        ("Municipal Utility Tax", "Flat rate (Chicago)", "$ 12.00"),
        ("Previous Balance", "Paid Apr 2 — Thank You", "$  0.00"),
        ("Customer Charge (monthly)", "Fixed", "$ 14.75"),
        ("State & Local Taxes (8.5%)", "Applied to supply", "$ 43.11"),
        ("Late Payment Charge", "None", "$  0.00"),
        ("ComEd CARE Program Credit", "Income-qualified", "- $  5.00"),
        ("Distributed Generation Adj.", "Net metering credit", "- $ 27.73"),
    ]
    for i, (desc, detail, amt) in enumerate(charges):
        bg = (252, 248, 248) if i % 2 == 0 else (255, 255, 255)
        d.rectangle([50, y, W - 50, y + 28], fill=bg)
        d.text((60, y + 6), desc, font=fnt(FONT_REG, 13), fill=(20, 20, 20))
        d.text((660, y + 6), detail, font=fnt(FONT_REG, 12), fill=(100, 100, 100))
        d.text((W - 130, y + 6), amt, font=fnt(FONT_MONO, 13), fill=(20, 20, 20))
        y += 28

    d.line([(50, y + 2), (W - 50, y + 2)], fill=(237, 28, 36), width=2)
    y += 10
    d.text((W - 240, y + 4), "TOTAL DUE:  $ 214.33", font=fnt(FONT_BOLD, 16), fill=(237, 28, 36))

    # Payment instructions
    y += 50
    d.rectangle([50, y, W - 50, y + 90], fill=(255, 248, 248), outline=(220, 180, 180), width=1)
    d.text((70, y + 10), "PAYMENT OPTIONS:", font=fnt(FONT_BOLD, 13), fill=(100, 0, 0))
    d.text(
        (70, y + 32),
        "Online: comed.com/pay  |  Phone: 1-800-334-7661  |  Mail: PO Box 6111, Carol Stream IL 60197",
        font=fnt(FONT_REG, 12),
        fill=(40, 40, 40),
    )
    d.text(
        (70, y + 54),
        "In-Person: Western Union, MoneyGram, CheckFreePay locations",
        font=fnt(FONT_REG, 12),
        fill=(40, 40, 40),
    )
    d.text(
        (70, y + 72),
        "Auto-Pay: Enrolled — no action required. Debit date: May 5, 2025.",
        font=fnt(FONT_REG, 12),
        fill=(40, 40, 40),
    )

    return img


# ── 4. Blank page / scanning error ───────────────────────────────────────────
def gen_blank_scan():
    W, H = 1200, 1600
    # Slightly off-white scanner bed colour
    img = Image.new("RGB", (W, H), (248, 246, 240))
    d = ImageDraw.Draw(img)

    import numpy as np

    arr = np.array(img).astype(float)
    # Scanner noise
    noise = np.random.RandomState(7).normal(0, 6, arr.shape)
    arr = (arr + noise).clip(0, 255).astype("uint8")
    img = Image.fromarray(arr)
    d = ImageDraw.Draw(img)

    # Faint scanner lines
    for y in range(0, H, 4):
        if rng.random() < 0.08:
            d.line([(0, y), (W, y)], fill=(230, 228, 222), width=1)

    # Shadow on left edge (scanner lid)
    for x in range(0, 30):
        alpha = int(60 * (1 - x / 30))
        d.line([(x, 0), (x, H)], fill=(200 - alpha, 198 - alpha, 192 - alpha), width=1)

    # Faint crease diagonal
    d.line([(0, 200), (400, 0)], fill=(235, 232, 226), width=2)

    # Coffee-stain ring
    d.ellipse([820, 980, 1040, 1180], outline=(195, 168, 115), width=5)
    d.ellipse([830, 990, 1030, 1170], outline=(205, 180, 130), width=2)
    d.ellipse([850, 1010, 1010, 1150], outline=(215, 192, 148), width=1)

    # Barely-visible stamp impression (too faint to read)
    for _ in range(3):
        x = rng.randint(100, 900)
        y = rng.randint(100, 1400)
        d.ellipse([x, y, x + 180, y + 70], outline=(235, 232, 226), width=1)

    # Blurry smudge
    patch = Image.new("RGB", (220, 80), (210, 205, 195))
    img.paste(patch, (300, 700))
    img = img.filter(ImageFilter.GaussianBlur(radius=1))

    return img


# ── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    docs = [
        (
            "unknown_blurry_scan_001",
            gen_blurry_scan,
            "Severely blurred unreadable scan — content indeterminate",
        ),
        (
            "unknown_bank_statement_001",
            gen_bank_statement,
            "Bank account statement — not a medical document",
        ),
        (
            "unknown_utility_bill_001",
            gen_utility_bill,
            "ComEd electric utility bill — not a medical document",
        ),
        (
            "unknown_blank_scan_001",
            gen_blank_scan,
            "Blank/near-blank page — accidental scanner submission",
        ),
    ]

    new_entries = []
    new_truth = {}
    for doc_id, gen_fn, note in docs:
        img = gen_fn()
        path = os.path.join(OUT, f"{doc_id}.png")
        img.save(path, "PNG")
        new_entries.append(
            {
                "doc_id": doc_id,
                "category": "unknown",
                "case_cluster_id": None,
                "fraud_label": False,
                "fraud_reason": None,
                "edge_flags": [],
                "patient_id": None,
                "policy_number": None,
                "blur_simulated": "blurry" in doc_id,
                "file_path": os.path.relpath(path, DATASET_ROOT).replace(os.sep, "/"),
                "expected_decision": "ESCALATE",
                "note": note,
            }
        )
        new_truth[doc_id] = {
            "patient_id": None,
            "policy_number": None,
            "cluster_id": None,
            "document_type": "UNKNOWN",
            "note": note,
        }
        print(f"  Generated: {path}")

    meta_path = os.path.join(DATASET_ROOT, "metadata.json")
    with open(meta_path, encoding="utf-8") as f:
        existing = json.load(f)
    existing = [entry for entry in existing if not entry.get("doc_id", "").startswith("unknown_")]
    existing.extend(new_entries)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=4, default=str)

    truth_path = os.path.join(DATASET_ROOT, "truth.json")
    with open(truth_path, encoding="utf-8") as f:
        truth = json.load(f)
    truth.update(new_truth)
    with open(truth_path, "w", encoding="utf-8") as f:
        json.dump(truth, f, indent=4, default=str)

    clusters_path = os.path.join(DATASET_ROOT, "clusters.json")
    with open(clusters_path, encoding="utf-8") as f:
        clusters = json.load(f)
    summary_path = generate_dataset_summary(existing, clusters, os.getcwd())

    print(f"\nDone. {len(new_entries)} UNKNOWN documents added.")
    print(f"metadata.json now has {len(existing)} total entries.")
    print(f"Dataset summary updated: {summary_path}")
