import json
import re
from pathlib import Path
from typing import Any

import pytest

from packages.agents.claims.agent import CLAIMS_PROMPT_VERSION, ClaimsExtraction
from packages.agents.classifier.agent import CLASSIFIER_PROMPT_VERSION, ClassificationPrediction
from packages.agents.kyc.agent import KYC_PROMPT_VERSION, TamperAssessment
from packages.agents.ocr.agent import OCR_PROMPT_VERSION, OcrLLMOutput
from packages.agents.policy.agent import POLICY_PROMPT_VERSION, PolicyAnswer
from packages.core.llm.prompts import PromptLoader
from packages.core.models import JustificationDraft

ROOT = Path(__file__).resolve().parents[2]
PROMPT_CASES = (
    ("classifier", CLASSIFIER_PROMPT_VERSION, ClassificationPrediction),
    ("ocr", OCR_PROMPT_VERSION, OcrLLMOutput),
    ("kyc_tamper", KYC_PROMPT_VERSION, TamperAssessment),
    ("claims_extract", CLAIMS_PROMPT_VERSION, ClaimsExtraction),
    ("policy_decide", POLICY_PROMPT_VERSION, PolicyAnswer),
    ("orchestrator_justify", "v2", JustificationDraft),
)


def _prompt_loader(prompt_name: str) -> PromptLoader:
    directory_by_prompt = {
        "classifier": "packages/agents/prompts",
        "orchestrator_justify": "packages/agents/prompts",
        "ocr": "packages/agents/ocr/prompts",
        "kyc_tamper": "packages/agents/kyc/prompts",
        "claims_extract": "packages/agents/claims/prompts",
        "policy_decide": "packages/agents/policy/prompts",
    }
    return PromptLoader(ROOT / directory_by_prompt[prompt_name])


def _example(prompt_name: str, version: str) -> dict[str, Any]:
    prompt = _prompt_loader(prompt_name).load(prompt_name, version)
    match = re.search(r"```json\s*(.*?)\s*```", prompt.system, flags=re.DOTALL | re.IGNORECASE)
    assert match is not None, f"{prompt_name}.{version} needs a fenced JSON schema example"
    value = json.loads(match.group(1))
    assert isinstance(value, dict)
    return value


@pytest.mark.parametrize(("prompt_name", "version", "schema"), PROMPT_CASES)
def test_prompt_json_example_validates_against_output_schema(
    prompt_name: str,
    version: str,
    schema: type,
) -> None:
    schema.model_validate(_example(prompt_name, version))


@pytest.mark.parametrize(("prompt_name", "version", "schema"), PROMPT_CASES)
def test_llm_output_schema_ignores_and_warns_unknown_provider_fields(
    prompt_name: str,
    version: str,
    schema: type,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from packages.core import llm_outputs

    warnings: list[tuple[str, tuple[object, ...]]] = []
    monkeypatch.setattr(
        llm_outputs.logger,
        "warning",
        lambda message, *args: warnings.append((message, args)),
    )
    payload = {**_example(prompt_name, version), "harmless_future_field": "ignored"}

    result = schema.model_validate(payload)

    assert "harmless_future_field" not in result.model_dump()
    assert warnings
    assert "Ignoring unknown LLM output fields" in warnings[0][0]
    assert "harmless_future_field" in warnings[0][1][1]
