"""Pure document-type routing rules for graph specialists."""

from dataclasses import dataclass

from packages.core.enums import DocType


@dataclass(frozen=True)
class Route:
    kyc: str | None
    claims: bool
    policy: bool
    fraud: bool


ROUTING_TABLE: dict[DocType, Route] = {
    DocType.CLAIM_FORM: Route(kyc="full", claims=True, policy=True, fraud=True),
    DocType.ID_DOCUMENT: Route(kyc="full", claims=False, policy=False, fraud=True),
    DocType.DISCHARGE_SUMMARY: Route(
        kyc="member_match_only", claims=True, policy=False, fraud=True
    ),
    DocType.PRESCRIPTION: Route(kyc="member_match_only", claims=True, policy=False, fraud=True),
    DocType.POLICY_AMENDMENT: Route(kyc="full", claims=False, policy=True, fraud=False),
    DocType.UNKNOWN: Route(kyc=None, claims=False, policy=False, fraud=False),
}


def route(doc_type: DocType) -> frozenset[str]:
    selection = ROUTING_TABLE[doc_type]
    return frozenset(
        name
        for name, enabled in (
            ("kyc", selection.kyc is not None),
            ("claims", selection.claims),
            ("policy", selection.policy),
            ("fraud", selection.fraud),
        )
        if enabled
    )


def classification_needs_review(doc_type: DocType, routing_tags: list[str]) -> bool:
    return doc_type == DocType.UNKNOWN or "NEEDS_REVIEW" in routing_tags
