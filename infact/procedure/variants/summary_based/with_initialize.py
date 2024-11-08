from typing import Any

from infact.common import FCDocument, Label
from .dynamic import DynamicSummary
from infact.prompts.prompts import InitializePrompt


class WithInitialize(DynamicSummary):
    """Like Dynamic but with initial broadening."""
    def apply_to(self, doc: FCDocument) -> (Label, dict[str, Any]):
        doc.add_reasoning(self.llm.generate(InitializePrompt(doc.claim)))
        n_iterations = 0
        label = Label.NEI
        while label == Label.NEI and n_iterations < self.max_iterations:
            self.logger.log("Not enough information yet. Continuing fact-check...")
            n_iterations += 1
            actions, reasoning = self.planner.plan_next_actions(doc)
            if len(reasoning) > 32:  # Only keep substantial reasoning
                doc.add_reasoning(reasoning)
            doc.add_actions(actions)
            if actions:
                evidences = self.actor.perform(actions, doc)
                doc.add_evidence(evidences)  # even if no evidence, add empty evidence block for the record
                self._develop(doc)
            label = self.judge.judge(doc, is_final=n_iterations == self.max_iterations or not actions)
        return label, {}
