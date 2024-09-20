from abc import ABC
from typing import Optional

from infact.common import FCDocument
from infact.tools import WebSearch
from infact.common.misc import WebSource
from infact.procedure.procedure import Procedure
from infact.prompts.prompts import PoseQuestionsPrompt, ProposeQueries, AnswerQuestion
from infact.utils.console import light_blue


class QABased(Procedure, ABC):
    """Base class for all procedures that apply a questions & answers (Q&A) strategy."""

    def _pose_questions(self, no_of_questions: int, doc: FCDocument) -> list[str]:
        """Generates some questions that needs to be answered during the fact-check."""
        prompt = PoseQuestionsPrompt(doc, n_questions=no_of_questions)
        response = self.llm.generate(prompt)
        if response is None:
            return []
        else:
            return response["questions"]

    def approach_question_batch(self, questions: list[str], doc: FCDocument) -> list:
        """Tries to answer the given list of questions. Unanswerable questions are dropped."""
        # Answer each question, one after another
        q_and_a = []
        for question in questions:
            qa_instance = self.approach_question(question, doc)
            if qa_instance is not None:
                q_and_a.append(qa_instance)

        # Add Q&A to doc reasoning
        q_and_a_strings = [(f"### {triplet['question']}\n"
                            f"Answer: {triplet['answer']}\n\n"
                            f"Source URL: {triplet['url']}") for triplet in q_and_a]
        q_and_a_string = "## Initial Q&A\n" + "\n\n".join(q_and_a_strings)
        doc.add_reasoning(q_and_a_string)

        return q_and_a

    def propose_queries_for_question(self, question: str, doc: FCDocument) -> list[WebSearch]:
        prompt = ProposeQueries(question, doc)

        n_attempts = 0
        while n_attempts < self.max_attempts:
            n_attempts += 1
            response = self.llm.generate(prompt)

            if response is None:
                continue

            queries: list = response["queries"]

            if len(queries) > 0:
                return queries

            self.logger.log("No new actions were found. Retrying...")

        self.logger.warning("Got no search query, dropping this question.")
        return []

    def approach_question(self, question: str, doc: FCDocument = None) -> Optional[dict]:
        """Tries to answer the given question. If unanswerable, returns None."""
        self.logger.log(light_blue(f"Answering question: {question}"))
        self.actor.reset()

        # Stage 3: Generate search queries
        queries = self.propose_queries_for_question(question, doc)
        if len(queries) == 0:
            return None

        # Execute searches and gather all results
        search_results = self.retrieve_resources(queries)

        # Step 4: Answer generation
        if len(search_results) > 0:
            return self.generate_answer(question, search_results, doc)

    def answer_question(self,
                        question: str,
                        results: list[WebSource],
                        doc: FCDocument = None) -> (str, WebSource):
        """Answers the given question and returns the answer along with the ID of the most relevant result."""
        answer, relevant_result = self.answer_question_individually(question, results, doc)
        return answer, relevant_result

    def generate_answer(self, question: str, results: list[WebSource], doc: FCDocument) -> Optional[dict]:
        answer, relevant_result = self.answer_question(question, results, doc)

        if answer is not None:
            self.logger.log(f"Got answer: {answer}")
            qa_instance = {"question": question,
                           "answer": answer,
                           "url": relevant_result.url,
                           "scraped_text": relevant_result.text}
            return qa_instance
        else:
            self.logger.log("Got no answer.")

    def answer_question_individually(
            self,
            question: str,
            results: list[WebSource],
            doc: FCDocument
    ) -> (Optional[str], Optional[WebSource]):
        """Generates an answer to the given question by iterating over the search results
        and using them individually to answer the question."""
        for result in results:
            answer = self.attempt_answer_question(question, result, doc)
            if answer is not None:
                return answer, result
        return None, None

    def attempt_answer_question(self, question: str, result: WebSource, doc: FCDocument) -> Optional[str]:
        """Generates an answer to the given question."""
        prompt = AnswerQuestion(question, result, doc)
        out = self.llm.generate(prompt, max_attempts=3)
        if out is not None and out["answered"]:
            return out["answer"]
