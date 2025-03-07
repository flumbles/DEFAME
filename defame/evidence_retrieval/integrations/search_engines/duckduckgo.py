import time
from typing import List, Dict, Optional

from duckduckgo_search import DDGS

from defame.common import logger, MultimediaSnippet
from defame.evidence_retrieval.integrations.search_engines.common import Query, WebSource, SearchResults
from defame.evidence_retrieval.integrations.search_engines.remote_search_api import RemoteSearchAPI


class DuckDuckGo(RemoteSearchAPI):
    """Class for querying the DuckDuckGo API.
    TODO: Solve the rate limit problem."""
    name = "duckduckgo"

    def __init__(self,
                 max_retries: int = 10,
                 backoff_factor: float = 60.0,
                 **kwargs):
        super().__init__(**kwargs)
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.total_searches = 0

    def _call_api(self, query: Query) -> Optional[SearchResults]:
        """Run a search query and return structured results."""
        assert query.has_text() and not query.has_image(), "DuckDuckGo only supports text queries."
        # TODO: Implement start and end date
        attempt = 0
        while attempt < self.max_retries:
            if attempt > 3:
                wait_time = self.backoff_factor * attempt
                logger.warning(f"Sleeping {wait_time} seconds.")
                time.sleep(wait_time)
            try:
                self.total_searches += 1
                response = DDGS().text(query.text, max_results=query.limit)
                if not response:
                    logger.warning("DuckDuckGo is having issues. Run duckduckgo.py "
                                        "and check https://duckduckgo.com/ for more information.")
                    return None
                return SearchResults(sources=self._parse_results(response), query=query)
            except Exception as e:
                attempt += 1
                logger.log(f"DuckDuckGo search attempt {attempt} failed: {e}. Retrying with modified query...")
        logger.warning("All attempts to reach DuckDuckGo have failed. Please try again later.")

    def _parse_results(self, response: List[Dict[str, str]]) -> list[WebSource]:
        """Parse results from DuckDuckGo search and return structured dictionary."""
        results = []
        for i, result in enumerate(response):
            url = result.get('href', '')
            title = result.get('title', '')
            content = MultimediaSnippet(result.get('body', ''))

            results.append(WebSource(reference=url, title=title, content=content))
        return results
