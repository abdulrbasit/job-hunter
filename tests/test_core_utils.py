from job_hunter.core.utils import (
    has_excluded_title_term,
    strip_html,
    title_is_allowed,
    title_matches_any_role,
)


def test_strip_html_removes_script_style_and_decodes_entities() -> None:
    html = """
    <html>
      <style>.hidden { display: none; }</style>
      <script>alert("x")</script>
      <body><h1>Product&nbsp;Manager</h1><p>Roadmap &amp; discovery&mdash;work.</p></body>
    </html>
    """

    assert strip_html(html) == "Product Manager Roadmap & discovery\u2014work."


# ---------------------------------------------------------------------------
# title_matches_any_role
# ---------------------------------------------------------------------------


def test_title_matches_any_role_true_for_matching_role() -> None:
    assert title_matches_any_role("Senior Product Manager", ["Product Manager"]) is True


def test_title_matches_any_role_false_for_no_role_list_match() -> None:
    assert title_matches_any_role("Data Scientist", ["Product Manager"]) is False


def test_title_matches_any_role_true_when_job_titles_empty() -> None:
    assert title_matches_any_role("Anything", []) is True


def test_title_matches_any_role_false_for_empty_title() -> None:
    assert title_matches_any_role("", ["Product Manager"]) is False


# ---------------------------------------------------------------------------
# has_excluded_title_term \u2014 order independence is the whole point of this helper
# ---------------------------------------------------------------------------


def test_has_excluded_title_term_matches_regardless_of_word_order() -> None:
    assert has_excluded_title_term("Senior Product Manager", ["senior"]) is True
    assert has_excluded_title_term("Product Manager Senior", ["senior"]) is True
    assert has_excluded_title_term("Product Manager Intern", ["intern"]) is True
    assert has_excluded_title_term("Intern Product Manager", ["intern"]) is True
    assert has_excluded_title_term("Product Owner Working Student", ["working student"]) is True
    assert has_excluded_title_term("Working Student Product Owner", ["working student"]) is True


def test_has_excluded_title_term_uses_word_boundaries() -> None:
    # "staff" must not match inside "staffing"
    assert has_excluded_title_term("Staffing Product Manager", ["staff"]) is False


def test_has_excluded_title_term_false_when_no_terms() -> None:
    assert has_excluded_title_term("Product Manager", []) is False
    assert has_excluded_title_term("Product Manager", None) is False


# ---------------------------------------------------------------------------
# title_is_allowed \u2014 role match AND no excluded term, word-order independent
# ---------------------------------------------------------------------------


def test_title_is_allowed_rejects_excluded_term_after_role() -> None:
    # This is the bug this helper fixes: the old title_matches only rejected
    # exclusions found *before* the matched role.
    assert title_is_allowed("Product Manager Intern", ["Product Manager"], ["intern"]) is False


def test_title_is_allowed_rejects_excluded_term_before_role() -> None:
    assert title_is_allowed("Intern Product Manager", ["Product Manager"], ["intern"]) is False


def test_title_is_allowed_accepts_role_without_excluded_term() -> None:
    assert title_is_allowed("Senior Product Manager", ["Product Manager"], ["intern"]) is True


def test_title_is_allowed_multi_word_excluded_term_both_orders() -> None:
    assert title_is_allowed("Product Owner Working Student", ["Product Owner"], ["working student"]) is False
    assert title_is_allowed("Working Student Product Owner", ["Product Owner"], ["working student"]) is False


def test_title_is_allowed_false_when_role_does_not_match() -> None:
    assert title_is_allowed("Data Scientist", ["Product Manager"], ["intern"]) is False
