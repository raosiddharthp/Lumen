import json

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .rating import Factors


class ResearchError(ValueError):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


class FactorsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    condition: str
    years_since_treatment: float | None = Field(default=None, ge=0, le=80)
    recurrence: bool | None = None
    surveillance_clear: bool | None = None
    systolic: int | None = Field(default=None, ge=60, le=260)
    diastolic: int | None = Field(default=None, ge=30, le=160)
    medications: int | None = Field(default=None, ge=0, le=20)
    stress_test_normal: bool | None = None
    hba1c: float | None = Field(default=None, ge=3, le=20)
    complications: int | None = Field(default=None, ge=0, le=10)
    occupation: str | None = None
    sum_assured: float | None = Field(default=None, ge=0)


class ResearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factors: FactorsIn
    citations: list[str] = Field(default_factory=list)

    @field_validator("citations")
    @classmethod
    def _dedupe(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(value))

    @property
    def precedent_ids(self) -> list[str]:
        return [c for c in self.citations if c.startswith("PR-")]

    def to_factors(self) -> Factors:
        return Factors(**self.factors.model_dump(exclude_none=True))


def _strip_fences(text: str) -> str:
    body = text.strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[1] if "\n" in body else ""
        if body.rstrip().endswith("```"):
            body = body.rstrip()[:-3]
    return body.strip()


def parse_result(text: str, known_ids: set[str]) -> ResearchResult:
    try:
        data = json.loads(_strip_fences(text))
    except json.JSONDecodeError as exc:
        raise ResearchError("NOT_JSON", str(exc)[:100])
    try:
        result = ResearchResult.model_validate(data)
    except ValidationError as exc:
        raise ResearchError("SCHEMA", str(exc)[:200])
    unknown = [c for c in result.citations if c not in known_ids]
    if unknown:
        raise ResearchError("UNKNOWN_CITATION", ", ".join(unknown))
    return result
