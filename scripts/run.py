"""Minimal running example for a multimodal fact-check."""

from ezmm import Image

from defame.fact_checker import FactChecker, RateLimitedFactChecker

fact_checker = RateLimitedFactChecker(
  llm="gpt_4o", 
  max_result_len=1200,
  max_iterations=3,
  tools_config={
      "searcher": {
          "limit_per_search": 4,
          "max_result_len": 2000
      },
      "geolocator": None  # default
  })
claim = ["The image",
         Image("in/example/Myanmar.png"),
         "shows the beautiful fields in Myanmar"]
report, _ = fact_checker.verify_claim_with_rate_limit(claim)
report.save_to("out/fact-check")
