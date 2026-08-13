"""Dataset loading and fingerprinting."""

from __future__ import annotations

import pytest

from harness.core.dataset import duplicate_case_ids, hash_cases, load_cases
from harness.core.errors import ConfigError
from harness.core.models import TestCase

JSONL = """\
{"id": "c1", "input": "what is 2+2?", "reference": "4", "tags": ["smoke"]}

{"id": "c2", "input": {"task": "book a flight"}, "extra": {"budget": 500}}
"""


def _write(tmp_path, text: str, name: str = "data.jsonl"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


class TestLoadCases:
    def test_loads_jsonl_and_skips_blank_lines(self, tmp_path):
        cases = load_cases(_write(tmp_path, JSONL))
        assert [c.id for c in cases] == ["c1", "c2"]
        assert cases[0].tags == ["smoke"]
        assert cases[1].input == {"task": "book a flight"}
        assert cases[1].extra == {"budget": 500}

    def test_malformed_line_names_the_line_number(self, tmp_path):
        broken = '{"id": "c1", "input": "ok"}\n{"id": "c2"}\n'  # no input
        with pytest.raises(ConfigError, match=r"data\.jsonl:2"):
            load_cases(_write(tmp_path, broken))

    def test_missing_file_is_a_config_error(self, tmp_path):
        with pytest.raises(ConfigError, match="Cannot read dataset"):
            load_cases(tmp_path / "nope.jsonl")

    def test_empty_dataset_is_a_config_error(self, tmp_path):
        with pytest.raises(ConfigError, match="no cases"):
            load_cases(_write(tmp_path, "\n\n"))


class TestHashCases:
    def test_hash_is_stable_across_reloads(self, tmp_path):
        path = _write(tmp_path, JSONL)
        assert hash_cases(load_cases(path)) == hash_cases(load_cases(path))

    def test_hash_ignores_formatting_but_not_content(self, tmp_path):
        reformatted = _write(
            tmp_path,
            '{"tags": ["smoke"], "reference": "4", "input": "what is 2+2?", "id": "c1"}\n'
            '{"extra": {"budget": 500}, "input": {"task": "book a flight"}, "id": "c2"}\n',
            name="reformatted.jsonl",
        )
        original = _write(tmp_path, JSONL)
        # Key order and blank lines are not drift...
        assert hash_cases(load_cases(original)) == hash_cases(load_cases(reformatted))

    def test_hash_changes_when_a_case_changes(self):
        base = [TestCase(id="c1", input="a"), TestCase(id="c2", input="b")]
        edited = [TestCase(id="c1", input="a"), TestCase(id="c2", input="B")]
        assert hash_cases(base) != hash_cases(edited)

    def test_hash_changes_when_a_case_is_dropped(self):
        base = [TestCase(id="c1", input="a"), TestCase(id="c2", input="b")]
        assert hash_cases(base) != hash_cases(base[:1])

    def test_order_is_part_of_the_identity(self):
        base = [TestCase(id="c1", input="a"), TestCase(id="c2", input="b")]
        assert hash_cases(base) != hash_cases(list(reversed(base)))

    def test_reference_and_tags_are_covered(self):
        plain = [TestCase(id="c1", input="a")]
        with_reference = [TestCase(id="c1", input="a", reference="4")]
        with_tags = [TestCase(id="c1", input="a", tags=["smoke"])]
        assert (
            len({hash_cases(plain), hash_cases(with_reference), hash_cases(with_tags)})
            == 3
        )


class TestDuplicateCaseIds:
    def test_finds_duplicates(self):
        cases = [
            TestCase(id="c1", input="a"),
            TestCase(id="c2", input="b"),
            TestCase(id="c1", input="c"),
        ]
        assert duplicate_case_ids(cases) == ["c1"]

    def test_clean_dataset_has_none(self):
        assert duplicate_case_ids([TestCase(id="c1", input="a")]) == []
