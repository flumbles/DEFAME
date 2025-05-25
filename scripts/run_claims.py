"""Minimal running example for a multimodal fact-check."""

from ezmm import Image

from defame.fact_checker import FactChecker, RateLimitedFactChecker
'''
fact_checker = RateLimitedFactChecker(llm="gpt_4o", tools_config={
        "searcher": None,  # default
        "geolocator": None  # default
    })'''

fact_checker = FactChecker(llm="llava_next")
'''claim = ["The image",
         Image("in/example/sahara.webp"),
         "shows the Sahara snowing!"]
report, _ = fact_checker.verify_claim(claim)
report.save_to("out/fact-check")'''

claim = ["The Sahara desert gets snow every winter."]
report, meta = fact_checker.verify_claim(claim)
print(f"✅ Result: {report.verdict}")
print(f"📝 Justification: {report.justification}")
