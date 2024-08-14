from src.common.document import FCDocument
from src.common.modeling import LLM
from src.common.logger import Logger
from src.prompts.prompt import SummarizeDocPrompt


class DocSummarizer:
    """Summarizes a given, finished fact-checking document. The resulting summary is
    equivalent to the justification of the verdict."""

    def __init__(self, llm: LLM, logger: Logger):
        self.llm = llm
        self.logger = logger

    def summarize(self, doc: FCDocument) -> str:
        summarize_doc_prompt = SummarizeDocPrompt(doc)
        summary = self.llm.generate(str(summarize_doc_prompt))
        return summary
