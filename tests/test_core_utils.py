from job_hunter.core.utils import (
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

    assert strip_html(html) == "Product Manager Roadmap & discovery—work."


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
# title_is_allowed — role match, word-order independent
# ---------------------------------------------------------------------------


def test_title_is_allowed_true_for_matching_role() -> None:
    assert title_is_allowed("Senior Product Manager", ["Product Manager"]) is True


def test_title_is_allowed_false_when_role_does_not_match() -> None:
    assert title_is_allowed("Data Scientist", ["Product Manager"]) is False


def test_title_is_allowed_relaxed_student_matches_on_meaningful_token_overlap() -> None:
    assert title_is_allowed("Software Engineering Intern", ["Software Engineer"], relaxed_student=True) is True
