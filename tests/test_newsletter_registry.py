from __future__ import annotations

from ingest.registry import load_sources


def test_newsletter_sources_have_source_type_and_credibility(tmp_path) -> None:
    src = tmp_path / "sources.yaml"
    src.write_text(
        """
- id: lennys_newsletter
  name: "Lenny's Newsletter"
  type: html_list
  url: "https://www.lennysnewsletter.com/"
  priority_weight: 0.8
  signal_type: ecosystem
  source_type: pm_newsletter
  credibility: high
""",
        encoding="utf-8",
    )
    sources = load_sources(src)
    assert sources[0].source_type == "pm_newsletter"
    assert sources[0].credibility == "high"
