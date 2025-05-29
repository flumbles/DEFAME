"""Minimal running example for a multimodal fact-check."""

from ezmm import Image

from defame.fact_checker import FactChecker, RateLimitedFactChecker
'''
fact_checker = RateLimitedFactChecker(llm="gpt_4o", tools_config={
        "searcher": None,  # default
        "geolocator": None  # default
    })'''

fact_checker = FactChecker(llm="llava_next", max_iterations=3, 
                           llm_kwargs={
                            "temperature": 0.01,      # More deterministic
                            "top_p": 0.8,            # Less random sampling
                            "max_response_len": 512,  # Shorter responses
                           },
                           tools_config={
                               "searcher": {
                                   "limit_per_search": 3  # Maximum results per search query
                               }
                           })
'''claim = ["The image",
         Image("in/example/sahara.webp"),
         "shows the Sahara snowing!"]
report, _ = fact_checker.verify_claim(claim)'''

# Define the claim
claim_text = "Singapore airlines had special deals as part of SG60 celebrations."
claim = [claim_text]  # Create claim list with the text

# Verify the claim
print(f"Verifying claim: {claim_text}")
report, meta = fact_checker.verify_claim(claim)
