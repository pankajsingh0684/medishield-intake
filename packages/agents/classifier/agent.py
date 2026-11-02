"""Vision-based document classification through the shared LLM gateway."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from packages.core.config import Settings
from packages.core.documents import render_document
from packages.core.enums import AgentStatus, DocType
from packages.core.llm.prompts import PromptLoader
from packages.core.llm.protocol import LLMGateway
from packages.core.models import Classification

CLASSIFIER_AGENT = "classifier"
CLASSIFIER_VERSION = "1.0.0"
CLASSIFIER_PROMPT_VERSION = "v1"
CLASSIFIER_MESSAGE: Mapping[str, str] = {
    "role": "user",
    "content": "Classify the supplied document image and return Classification JSON.",
}
ClassificationConfidence = Annotated[float, Field(ge=0.0, le=1.0)]


class ClassificationPrediction(BaseModel):
    """The model-generated fields before the agent adds its trusted envelope."""

    model_config = ConfigDict(extra="forbid")

    doc_type: DocType
    confidence: ClassificationConfidence
    routing_tags: list[str] = Field(default_factory=list)
    raw_response_ref: str | None = None


class ClassifierAgent:
    def __init__(
        self,
        gateway: LLMGateway,
        settings: Settings,
        *,
        prompt_loader: PromptLoader | None = None,
    ) -> None:
        self.gateway = gateway
        self.settings = settings
        self.prompt_loader = prompt_loader or PromptLoader()

    def classify(self, content: bytes, mime_type: str) -> Classification:
        started_at = datetime.now(UTC)
        model_name = self.settings.llm_vision_model
        try:
            rendered = render_document(content, mime_type)
            prompt = self.prompt_loader.load("classifier", CLASSIFIER_PROMPT_VERSION)
            model_name = prompt.resolve_model(self.settings)
            prediction = prompt.invoke(
                self.gateway,
                self.settings,
                [CLASSIFIER_MESSAGE],
                rendered.images,
                ClassificationPrediction,
            )
            routing_tags = list(prediction.routing_tags)
            needs_review = (
                prediction.doc_type == DocType.UNKNOWN
                or prediction.confidence < self.settings.threshold_classify_review
            )
            if needs_review and "NEEDS_REVIEW" not in routing_tags:
                routing_tags.append("NEEDS_REVIEW")
            return Classification(
                agent=CLASSIFIER_AGENT,
                agent_version=CLASSIFIER_VERSION,
                status=AgentStatus.OK,
                confidence=prediction.confidence,
                model=model_name,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                raw_response_ref=prediction.raw_response_ref,
                doc_type=prediction.doc_type,
                routing_tags=routing_tags,
            )
        except Exception as error:  # noqa: BLE001
            return self._error_result(started_at, model_name, error)

    @staticmethod
    def _error_result(
        started_at: datetime,
        model_name: str,
        error: Exception,
    ) -> Classification:
        return Classification(
            agent=CLASSIFIER_AGENT,
            agent_version=CLASSIFIER_VERSION,
            status=AgentStatus.ERROR,
            confidence=0.0,
            model=model_name,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            error=type(error).__name__,
            doc_type=DocType.UNKNOWN,
            routing_tags=["NEEDS_REVIEW"],
        )
