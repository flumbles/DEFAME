from typing import Collection

import pyparsing as pp

from defame.common.action import (Action)
from defame.evidence_retrieval.tools import IMAGE_ACTIONS, Search
from defame.common import logger, Report, Model
from defame.prompts.prompts import PlanPrompt


class Planner:
    """Chooses the next actions to perform based on the current knowledge as contained
    in the FC document."""

    def __init__(self,
                 valid_actions: Collection[type[Action]],
                 llm: Model,
                 extra_rules: str):
        self.valid_actions = valid_actions
        self.llm = llm
        self.max_attempts = 5
        self.extra_rules = extra_rules

    def get_available_actions(self, doc: Report):
        available_actions = []
        completed_actions = set(type(a) for a in doc.get_all_actions())

        if doc.claim.has_image():  # TODO: enable multiple image actions for multiple images
            available_actions += [a for a in IMAGE_ACTIONS if a not in completed_actions]

        # TODO: finish this method

        return available_actions

    def plan_next_actions(self, doc: Report, all_actions=False) -> (list[Action], str):
        # First, try to get actions from the original planning logic
        prompt = PlanPrompt(doc, self.valid_actions, self.extra_rules, all_actions)
        n_attempts = 0
        original_actions = []
        original_reasoning = ""

        # Clean up the claim text first
        claim_text = str(doc.claim)
        if "Claim:" in claim_text:
            claim_text = claim_text.split("Claim:", 1)[1].strip()
            claim_text = claim_text.split('"')[1] if '"' in claim_text else claim_text
            claim_text = claim_text.split("\n")[0].strip()
        print(f"DEBUG - Using claim text: {claim_text}")

        while n_attempts < self.max_attempts and not original_actions:
            n_attempts += 1

            response = self.llm.generate(prompt)
            if response is None:
                logger.warning("No new actions were found.")
                break

            actions_from_prompt = response["actions"]
            reasoning_from_prompt = response["reasoning"]

            # Remove actions that have been performed before
            performed_actions = doc.get_all_actions()
            original_actions = [action for action in actions_from_prompt if action not in performed_actions]
            print(f"DEBUG - Original actions: {original_actions}")
            
            if original_actions:
                original_reasoning = reasoning_from_prompt 
                print(f"DEBUG - Original reasoning: {original_reasoning}")
            else:
                # If no actions were found, force a search action with the claim text
                search_action = Search(claim_text)
                original_actions = [search_action]
                original_reasoning = "Performing a search to find information about the claim."
                logger.info("No actions found from LLM, adding default search action.")

        # Now, check if we should add a Geolocate action for images
        geolocate_action = None
        geolocate_reasoning = ""
        
        try:
            # Use has_image() method if it exists
            has_image = doc.claim.has_image() if hasattr(doc.claim, 'has_image') else False
        except Exception:
            # Fallback: try checking if there are any Image objects in the claim items
            has_image = False
            try:
                for item in doc.claim:
                    if "Image" in str(type(item)):
                        has_image = True
                        break
            except Exception:
                # If all else fails, assume no image
                has_image = False
        
        if has_image:
            completed_action_types = set(type(a) for a in doc.get_all_actions())
            # Check if Geolocate hasn't been performed yet
            if Geolocate not in completed_action_types:
                try:
                    # Try to get image URLs
                    if hasattr(doc.claim, 'get_image_urls'):
                        image_urls = doc.claim.get_image_urls()
                    else:
                        # Fallback: try to find image references directly
                        image_urls = []
                        for item in doc.claim:
                            if "Image" in str(type(item)) and hasattr(item, 'reference'):
                                image_urls.append(item.reference)
                    
                    if image_urls:
                        geolocate_action = Geolocate(image_urls[0])
                        geolocate_reasoning = "Adding geolocation analysis for the image in this claim."
                except Exception as e:
                    logger.warning(f"Failed to create Geolocate action: {e}")
        
        # Combine original actions with Geolocate if available
        final_actions = original_actions.copy()
        final_reasoning = original_reasoning
        
        if geolocate_action and geolocate_action not in final_actions:
            final_actions.append(geolocate_action)
            if final_reasoning:
                final_reasoning += " " + geolocate_reasoning
            else:
                final_reasoning = geolocate_reasoning
        
        return final_actions, final_reasoning


def _process_answer(answer: str) -> str:
    reasoning = answer.split("NEXT_ACTIONS:")[0].strip()
    return reasoning.replace("REASONING:", "").strip()


def _extract_arguments(arguments_str: str) -> list[str]:
    """Separates the arguments_str at all commas that are not enclosed by quotes."""
    ppc = pp.pyparsing_common

    # Setup parser which separates at each comma not enclosed by a quote
    csl = ppc.comma_separated_list()

    # Parse the string using the created parser
    parsed = csl.parse_string(arguments_str)

    # Remove whitespaces and split into arguments list
    return [str.strip(value) for value in parsed]
