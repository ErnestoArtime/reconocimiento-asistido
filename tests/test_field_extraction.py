"""Tests de `app.services.field_extraction_service`."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models.suggestion import AiSuggestion  # noqa: E402
from app.services.field_extraction_service import (  # noqa: E402
    chunk_questions,
    extract_field,
    extract_small_batches,
)


def _fake_extractor(text, module, section, questions):
    """Extractor mock: produce 1 sugerencia por pregunta con codigo dummy."""
    return [
        AiSuggestion(
            question_id=q["id"],
            selected_codes=[f"{q['id']}-mock"],
            confidence=0.9,
            evidence=f"evidence for {q['id']}",
        )
        for q in questions
    ]


def _empty_extractor(text, module, section, questions):
    return []


def _q(qid: str) -> dict:
    return {
        "id": qid,
        "text": f"Pregunta {qid}",
        "question_type": "yesno",
        "codes": {f"{qid}-1": "Si", f"{qid}-2": "No"},
        "section": "TEST",
    }


class ChunkQuestionsTest(unittest.TestCase):
    def test_chunks_exact(self) -> None:
        qs = [_q(f"Q{i}") for i in range(6)]
        chunks = chunk_questions(qs, batch_size=2)
        self.assertEqual(len(chunks), 3)
        self.assertEqual([len(c) for c in chunks], [2, 2, 2])

    def test_chunks_with_remainder(self) -> None:
        qs = [_q(f"Q{i}") for i in range(7)]
        chunks = chunk_questions(qs, batch_size=3)
        self.assertEqual([len(c) for c in chunks], [3, 3, 1])

    def test_batch_size_one(self) -> None:
        qs = [_q("A"), _q("B")]
        chunks = chunk_questions(qs, batch_size=1)
        self.assertEqual(chunks, [[qs[0]], [qs[1]]])

    def test_empty_returns_empty(self) -> None:
        self.assertEqual(chunk_questions([], batch_size=5), [])

    def test_batch_size_zero_raises(self) -> None:
        with self.assertRaises(ValueError):
            chunk_questions([_q("X")], batch_size=0)

    def test_batch_size_larger_than_input(self) -> None:
        qs = [_q("A"), _q("B")]
        chunks = chunk_questions(qs, batch_size=10)
        self.assertEqual(chunks, [qs])


class ExtractFieldTest(unittest.TestCase):
    def test_single_question_calls_extractor_with_one_question(self) -> None:
        captured = {}

        def capturing(text, module, section, questions):
            captured["n"] = len(questions)
            captured["qid"] = questions[0]["id"]
            return []

        extract_field(
            text="hola",
            module="exam",
            section="TEST",
            question=_q("E1-3"),
            extractor=capturing,
        )
        self.assertEqual(captured["n"], 1)
        self.assertEqual(captured["qid"], "E1-3")

    def test_returns_extractor_output(self) -> None:
        result = extract_field(
            text="hola",
            module="exam",
            section="TEST",
            question=_q("E1-3"),
            extractor=_fake_extractor,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].question_id, "E1-3")


class ExtractSmallBatchesTest(unittest.TestCase):
    def test_processes_all_questions(self) -> None:
        qs = [_q(f"Q{i}") for i in range(5)]
        result = extract_small_batches(
            text="x",
            module="exam",
            section="TEST",
            questions=qs,
            batch_size=2,
            extractor=_fake_extractor,
        )
        ids = sorted(s.question_id for s in result)
        self.assertEqual(ids, [f"Q{i}" for i in range(5)])

    def test_batches_called_correctly(self) -> None:
        call_log = []

        def logging_extractor(text, module, section, questions):
            call_log.append([q["id"] for q in questions])
            return _fake_extractor(text, module, section, questions)

        qs = [_q(f"Q{i}") for i in range(7)]
        extract_small_batches(
            text="x",
            module="exam",
            section="TEST",
            questions=qs,
            batch_size=3,
            extractor=logging_extractor,
        )
        self.assertEqual(len(call_log), 3)
        self.assertEqual([len(b) for b in call_log], [3, 3, 1])

    def test_merge_preserves_first_occurrence(self) -> None:
        """Si batch posterior duplica question_id, prevalece el primero."""
        qs = [_q("A"), _q("B")]

        def first_call_only(text, module, section, questions):
            # Devuelve mock con codigo distinto segun llamada
            return [
                AiSuggestion(
                    question_id=q["id"],
                    selected_codes=[f"{q['id']}-batch1"],
                    confidence=0.9,
                    evidence="batch1",
                )
                for q in questions
            ]

        result = extract_small_batches(
            text="x",
            module="exam",
            section="TEST",
            questions=qs,
            batch_size=1,
            extractor=first_call_only,
        )
        # cada pregunta procesada en su propio batch, sin overlap
        self.assertEqual(len(result), 2)

    def test_empty_questions_returns_empty(self) -> None:
        result = extract_small_batches(
            text="x",
            module="exam",
            section="TEST",
            questions=[],
            batch_size=3,
            extractor=_fake_extractor,
        )
        self.assertEqual(result, [])

    def test_empty_extractor_returns_empty(self) -> None:
        qs = [_q("A"), _q("B")]
        result = extract_small_batches(
            text="x",
            module="exam",
            section="TEST",
            questions=qs,
            batch_size=2,
            extractor=_empty_extractor,
        )
        self.assertEqual(result, [])

    def test_batch_size_zero_raises(self) -> None:
        qs = [_q("A")]
        with self.assertRaises(ValueError):
            extract_small_batches(
                text="x",
                module="exam",
                section="TEST",
                questions=qs,
                batch_size=0,
                extractor=_fake_extractor,
            )


if __name__ == "__main__":
    unittest.main()
