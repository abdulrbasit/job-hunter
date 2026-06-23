from job_hunter.core.utils import strip_html


def test_strip_html_removes_script_style_and_decodes_entities() -> None:
    html = """
    <html>
      <style>.hidden { display: none; }</style>
      <script>alert("x")</script>
      <body><h1>Product&nbsp;Manager</h1><p>Roadmap &amp; discovery&mdash;work.</p></body>
    </html>
    """

    assert strip_html(html) == "Product Manager Roadmap & discovery\u2014work."
