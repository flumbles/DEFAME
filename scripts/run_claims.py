"""Minimal running example for a multimodal fact-check."""

from ezmm import Image

from defame.fact_checker import FactChecker, RateLimitedFactChecker

fact_checker = RateLimitedFactChecker(llm="gpt_4o", tools_config={
        "searcher": None,  # default
        "geolocator": None  # default
    })
claim = ["The image",
         Image("in/example/Sahara.webp"),
         "shows the Sahara snowing!"]
report, _ = fact_checker.verify_claim_with_rate_limit(claim)
report.save_to("out/fact-check")
