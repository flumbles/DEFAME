from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional

from defame.common import Results, Image, MultimediaSnippet


class SearchMode(Enum):
    SEARCH = "search"
    NEWS = "news"
    PLACES = "places"
    IMAGES = "images"
    REVERSE = "reverse"  # Reverse Image Search (RIS)


@dataclass(frozen=True)
class Query:
    text: Optional[str] = None
    image: Optional[Image] = None
    limit: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    search_mode: Optional[SearchMode] = None

    def __post_init__(self):
        assert self.text or self.image, "Query must have at least one of 'text' or 'image'."

    def has_text(self) -> bool:
        return self.text is not None

    def has_image(self) -> bool:
        return self.image is not None

    def __eq__(self, other):
        return isinstance(other, Query) and (
            self.text == other.text and
            self.image == other.image and
            self.limit == other.limit and
            self.start_date == other.start_date and
            self.end_date == other.end_date and
            self.search_mode == other.search_mode
        )

    def __hash__(self):
        return hash((
            self.text,
            self.image,
            self.limit,
            self.start_date,
            self.end_date,
            self.search_mode,
        ))


@dataclass
class Source:
    """A source of information. For example, a web page or an excerpt
     of a local knowledge base. Each source must be clearly identifiable
     (and ideally also retrievable) by its reference."""
    reference: str  # e.g. URL
    content: MultimediaSnippet = None  # the contained raw information, may require lazy scrape
    takeaways: MultimediaSnippet = None  # an optional summary of the content's relevant info

    def is_loaded(self) -> bool:
        return self.content is not None

    def is_relevant(self) -> Optional[bool]:
        """Returns True if the summary contains information helpful for the fact-check."""
        if self.takeaways is None:
            return None
        elif self.takeaways.data == "":
            return False
        else:
            return "NONE" not in self.takeaways.data

    def _get_content_str(self):
        if self.is_relevant():
            return f"Takeaways: {self.takeaways.data}"
        elif self.is_loaded():
            return f"Content: {self.content.data}"
        else:
            return "⚠️ Content not yet loaded."

    def __str__(self):
        """Uses the summary if available, otherwise the raw content."""
        text = f"Source {self.reference}\n"
        return text + self._get_content_str()

    def __eq__(self, other):
        return isinstance(other, Source) and self.reference == other.reference

    def __hash__(self):
        return hash(self.reference)

    def __repr__(self):
        return f"Source(reference='{self.reference}')"


@dataclass
class WebSource(Source):
    """Any web page."""
    title: str = None
    release_date: date = None
    preview: str = None

    @property
    def url(self) -> str:
        return self.reference

    def __str__(self):
        text = f"Web Source {self.url}\n"
        if self.title is not None:
            text += f"Title: {self.title}\n"
        if self.release_date is not None:
            text += f"Release Date: {self.release_date.strftime('%B %d, %Y')}\n"
        if self.preview is not None:
            text += f"{self.preview}\n"
        return text + self._get_content_str()

    def __repr__(self):
        return f"WebSource(url='{self.url}')"

    def __eq__(self, other):
        """Needed because @dataclass overrides __eq__()."""
        return isinstance(other, WebSource) and self.url == other.url

    def __hash__(self):
        """Needed because @dataclass overrides __hash__()."""
        return hash(self.url)


@dataclass
class SearchResults(Results):
    """A list of sources."""
    sources: list[Source]
    query: Query  # the query that resulted in these sources

    @property
    def n_sources(self):
        return len(self.sources)

    def __str__(self):
        if self.n_sources == 0:
            return "No search results found."
        else:
            return "**Search Results**\n\n" + "\n\n".join(map(str, self.sources))

    def __repr__(self):
        return f"SearchResults(n_sources={len(self.sources)}, sources={self.sources})"
