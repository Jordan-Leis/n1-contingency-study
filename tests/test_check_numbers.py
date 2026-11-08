from n1study.check_numbers import check


def test_flags_a_number_not_in_results(tmp_path):
    doc = tmp_path / "doc.md"
    doc.write_text("Worst overload 157.7% (sourced). Made up: 123.4% and 9,876 MW.\n```\n999.9 in code is ignored\n```")
    assert [t for _, t in check([doc])] == ["123.4", "9,876"]
