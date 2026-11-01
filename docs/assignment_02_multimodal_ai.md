# Assignment 02 — Multi-Agent Document Intake System
### MediShield Insurance | AI-Powered Claims Processing Platform

---

## 🏢 Business Context

**Company:** MediShield Health Insurance Ltd.
**Industry:** Health Insurance & Claims Management
**Headquarters:** Chicago, IL

MediShield is a mid-sized health insurance provider managing over 2 million active policyholders across 14 states. Each month, MediShield's operations team receives approximately 85,000 document submissions — scanned claim forms, hospital discharge summaries, prescription images, identity documents, and policy amendment requests. These arrive via email, mobile uploads, and physical scanning stations at partner hospitals.

Currently, a team of 120 document reviewers manually sorts, validates, and routes these submissions — a process that takes an average of 4.2 days per claim and costs MediShield $18.4M annually in processing overhead. Errors in manual classification have led to a 12% re-processing rate, delayed reimbursements, and 3 ongoing regulatory audits related to KYC non-compliance.

The VP of Operations has commissioned an **AI-powered multi-agent document intake system** that can automatically classify incoming documents, extract structured data, cross-reference against policy coverage, flag potential fraud, and issue a final Approve / Reject / Escalate decision — all within minutes of document receipt.

**Your role:** You are a founding ML engineer at the internal AI team. You are responsible for designing and deploying this multi-agent pipeline as a production-ready system with a case management UI for the operations team.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DOCUMENT INGESTION                           │
│         (Upload API — FastAPI endpoint, real-time intake)           │
└─────────────────────────────────────────────────┬───────────────────┘
                                                  │
                                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    CLASSIFIER AGENT (Vision LLM)                    │
│   Identifies doc type: Claim Form / ID Document / Discharge         │
│   Summary / Prescription / Policy Amendment / Unknown               │
└────────────────────────────┬────────────────────────────────────────┘
                             │  Routes based on document type
          ┌──────────────────┼─────────────────────┐
          ▼                  ▼                      ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────────┐
│   KYC AGENT      │ │  CLAIMS AGENT    │ │   POLICY AGENT       │
│ Identity verify  │ │ Extract amounts, │ │ RAG over uploaded    │
│ Expiry/tamper    │ │ diagnosis codes, │ │ policy PDFs; checks  │
│ detection        │ │ provider details │ │ procedure coverage   │
└──────────────────┘ └──────────────────┘ └──────────────────────┘
          │                  │                      │
          └──────────────────┼──────────────────────┘
                             ▼
              ┌──────────────────────────┐
              │   FRAUD DETECTION AGENT  │
              │ Cross-checks claim vs.   │
              │ patient history; anomaly │
              │ scoring                  │
              └─────────────┬────────────┘
                            ▼
              ┌──────────────────────────┐
              │    ORCHESTRATOR AGENT    │
              │ Aggregates all outputs;  │
              │ Final: Approve / Reject  │
              │ / Escalate + confidence  │
              └─────────────┬────────────┘
                            ▼
              ┌──────────────────────────┐
              │   CASE MANAGEMENT UI     │
              │  (Next.js + FastAPI)     │
              └──────────────────────────┘
```

**State Machine (LangGraph):**

`RECEIVED → CLASSIFIED → [PARALLEL: KYC + CLAIMS + POLICY] → FRAUD_CHECK → AGGREGATED → DECIDED`

Conditional edges after classification route documents to the relevant specialist agents. The orchestrator only fires once all upstream agents complete.

---

## 🧩 Components

### 1. Document Ingestion API
- FastAPI endpoint accepting multi-part file uploads (JPEG, PNG, PDF, TIFF)
- Assigns a unique `case_id` per submission
- Stores raw documents in object storage (S3 or local MinIO)
- Publishes job to a task queue (Redis or Celery)

### 2. Classifier Agent
- Uses a vision-capable LLM (Claude claude-sonnet-4-20250514 or GPT-4o) to inspect the document image
- Outputs a structured classification: `{ doc_type, confidence, routing_tags }`
- Supported doc types: `CLAIM_FORM`, `ID_DOCUMENT`, `DISCHARGE_SUMMARY`, `PRESCRIPTION`, `POLICY_AMENDMENT`, `UNKNOWN`
- Unrecognized or low-confidence documents are routed to a human review queue

### 3. OCR / Pre-processor
- Runs before specialist agents on image-based inputs
- Uses Tesseract or a vision LLM for structured text extraction
- Outputs a normalized JSON payload: `{ fields: [...], raw_text, bounding_boxes }`

### 4. KYC Agent
- Validates member ID, date of birth, policy number against the member database
- Checks document expiry dates (e.g., ID validity)
- Flags visual anomalies that may indicate tampering (font inconsistencies, pixel artifacts)
- Outputs: `{ kyc_passed: bool, flags: [...], confidence }`

### 5. Claims Agent
- Extracts: claim amount, ICD-10 diagnosis codes, CPT procedure codes, provider NPI, service date
- Validates the extracted schema against MediShield's claim submission standard
- Outputs: `{ extracted_fields, schema_valid: bool, validation_errors: [...] }`

### 6. Policy Agent (RAG)
- Accepts real-time policy PDF uploads via Docling for ingestion and chunking
- Stores chunks in a vector database (ChromaDB or Qdrant)
- Given the procedure codes from the Claims Agent, retrieves relevant policy clauses
- Outputs: `{ covered: bool, coverage_percentage, policy_clause, exclusions: [...] }`

### 7. Fraud Detection Agent
- Queries patient claim history from the database
- Scores the current claim against statistical baselines (duplicate submissions, frequency anomalies, provider billing patterns)
- Outputs: `{ fraud_score: float, anomalies: [...], risk_level: LOW | MEDIUM | HIGH }`

### 8. Orchestrator Agent
- Waits for all upstream agent outputs via LangGraph's state aggregation
- Applies a weighted decision rule:
  - `APPROVE`: KYC passed + claim valid + covered + fraud score < 0.3
  - `REJECT`: KYC failed OR procedure not covered OR schema invalid
  - `ESCALATE`: fraud score ≥ 0.3 OR any agent confidence < 0.6
- Outputs: `{ decision, confidence, justification, agent_summaries }`

### 9. Case Management UI (Next.js + FastAPI)
- **Dashboard view:** List of all incoming cases with status badges (Processing / Approved / Rejected / Escalated)
- **Case detail view:** Document image viewer + per-agent output panel (collapsible)
- **Decision panel:** Final decision, confidence score, justification text
- **Human review queue:** Escalated cases with override capability for ops staff
- **Audit log:** Full trace of agent decisions per case, timestamped

---

## 📦 Deliverables

1. **Multi-Agent Pipeline** — fully functional LangGraph pipeline with all 7 agents implemented and connected
2. **Ingestion API** — FastAPI backend with file upload, case management endpoints, and agent orchestration trigger
3. **Policy RAG Module** — real-time PDF ingestion using Docling + vector store retrieval, tested with at least 2 sample policy documents
4. **Case Management UI** — Next.js frontend with dashboard, case detail, and human review queue
5. **Sample Dataset** — minimum 20 synthetic document images (mix of valid/invalid/fraudulent cases) with ground-truth labels for evaluation
6. **Architecture Diagram** — updated diagram showing actual component names, models used, and data flow
7. **README** — setup instructions, environment variables, and a walkthrough of one end-to-end case

---

## 📊 Evaluation Criteria

| Criteria | Weight | Description |
|---|---|---|
| **Classification Accuracy** | 20% | % of documents correctly classified by the Classifier Agent across the 20-case test set |
| **Extraction Completeness** | 20% | % of required fields successfully extracted by the Claims Agent (ICD codes, CPT codes, amounts, provider) |
| **Policy Retrieval Quality** | 15% | Relevance of retrieved policy clauses to the queried procedure codes (manual spot-check) |
| **Decision Correctness** | 25% | % of final Approve / Reject / Escalate decisions matching ground-truth labels |
| **UI Functionality** | 10% | Dashboard loads, case detail renders, human override works end-to-end |
| **Code Quality & Structure** | 10% | Clear agent separation, typed interfaces between agents, no hardcoded credentials |

**Minimum passing threshold:** 70% overall weighted score, with Decision Correctness ≥ 60%.

---

## 🌟 Bonus Challenges

- **Confidence Calibration:** Plot a calibration curve — does the Orchestrator's confidence score correlate with actual accuracy across the test set?
- **Streaming Updates:** Use WebSockets to push real-time agent status updates to the UI as each agent completes (e.g., "KYC Agent: ✅ Passed")
- **Tamper Detection:** Implement a lightweight image forensics check in the KYC Agent (ELA — Error Level Analysis) to detect JPEG manipulation
- **Multi-language Support:** Handle documents in Spanish or Hindi using a multilingual OCR model
- **Audit Export:** Add a "Download Case Report" button in the UI that generates a PDF summary of the case with all agent outputs
- **LangSmith Tracing:** Integrate LangSmith to trace every agent call, token count, and latency per case for observability
