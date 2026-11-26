# Dev 40 Policy Citation Diagnosis

Offline reconstruction used the original v3 prompt, cached Groq responses, local Qdrant retrieval and the cross-encoder. No Groq calls were made. The retrieval CSV from this run contains the primary retrieved clause and repeats it for each code; it does not preserve each code's individual model answer. The cached answers below were reconstructed individually.

The common cited chunk is Gold coverage chunk `ab121388-a0c9-5885-be1c-6e819dfc0a4d`; its full text is in [the retrieval CSV](eval_20261126T043835Z-c93a941c_retrieval.csv). Relevant exact excerpts:

- `Diagnostic services: laboratory tests, blood panels, urinalysis, pathology.`
- `Diagnostic imaging: X-ray, CT scan, MRI, PET scan, echocardiogram, ultrasound.`
- `Surgical services: physician fees, anesthesia, operating room, post-operative care.`
- `Day Care Procedures as defined in Section 2.` follows the surgical sentence in the chunk.
- `Mental health and substance use disorder treatment (inpatient and outpatient), as required by the Mental Health Parity and Addiction Equity Act (MHPAEA).`
- `Emergency room services, including stabilization and observation.`

The day-care chunk `baf9a0f0-fed7-5ec2-a340-6e41104cd60a` includes: `Day Care Procedures are covered under inpatient benefits despite not requiring an overnight stay. Examples include cataract surgery, chemotherapy sessions, hemodialysis, and laparoscopic procedures completed within a single day.`

| Claim | CPT | Cached citation and result |
|---|---|---|
| claim_PT_99733 | 80053 | Diagnostic services excerpt above; verbatim match. |
| claim_PT_99733 | 90837 | No citation; `covered=null`, despite a retrieved mental-health excerpt. |
| claim_PT_99733 | 27447 | Surgical services excerpt above; verbatim match. |
| claim_PT_99733 | 99291 | No citation; `covered=null`, despite a retrieved emergency-room excerpt. |
| claim_PT_20322 | 70553 | Diagnostic imaging excerpt above; verbatim match. |
| claim_PT_20322 | 93000 | No citation; `covered=null`; the common coverage chunk was retrieved. |
| claim_PT_39451 | 36415 | Diagnostic services excerpt above; verbatim match. |
| claim_PT_39451 | 47562 | Day-care chunk excerpt above; verbatim match. |
| claim_PT_39451 | 43239 | `Day Care Procedures as defined in Section 2.\n\nSurgical services: physician fees, anesthesia, operating room, post-operative care.` Not verbatim: both sentences occur in the same chunk but in the opposite order. |
| claim_PT_67125 | 43239 | Same reversed citation as claim_PT_39451; not verbatim. |
| claim_PT_67125 | 90837 | No citation; `covered=null`, despite a retrieved mental-health excerpt. |
| claim_PT_67125 | 27447 | Surgical services excerpt above; verbatim match. |
| claim_PT_55056 | 29827 | Surgical services excerpt above; verbatim match. |
| claim_PT_55056 | 27447 | Surgical services excerpt above; verbatim match. |
| claim_PT_55056 | 93000 | No citation; `covered=null`; the common coverage chunk was retrieved. |

No citation threshold was lowered and the reversed citation was not accepted. Null model answers cannot be safely converted into coverage decisions by text normalization.