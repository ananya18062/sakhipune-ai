"""Offline validation for the non-production resource CSV repair candidate."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
import unittest
from pathlib import Path


REPAIR_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = REPAIR_DIR.parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
ORIGINAL_CSV = BACKEND_DIR / "app" / "data" / "resources.csv"
CANDIDATE_CSV = REPAIR_DIR / "resources_repaired_candidate.csv"
MAPPING_CSV = REPAIR_DIR / "csv_row_mapping_report.csv"
AMBIGUOUS_CSV = REPAIR_DIR / "csv_ambiguous_rows.csv"

EXPECTED_HEADER = [
    "name",
    "category",
    "description",
    "location",
    "contact",
    "language",
    "keywords",
    "experience_level",
    "work_mode",
    "employment_type",
]
ORIGINAL_SHA256 = "24b6d4be6501e2b86c0491c755d58b4d43386fdb011342c305d6261341d8ecfd"

EXPERIENCE_LEVELS = {
    "",
    "fresher",
    "less_than_1",
    "1_2_years",
    "3_5_years",
    "6_10_years",
    "more_than_10",
    "any",
}
WORK_MODES = {"", "remote", "hybrid", "on_site"}
EMPLOYMENT_TYPES = {
    "",
    "full_time",
    "part_time",
    "contract",
    "apprenticeship",
    "self_employment",
}
LANGUAGES = {"en", "hi", "mr"}


def read_dicts(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


class ResourceCSVCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(BACKEND_DIR))
        from app.database.models import SupportResource

        cls.model = SupportResource

    def test_candidate_header_and_all_rows_have_ten_fields(self) -> None:
        with CANDIDATE_CSV.open(encoding="utf-8", newline="") as source:
            rows = list(csv.reader(source))
        self.assertEqual(rows[0], EXPECTED_HEADER)
        self.assertEqual(len(rows) - 1, 46)
        self.assertTrue(all(len(row) == len(EXPECTED_HEADER) for row in rows[1:]))

    def test_candidate_round_trips_commas_quotes_and_newlines(self) -> None:
        original = {
            "name": 'Resource, "quoted"',
            "category": "Education",
            "description": "First line,\nsecond line with \"quotes\"",
            "location": "",
            "contact": "https://example.invalid/path?a=1,b=2",
            "language": "en",
            "keywords": "career,education,student",
            "experience_level": "",
            "work_mode": "",
            "employment_type": "",
        }
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=EXPECTED_HEADER)
        writer.writeheader()
        writer.writerow(original)
        buffer.seek(0)
        round_tripped = list(csv.DictReader(buffer))
        self.assertEqual(round_tripped, [original])

    def test_candidate_values_match_row_mapping_and_original_fields(self) -> None:
        candidate = read_dicts(CANDIDATE_CSV)
        mapping = read_dicts(MAPPING_CSV)
        with ORIGINAL_CSV.open(encoding="utf-8-sig", newline="") as source:
            original_rows = list(csv.reader(source))

        self.assertEqual(len(candidate), len(mapping))
        self.assertEqual(len(candidate), len(original_rows) - 1)
        for index, (record, mapped) in enumerate(zip(candidate, mapping), start=1):
            self.assertEqual(mapped["original_row_number"], str(index + 1))
            self.assertEqual(mapped["candidate_status"], "Repaired")
            self.assertEqual(mapped["candidate_record_number"], str(index))
            self.assertEqual(json.loads(mapped["candidate_fields_json"]), record)
            self.assertEqual(
                json.loads(mapped["original_fields_json"]),
                original_rows[index],
            )

    def test_reconstructed_keywords_and_filter_suffixes_are_not_shifted(self) -> None:
        with ORIGINAL_CSV.open(encoding="utf-8-sig", newline="") as source:
            original_rows = list(csv.reader(source))[1:]
        candidate = read_dicts(CANDIDATE_CSV)

        for raw, record in zip(original_rows, candidate):
            self.assertEqual(record["name"], raw[0])
            self.assertEqual(record["category"], raw[1])
            self.assertEqual(record["description"], raw[2])
            self.assertEqual(record["location"], raw[3])
            self.assertEqual(record["contact"], raw[4])
            self.assertEqual(record["language"], raw[5])
            self.assertIn(record["language"], LANGUAGES)

            tail = raw[-3:]
            suffix_is_filters = (
                len(tail) == 3
                and tail[0] in EXPERIENCE_LEVELS
                and tail[1] in WORK_MODES
                and tail[2] in EMPLOYMENT_TYPES
            )
            keyword_tokens = raw[6:-3] if suffix_is_filters else raw[6:]
            expected_keywords = ",".join(keyword_tokens)
            expected_filters = tail if suffix_is_filters else ["", "", ""]
            self.assertEqual(record["keywords"], expected_keywords)
            self.assertEqual(record["experience_level"], expected_filters[0])
            self.assertEqual(record["work_mode"], expected_filters[1])
            self.assertEqual(record["employment_type"], expected_filters[2])

    def test_required_fields_types_and_model_mapping(self) -> None:
        records = read_dicts(CANDIDATE_CSV)
        model_columns = {
            column.name: column
            for column in self.model.__table__.columns
            if column.name != "id"
        }
        self.assertEqual(set(records[0]), set(model_columns))

        for record in records:
            self.assertTrue(record["name"].strip())
            self.assertTrue(record["category"].strip())
            self.assertIn(record["language"], LANGUAGES)
            self.assertIn(record["experience_level"], EXPERIENCE_LEVELS)
            self.assertIn(record["work_mode"], WORK_MODES)
            self.assertIn(record["employment_type"], EMPLOYMENT_TYPES)
            for field, column in model_columns.items():
                if column.type.length is not None:
                    self.assertLessEqual(len(record[field]), column.type.length, field)

            instance = self.model(**record)
            for field, value in record.items():
                self.assertEqual(getattr(instance, field), value)

    def test_ambiguities_are_explicit_and_original_is_unchanged(self) -> None:
        with AMBIGUOUS_CSV.open(encoding="utf-8", newline="") as source:
            ambiguities = list(csv.DictReader(source))
        mapping = read_dicts(MAPPING_CSV)
        self.assertEqual(ambiguities, [])
        self.assertEqual(len(mapping), 46)
        self.assertTrue(all(row["candidate_status"] == "Repaired" for row in mapping))
        self.assertEqual(
            hashlib.sha256(ORIGINAL_CSV.read_bytes()).hexdigest(),
            ORIGINAL_SHA256,
        )


if __name__ == "__main__":
    unittest.main()
