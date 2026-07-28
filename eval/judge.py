"""Optional, evaluation-only Groq judge for generated RAG answers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = PROJECT_ROOT / ".csrs_cache" / "eval" / "judge"
PROMPT_PATH = Path(__file__).with_name("prompts") / "judge_v1.txt"
PROMPT_VERSION = "judge_v1"
PROVIDER = "groq"
MODEL = "openai/gpt-oss-120b"
MAX_COMPLETION_TOKENS = 1_200


class JudgeError(Exception):
    """Base class for visible judge failures."""


class JudgeConfigurationError(JudgeError):
    """The judge cannot start because local configuration is incomplete."""


class JudgeResponseError(JudgeError):
    """Groq returned output that did not satisfy the judgment schema."""


class GroqJudgeSettings(BaseSettings):
    """Evaluation-only credentials loaded from the repository root environment."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_key: SecretStr | None = Field(default=None, validation_alias="GROQ_API_KEY")


class ScoredCriterion(BaseModel):
    """One rubric score with a concise, evidence-based explanation."""

    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=0, le=4)
    justification: str = Field(min_length=1)


class CompletenessCriterion(ScoredCriterion):
    """Coverage judgment with the IDs of omitted required claims."""

    missing_claim_ids: list[str]


class FaithfulnessCriterion(ScoredCriterion):
    """Evidence-grounding judgment with auditable failure descriptions."""

    unsupported_claims: list[str]
    contradicted_claims: list[str]


class JudgeJudgment(BaseModel):
    """Strict structured output produced by the fixed Groq judge."""

    model_config = ConfigDict(extra="forbid")

    correctness: ScoredCriterion
    completeness: CompletenessCriterion
    faithfulness: FaithfulnessCriterion
    relevance: ScoredCriterion
    verdict: Literal["pass", "partial", "fail"]


class CachedJudgeRecord(BaseModel):
    """Validated cache representation of one successful judgment."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    provider: Literal["groq"]
    model: Literal["openai/gpt-oss-120b"]
    prompt_version: Literal["judge_v1"]
    prompt_hash: str
    cache_key: str
    judgment: JudgeJudgment
    raw_response: str


class JudgeResult(BaseModel):
    """Auditable judge result returned to the evaluation runner."""

    model_config = ConfigDict(extra="forbid")

    provider: Literal["groq"]
    model: Literal["openai/gpt-oss-120b"]
    prompt_version: Literal["judge_v1"]
    prompt_hash: str
    cache_key: str
    cached: bool
    judgment: JudgeJudgment
    raw_response: str


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as error:
        raise ValueError("judge inputs must be JSON serializable") from error


def make_cache_key(
    *,
    question_id: str,
    candidate_answer: str,
    retrieved_context: list[dict[str, object]],
    prompt_hash: str,
) -> str:
    """Build a stable key from the answer, actual context, and judge contract."""
    if not question_id.strip():
        raise ValueError("question_id must not be empty")
    if not candidate_answer.strip():
        raise ValueError("candidate_answer must not be empty")

    key_data = {
        "question_id": question_id,
        "candidate_answer_hash": _sha256_text(candidate_answer),
        "retrieved_context_hash": _sha256_text(_canonical_json(retrieved_context)),
        "judge_model": MODEL,
        "prompt_version": PROMPT_VERSION,
        "prompt_hash": prompt_hash,
    }
    return _sha256_text(_canonical_json(key_data))


def load_judge_settings(env_file: Path | None = None) -> GroqJudgeSettings:
    """Load the Groq key without exposing its value in logs or result records."""
    if env_file is None:
        return GroqJudgeSettings()
    return GroqJudgeSettings(_env_file=env_file)


class GroqJudge:
    """One fixed Groq judge with strict output validation and local caching."""

    def __init__(
        self,
        client: Any | None = None,
        *,
        no_cache: bool = False,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        prompt_path: Path = PROMPT_PATH,
        env_file: Path | None = None,
    ) -> None:
        self._client = client if client is not None else self._client_from_env(env_file)
        self._no_cache = no_cache
        self._cache_dir = cache_dir
        try:
            self._system_prompt = prompt_path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeError) as error:
            raise JudgeConfigurationError(f"could not read judge prompt: {error}") from error
        if not self._system_prompt:
            raise JudgeConfigurationError("judge prompt must not be empty")
        self.prompt_hash = _sha256_text(self._system_prompt)

    @classmethod
    def from_env(
        cls,
        *,
        no_cache: bool = False,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        prompt_path: Path = PROMPT_PATH,
        env_file: Path | None = None,
    ) -> GroqJudge:
        """Create the judge only when an evaluation command explicitly requests it."""
        return cls(
            no_cache=no_cache,
            cache_dir=cache_dir,
            prompt_path=prompt_path,
            env_file=env_file,
        )

    @staticmethod
    def _client_from_env(env_file: Path | None) -> Any:
        settings = load_judge_settings(env_file)
        if settings.api_key is None or not settings.api_key.get_secret_value().strip():
            raise JudgeConfigurationError(
                "GROQ_API_KEY is required when Groq judge evaluation is enabled"
            )
        try:
            from groq import Groq
        except ImportError as error:
            raise JudgeConfigurationError(
                "Groq evaluation dependency is missing; install the eval dependency group"
            ) from error
        return Groq(api_key=settings.api_key.get_secret_value())

    def evaluate(
        self,
        question_id: str,
        question: str,
        candidate_answer: str,
        reference_answer: str,
        gold_claims: list[dict[str, object]],
        gold_evidence: list[dict[str, object]],
        retrieved_context: list[dict[str, object]],
    ) -> dict[str, object]:
        """Return the runner-facing, JSON-serializable judgment record."""
        result = self.judge(
            question_id=question_id,
            question=question,
            candidate_answer=candidate_answer,
            reference_answer=reference_answer,
            gold_claims=gold_claims,
            gold_evidence=gold_evidence,
            retrieved_context=retrieved_context,
        )
        output = result.model_dump(mode="json")
        output["cache_hit"] = output.pop("cached")
        return output

    def judge(
        self,
        *,
        question_id: str,
        question: str,
        candidate_answer: str,
        reference_answer: str,
        gold_claims: list[dict[str, object]],
        gold_evidence: list[dict[str, object]],
        retrieved_context: list[dict[str, object]],
        bypass_cache: bool | None = None,
    ) -> JudgeResult:
        """Judge one answer, using a successful cached judgment when available."""
        self._validate_inputs(
            question=question,
            candidate_answer=candidate_answer,
            reference_answer=reference_answer,
            gold_claims=gold_claims,
            gold_evidence=gold_evidence,
            retrieved_context=retrieved_context,
        )
        cache_key = make_cache_key(
            question_id=question_id,
            candidate_answer=candidate_answer,
            retrieved_context=retrieved_context,
            prompt_hash=self.prompt_hash,
        )
        cache_is_bypassed = self._no_cache if bypass_cache is None else bypass_cache
        if not cache_is_bypassed:
            cached = self._read_cache(cache_key)
            if cached is not None:
                return self._result_from_record(cached, cached=True)

        payload = {
            "question": question,
            "candidate_answer": candidate_answer,
            "reference_answer": reference_answer,
            "gold_claims": gold_claims,
            "gold_evidence": gold_evidence,
            "retrieved_context": retrieved_context,
        }
        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": _canonical_json(payload)},
        ]
        raw_response = self._request(messages)
        try:
            judgment = self._parse_judgment(raw_response)
        except JudgeResponseError as first_error:
            repair_messages = [
                *messages,
                {"role": "assistant", "content": raw_response[:8_000]},
                {
                    "role": "user",
                    "content": (
                        "The previous response was invalid. Return only a corrected JSON "
                        "object that satisfies the supplied schema."
                    ),
                },
            ]
            repaired_response = self._request(repair_messages)
            try:
                judgment = self._parse_judgment(repaired_response)
            except JudgeResponseError as second_error:
                raise JudgeResponseError(
                    "Groq judge returned invalid structured output after one repair retry: "
                    f"{second_error}"
                ) from first_error
            raw_response = repaired_response

        record = CachedJudgeRecord(
            schema_version=1,
            provider=PROVIDER,
            model=MODEL,
            prompt_version=PROMPT_VERSION,
            prompt_hash=self.prompt_hash,
            cache_key=cache_key,
            judgment=judgment,
            raw_response=raw_response,
        )
        if not cache_is_bypassed:
            self._write_cache(record)
        return self._result_from_record(record, cached=False)

    def _request(self, messages: list[dict[str, str]]) -> str:
        response = self._client.chat.completions.create(
            model=MODEL,
            messages=messages,
            temperature=0,
            reasoning_effort="low",
            include_reasoning=False,
            max_completion_tokens=MAX_COMPLETION_TOKENS,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "rag_answer_judgment",
                    "strict": True,
                    "schema": JudgeJudgment.model_json_schema(),
                },
            },
        )
        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError, TypeError) as error:
            raise JudgeResponseError(
                "Groq judge response did not contain message content"
            ) from error
        if not isinstance(content, str) or not content.strip():
            raise JudgeResponseError("Groq judge response content was empty")
        return content

    @staticmethod
    def _parse_judgment(raw_response: str) -> JudgeJudgment:
        try:
            return JudgeJudgment.model_validate_json(raw_response)
        except ValidationError as error:
            raise JudgeResponseError(f"structured judgment failed validation: {error}") from error

    @staticmethod
    def _validate_inputs(
        *,
        question: str,
        candidate_answer: str,
        reference_answer: str,
        gold_claims: list[dict[str, object]],
        gold_evidence: list[dict[str, object]],
        retrieved_context: list[dict[str, object]],
    ) -> None:
        if not question.strip():
            raise ValueError("question must not be empty")
        if not candidate_answer.strip():
            raise ValueError("candidate_answer must not be empty")
        if not reference_answer.strip():
            raise ValueError("reference_answer must not be empty")
        if not gold_claims:
            raise ValueError("gold_claims must not be empty")
        if not gold_evidence:
            raise ValueError("gold_evidence must not be empty")
        _canonical_json(gold_claims)
        _canonical_json(gold_evidence)
        _canonical_json(retrieved_context)

    def _read_cache(self, cache_key: str) -> CachedJudgeRecord | None:
        path = self._cache_dir / f"{cache_key}.json"
        if not path.exists():
            return None
        try:
            record = CachedJudgeRecord.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValidationError) as error:
            raise JudgeResponseError(f"judge cache entry is invalid: {path}: {error}") from error
        if record.cache_key != cache_key or record.prompt_hash != self.prompt_hash:
            raise JudgeResponseError(f"judge cache entry metadata does not match: {path}")
        return record

    def _write_cache(self, record: CachedJudgeRecord) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        path = self._cache_dir / f"{record.cache_key}.json"
        temporary_path = path.with_suffix(".tmp")
        temporary_path.write_text(
            record.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(path)

    @staticmethod
    def _result_from_record(record: CachedJudgeRecord, *, cached: bool) -> JudgeResult:
        return JudgeResult(
            provider=record.provider,
            model=record.model,
            prompt_version=record.prompt_version,
            prompt_hash=record.prompt_hash,
            cache_key=record.cache_key,
            cached=cached,
            judgment=record.judgment,
            raw_response=record.raw_response,
        )
