"""Shared types and base class for LLM backends."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class DetectionResult:
    """Outcome of running vision on a screenshot.

    `questions` is the new field — backends may extract multiple questions from
    one screenshot (e.g. a practice page with several MCQs). For backward-
    compatibility, `question` mirrors `questions[0]` when present.
    """

    has_question: bool
    question: str = ""
    questions: list[str] = field(default_factory=list)
    notes: str = ""

    def __post_init__(self) -> None:
        # Normalise — if only `question` was set, populate the list; if only
        # the list was set, populate the singular field.
        if self.questions and not self.question:
            self.question = self.questions[0]
        elif self.question and not self.questions:
            self.questions = [self.question]


@dataclass
class AnswerResult:
    answer: str
    explanation: str


class BackendError(Exception):
    """Raised by backends when an API call fails. The string form is shown to
    the user, so keep it short and human-readable."""


# -------------------------------------------------------------------- prompts
# Detection now requests up to 5 questions. We cap the list to keep responses
# small — most screenshots have one focused question; practice-PDF pages might
# have 3–5.
DETECT_SYSTEM = """\
You are a vision assistant that inspects screenshots to find quiz, exam, \
homework, or test-style questions a user might want help answering.

Respond ONLY with a single JSON object, no prose, no markdown fences. Schema:

{
  "has_question": boolean,
  "questions": [string, ...],  // up to 5 extracted questions, in order of \
prominence on the page. Empty array if has_question is false.
  "notes": string             // optional short context, e.g. "multiple choice", \
"math", "code". Empty if none.
}

Rules:
- has_question is true ONLY if the screenshot clearly contains at least one \
question the user is meant to answer (quiz, test, exercise, flashcard, MCQ, \
fill-in-the-blank, short answer, coding problem, math problem, etc).
- General UI text, chat messages, casual writing, news, social media, code \
editors without an explicit problem statement, etc. are NOT questions.
- For each extracted question: preserve the wording exactly. Include any \
answer choices verbatim, each on its own line, prefixed with their label \
(A., B., 1), etc.).
- If multiple questions are visible, include each as a separate string in \
the questions array. Maximum 5. List them in the order they appear (most \
prominent / top first).
- Output only the JSON object. No commentary."""


ANSWER_SYSTEM = """\
You are a careful expert tutor. The user will give you a single quiz or exam \
question. Reason through it step by step internally, then give a clean answer.

Output format — plain text, exactly two sections with these literal headers:

ANSWER:
<the answer itself, as concise as the question allows. For multiple choice, \
state the letter AND the full option text, e.g. "B. Mitochondria". For numeric, \
give the number with units. For short answer, give the answer phrase.>

EXPLANATION:
<a clear, friendly explanation of why this is correct. 2-6 sentences. \
If relevant, briefly say why the other options are wrong.>

Do not use markdown headers, bullets, or bold. Just the two labelled sections."""


# ------------------------------------------------------------------- base class
class Backend(ABC):
    """Provider-agnostic interface for the rest of the app to use."""

    name: str = "base"

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise ValueError("API key is required")
        self._api_key = api_key
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    @abstractmethod
    def detect_and_extract_question(self, png_bytes: bytes) -> DetectionResult:
        """Vision: decide if questions are on screen and extract them."""

    @abstractmethod
    def answer_question(self, question: str, context: str | None = None) -> AnswerResult:
        """Text: reason through and answer a single question.

        `context`, when provided, is prior conversation text the model should
        use as background (e.g. "Previous Q: …\nPrevious A: …"). Backends
        should prepend it to the user turn rather than treat it as the system
        prompt — keeps the ANSWER format contract intact.
        """

    def warmup(self) -> None:
        """Optional: preload the model so the first real call isn't cold.

        Default is a no-op (cloud backends need no warmup). Local backends
        override this to load weights + vision encoder into memory ahead of
        the user's first capture. Must never raise.
        """
        return

    def answer_questions_with_image(
        self, questions: list[str], png_bytes: bytes
    ) -> list[AnswerResult]:
        """Vision: answer already-extracted questions using the screenshot.

        Used for visually-dependent questions (charts, diagrams, geometry) where
        OCR text alone can't answer. One call answers all `questions`, in order.
        Default: unsupported.
        """
        raise NotImplementedError


def build_followup_prompt(context: str, question: str) -> str:
    """Compose the user message for a follow-up question."""
    return (
        "Earlier in this conversation:\n"
        f"{context.strip()}\n\n"
        "Follow-up question:\n"
        f"{question.strip()}"
    )


# ============================================================ shared parsers
def parse_detection_json(raw: str) -> DetectionResult:
    """Forgiving extractor — handles clean JSON, markdown-fenced JSON, JSON in
    prose, and the older single-question schema."""
    if not raw:
        return DetectionResult(has_question=False, notes="empty response")

    candidate = _strip_fences(raw)
    if not candidate.lstrip().startswith("{"):
        m = re.search(r"\{[\s\S]*\}", candidate)
        if m:
            candidate = m.group(0)

    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return DetectionResult(has_question=False, notes="parse error")

    if not isinstance(data, dict):
        # E.g. the API returned a list or a bare scalar — treat as no question.
        return DetectionResult(has_question=False, notes="unexpected JSON shape")

    has = bool(data.get("has_question", False))
    notes = str(data.get("notes", "") or "").strip()

    # Prefer the new `questions` array; fall back to legacy `question` string.
    raw_list = data.get("questions")
    questions: list[str] = []
    if isinstance(raw_list, list):
        for item in raw_list:
            if isinstance(item, str):
                t = item.strip()
                if t:
                    questions.append(t)
    elif data.get("question"):
        t = str(data["question"]).strip()
        if t:
            questions.append(t)

    # Cap at 5 to match the prompt contract.
    questions = questions[:5]

    if has and not questions:
        # Inconsistent — treat as no question.
        has = False

    return DetectionResult(has_question=has, questions=questions, notes=notes)


def parse_answer_text(raw: str) -> AnswerResult:
    """Split the ANSWER/EXPLANATION sections. Tolerant of small format drift."""
    if not raw:
        return AnswerResult(answer="(no response)", explanation="")

    m = re.search(
        r"ANSWER\s*:\s*(.+?)\n\s*EXPLANATION\s*:\s*(.+)$",
        raw,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        return AnswerResult(answer=m.group(1).strip(), explanation=m.group(2).strip())
    return AnswerResult(answer=raw.strip(), explanation="")


def _strip_fences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    return s.strip()
