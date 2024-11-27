from defame.common import Report, Action, logger
from defame.common.misc import WebSource
from defame.procedure.variants.qa_based.infact import InFact
from defame.prompts.prompts import ProposeQuerySimple


class SimpleQA(InFact):
    """InFact but without interpretation, uses only one query per question and takes first search result.
    (Never used in AVeriTeC challenge)."""

    def propose_queries_for_question(self, question: str, doc: Report) -> list[Action]:
        prompt = ProposeQuerySimple(question)

        n_tries = 0
        while n_tries < self.max_attempts:
            n_tries += 1
            response = self.llm.generate(prompt)

            if response is None:
                continue

            queries: list = response["queries"]

            if len(queries) > 0:
                return [queries[0]]

            logger.log("No new actions were found. Retrying...")

        logger.warning("Got no search query, dropping this question.")
        return []

    def answer_question(self,
                        question: str,
                        results: list[WebSource],
                        doc: Report = None) -> (str, WebSource):
        relevant_result = results[0]
        answer = self.attempt_answer_question(question, relevant_result, doc)
        return answer, relevant_result
