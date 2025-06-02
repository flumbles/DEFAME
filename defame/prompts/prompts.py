import re
import traceback
from pathlib import Path
from typing import Collection, Optional
from datetime import datetime

from defame.common import Report, Label, Claim, Action, Prompt, Content, logger
from defame.common.action import get_action_documentation
from defame.common.label import DEFAULT_LABEL_DEFINITIONS
from defame.evidence_retrieval.integrations.search.common import Source
from defame.common.results import Results
from defame.utils.parsing import (remove_non_symbols, extract_last_code_span, read_md_file,
                                  find_code_span, extract_last_paragraph, extract_last_python_code_block,
                                  strip_string, remove_code_blocks, parse_function_call)

SYMBOL = 'Check-worthy'
NOT_SYMBOL = 'Unimportant'

def get_action_registry():
    """Lazy import to avoid circular dependencies"""
    from defame.evidence_retrieval.tools import ACTION_REGISTRY
    return ACTION_REGISTRY

def get_search_action():
    """Lazy import to avoid circular dependencies"""
    from defame.evidence_retrieval.tools import Search
    return Search

class JudgePrompt(Prompt):
    template_file_path = "defame/prompts/judge.md"
    retry_instruction = ("(Do not forget to choose one option from Decision Options "
                         "and enclose it in backticks like `this`)")

    def __init__(self, doc: Report,
                 classes: Collection[Label],
                 class_definitions: dict[Label, str] = None,
                 extra_rules: str = None):
        if class_definitions is None:
            class_definitions = DEFAULT_LABEL_DEFINITIONS
        self.classes = classes
        class_str = '\n'.join([f"* `{cls.value}`: {remove_non_symbols(class_definitions[cls])}"
                               for cls in classes])
        placeholder_targets = {
            "[DOC]": str(doc),
            "[CLASSES]": class_str,
            "[EXTRA_RULES]": "" if extra_rules is None else remove_non_symbols(extra_rules),
        }
        super().__init__(placeholder_targets=placeholder_targets)

    def extract(self, response: str) -> dict | str | None:
        verdict = extract_verdict(response, classes=self.classes)
        if verdict is None:
            return None
        else:
            return dict(verdict=verdict, response=response)


class DecontextualizePrompt(Prompt):
    template_file_path = "defame/prompts/decontextualize.md"

    def __init__(self, claim: Claim):
        placeholder_targets = {
            "[ATOMIC_FACT]": str(claim),
            "[CONTEXT]": str(claim.context),
        }
        super().__init__(placeholder_targets=placeholder_targets)


class FilterCheckWorthyPrompt(Prompt):
    def __init__(self, claim: Claim, filter_method: str = "default"):
        assert (filter_method in ["default", "custom"])
        placeholder_targets = {  # re-implement this
            "[SYMBOL]": SYMBOL,
            "[NOT_SYMBOL]": NOT_SYMBOL,
            "[ATOMIC_FACT]": claim,
            "[CONTEXT]": claim.context,
        }
        if filter_method == "custom":
            self.template_file_path = "defame/prompts/custom_checkworthy.md"
        else:
            self.template_file_path = "defame/prompts/default_checkworthy.md"
        super().__init__(placeholder_targets=placeholder_targets)


class SummarizeSourcePrompt(Prompt):
    template_file_path = "defame/prompts/summarize_source.md"

    def __init__(self, source: Source, doc: Report):
        placeholder_targets = {
            "[SOURCE]": str(source),
            "[DOC]": str(doc),
        }
        super().__init__(placeholder_targets=placeholder_targets)


class SummarizeManipulationResultPrompt(Prompt):
    template_file_path = "defame/prompts/summarize_manipulation_result.md"

    def __init__(self, manipulation_result: Results):
        placeholder_targets = {
            "[MANIPULATION_RESULT]": str(manipulation_result),
        }
        super().__init__(placeholder_targets=placeholder_targets)


class SummarizeDocPrompt(Prompt):
    template_file_path = "defame/prompts/summarize_doc.md"

    def __init__(self, doc: Report):
        super().__init__(placeholder_targets={"[DOC]": doc})


class PlanPrompt(Prompt):
    template_file_path = "defame/prompts/plan.md"

    def __init__(self, doc: Report,
                 valid_actions: Collection[type[Action]],
                 extra_rules: str = None,
                 all_actions: bool = False):
        action_docs = [get_action_documentation(a) for a in valid_actions]
        valid_action_str = "\n\n".join(action_docs)
        extra_rules = "" if extra_rules is None else remove_non_symbols(extra_rules)
        if all_actions:
            extra_rules = "Very Important: No need to be frugal. Choose all available actions at least once."

        # Add current date information
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        placeholder_targets = {
            "[DOC]": doc,
            "[VALID_ACTIONS]": valid_action_str,
            "[EXTRA_RULES]": extra_rules,
            "[CURRENT_DATE]": current_date,
        }
        super().__init__(placeholder_targets=placeholder_targets)

    def extract(self, response: str) -> dict:
        print("="*70)
        print("DEBUGGING PlanPrompt.extract()")
        print("="*70)
        print(f"Raw response to extract actions from:\n{response}")
        print("="*70)

        # Extract the reasoning first
        reasoning = ""
        if "REASONING:" in response:
            reasoning = response.split("REASONING:", 1)[1].split("```", 1)[0].strip()
        
        # Extract the code block
        code_block = extract_last_python_code_block(response)
        print(f"DEBUG - Extracted code block:\n{code_block}")
        
        # Extract actions from the code block
        actions = []
        if code_block:
            # Simpler pattern to match all search formats
            search_pattern = r'search\s*\(\s*(?:"[^"]+"|\'[^\']+\'|\<image:\d+\>)(?:\s*,\s*(?:"[^"]+"|\'[^\']+\'|\<image:\d+\>|\w+\s*=\s*"[^"]+"|\w+\s*=\s*\'[^\']+\'))*\s*\)'
            search_calls = re.finditer(search_pattern, code_block)
            
            for match in search_calls:
                search_call = match.group(0)
                print(f"DEBUG - Found search call: {search_call}")
                
                try:
                    action = parse_single_action(search_call)
                    if action:
                        actions.append(action)
                        print(f"DEBUG - Successfully parsed action: {action}")
                except Exception as e:
                    print(f"DEBUG - Failed to parse search call '{search_call}': {e}")
                    continue
        
        print(f"DEBUG - Extracted actions: {actions}")
        
        return dict(
            actions=actions,
            reasoning=reasoning,
            response=response,
        )


class PoseQuestionsPrompt(Prompt):
    def __init__(self, doc: Report, n_questions: int = 10, interpret: bool = True):
        placeholder_targets = {
            "[CLAIM]": doc.claim,
            "[N_QUESTIONS]": n_questions
        }
        if interpret:
            self.template_file_path = "defame/prompts/pose_questions.md"
        else:
            self.template_file_path = "defame/prompts/pose_questions_no_interpretation.md"
        super().__init__(placeholder_targets=placeholder_targets)

    def extract(self, response: str) -> dict:
        questions = find_code_span(response)
        return dict(
            questions=questions,
            response=response,
        )


class ProposeQueries(Prompt):
    """Used to generate queries to answer AVeriTeC questions."""
    template_file_path = "defame/prompts/propose_queries.md"

    def __init__(self, question: str, doc: Report):
        placeholder_targets = {
            "[DOC]": doc,
            "[QUESTION]": question,
        }
        super().__init__(placeholder_targets=placeholder_targets)

    def extract(self, response: str) -> dict:
        queries = extract_queries(response)
        return dict(
            queries=queries,
            response=response,
        )


class ProposeQuerySimple(Prompt):
    """Used to generate queries to answer AVeriTeC questions."""
    template_file_path = "defame/prompts/propose_query_simple.md"

    def __init__(self, question: str):
        placeholder_targets = {
            "[QUESTION]": question,
        }
        super().__init__(placeholder_targets=placeholder_targets)

    def extract(self, response: str) -> dict:
        queries = extract_queries(response)
        return dict(
            queries=queries,
            response=response,
        )


class ProposeQueriesNoQuestions(Prompt):
    """Used to generate queries to answer AVeriTeC questions."""
    template_file_path = "defame/prompts/propose_queries_no_questions.md"

    def __init__(self, doc: Report):
        placeholder_targets = {
            "[DOC]": doc,
        }
        super().__init__(placeholder_targets=placeholder_targets)

    def extract(self, response: str) -> dict:
        queries = extract_queries(response)
        return dict(
            queries=queries,
            response=response,
        )


class AnswerCollectively(Prompt):
    """Used to generate answers to the AVeriTeC questions."""
    template_file_path = "defame/prompts/answer_question_collectively.md"

    def __init__(self, question: str, results: list[Source], doc: Report):
        result_strings = [f"## Result `{i}`\n{str(result)}" for i, result in enumerate(results)]
        results_str = "\n\n".join(result_strings)

        placeholder_targets = {
            "[DOC]": doc,
            "[QUESTION]": question,
            "[RESULTS]": results_str,
        }
        super().__init__(placeholder_targets=placeholder_targets)

    def extract(self, response: str) -> dict:
        """Extract result ID and answer to the question from response"""
        answered = "NONE" not in response and "None" not in response

        out = dict(
            answered=answered,
            response=response,
        )

        if answered:
            result_id = extract_last_code_span(response)
            if result_id != "":
                result_id = int(result_id)
                answer = extract_last_paragraph(response)
                out.update(dict(
                    answer=answer,
                    result_id=result_id,
                ))

        return out


class AnswerQuestion(Prompt):
    """Used to generate answers to the AVeriTeC questions."""
    template_file_path = "defame/prompts/answer_question.md"

    def __init__(self, question: str, result: Source, doc: Report):
        placeholder_targets = {
            "[DOC]": doc,
            "[QUESTION]": question,
            "[RESULT]": result,
        }
        super().__init__(placeholder_targets=placeholder_targets)

    def extract(self, response: str) -> dict:
        """Extract result ID and answer to the question from response"""
        answered = "NONE" not in response and "None" not in response

        out = dict(
            answered=answered,
            response=response,
        )

        if answered:
            answer = extract_last_paragraph(response)
            out.update(dict(answer=answer))

        return out


class AnswerQuestionNoEvidence(Prompt):
    """Used to generate answers to the AVeriTeC questions."""
    template_file_path = "defame/prompts/answer_question_no_evidence.md"

    def __init__(self, question: str, doc: Report):
        placeholder_targets = {
            "[DOC]": doc,
            "[QUESTION]": question,
        }
        super().__init__(placeholder_targets=placeholder_targets)


class DevelopPrompt(Prompt):
    template_file_path = "defame/prompts/develop.md"

    def __init__(self, doc: Report):
        placeholder_targets = {"[DOC]": doc}
        super().__init__(placeholder_targets=placeholder_targets)


class InterpretPrompt(Prompt):
    template_file_path = "defame/prompts/interpret.md"

    def __init__(self, content: Content, guidelines: str = None):
        placeholder_targets = {
            "[CONTENT]": content,
            "[GUIDELINES]": guidelines,
        }
        super().__init__(placeholder_targets=placeholder_targets)

    def extract(self, response: str) -> dict | str | None:
        paragraphs = response.split("\n")
        assert len(paragraphs) >= 2
        interpretation = paragraphs[0]
        topic = paragraphs[-1]
        return dict(
            interpretation=interpretation,
            topic=topic,
            response=response,
        )


class DecomposePrompt(Prompt):
    template_file_path = "defame/prompts/decompose.md"

    def __init__(self, content: Content):
        self.content = content
        placeholder_targets = {
            "[CONTENT]": content,
            "[INTERPRETATION]": content.interpretation
        }
        super().__init__(placeholder_targets=placeholder_targets)

    def extract(self, response: str) -> dict:
        statements = response.split("\n\n")
        return dict(statements=[Claim(s.strip(), context=self.content) for s in statements if s],
                    response=response)


class JudgeNaively(Prompt):
    template_file_path = "defame/prompts/judge_naive.md"

    def __init__(self, claim: Claim,
                 classes: Collection[Label],
                 class_definitions: dict[Label, str] = None):
        self.classes = classes
        if class_definitions is None:
            class_definitions = DEFAULT_LABEL_DEFINITIONS
        class_str = '\n'.join([f"* `{cls.value}`: {remove_non_symbols(class_definitions[cls])}"
                               for cls in classes])
        placeholder_targets = {
            "[CLAIM]": claim,
            "[CLASSES]": class_str,
        }
        super().__init__(placeholder_targets=placeholder_targets)

    def extract(self, response: str) -> dict:
        verdict = extract_verdict(response, classes=self.classes)
        return dict(verdict=verdict, response=response)


class JudgeMinimal(JudgeNaively):
    template_file_path = "defame/prompts/judge_minimal.md"


class InitializePrompt(Prompt):
    template_file_path = "defame/prompts/initialize.md"

    def __init__(self, claim: Claim):
        placeholder_targets = {
            "[CLAIM]": claim,
        }
        super().__init__(placeholder_targets=placeholder_targets)


def load_exemplars(valid_actions: Collection[type[Action]]) -> str:
    exemplars_dir = Path("defame/prompts/plan_exemplars")
    exemplar_paths = []
    for a in valid_actions:
        exemplar_path = exemplars_dir / f"{a.name}.md"
        if exemplar_path.exists():
            exemplar_paths.append(exemplar_path)

    if len(exemplar_paths) == 0:
        return read_md_file(exemplars_dir / "default.md")
    else:
        return "\n\n".join([read_md_file(path) for path in exemplar_paths])


def parse_single_action(raw_action: str) -> Optional[Action]:
    print(f"\n=== DEBUG: Starting parse_single_action ===")
    print(f"Raw action: {raw_action}")
    
    raw_action = raw_action.strip(" \"")
    print(f"Stripped action: {raw_action}")

    if not raw_action:
        print("DEBUG - Empty action, returning None")
        return None

    try:
        out = parse_function_call(raw_action)
        print(f"DEBUG - parse_function_call result: {out}")

        if out is None:
            print("DEBUG - Failed to parse function call")
            raise ValueError(f'Invalid action: {raw_action}\nExpected format: action_name(<arg1>, <arg2>, ...)')

        action_name, args, kwargs = out
        print(f"DEBUG - Parsed components:")
        print(f"  - action_name: {action_name}")
        print(f"  - args: {args}")
        print(f"  - kwargs: {kwargs}")

        # Get available actions
        ACTION_REGISTRY = get_action_registry()

        for action in ACTION_REGISTRY:
            if action_name == action.name:
                # Handle image search formats
                if action_name == "search":
                    # Extract image reference if present in args or kwargs
                    image_ref = None
                    query = None
                    
                    # Check args first
                    print("\nDEBUG - Checking args for image/query")
                    for arg in args:
                        if isinstance(arg, str):
                            if "<image:" in arg:
                                image_ref = arg
                                print(f"DEBUG - Found image ref in args: {image_ref}")
                            else:
                                query = arg
                                print(f"DEBUG - Found query in args: {query}")
                    
                    # Check kwargs
                    print("\nDEBUG - Checking kwargs for image/query")
                    if "image" in kwargs:
                        image_ref = kwargs["image"]
                        print(f"DEBUG - Found image ref in kwargs: {image_ref}")
                    if "query" in kwargs:
                        query = kwargs["query"]
                        print(f"DEBUG - Found query in kwargs: {query}")
                    
                    # Create appropriate search action
                    print("\nDEBUG - Creating search action")
                    print(f"Final values: query={query}, image={image_ref}")
                    if image_ref and query:
                        print("DEBUG - Creating combined search")
                        return action(query=query, image=image_ref, mode="reverse")
                    elif image_ref:
                        print("DEBUG - Creating image-only search")
                        return action(image=image_ref, mode="reverse")
                    else:
                        print("DEBUG - Creating text-only search")
                        return action(*args, **kwargs)
                return action(*args, **kwargs)

        raise ValueError(f'Invalid action: {raw_action}\nExpected format: action_name(<arg1>, <arg2>, ...)')

    except Exception as e:
        print(f"DEBUG - Exception in parse_single_action: {str(e)}")
        print(f"DEBUG - Traceback: {traceback.format_exc()}")
        logger.warning(f"Failed to parse '{raw_action}':\n{e}")
        logger.warning(traceback.format_exc())

    return None


def extract_actions(answer: str, limit=5, claim_text: str = None) -> list[Action]:
    actions = []
    
    print("\n=== DEBUG: Starting extract_actions ===")
    print(f"Input answer:\n{answer}")
    
    # First try to extract from code block
    code_block = extract_last_python_code_block(answer)
    print(f"\nDEBUG - Raw code block content:\n{code_block}")
    
    if code_block:
        # Pattern to match all search formats including named parameters
        search_pattern = r'search\s*\(\s*(?:(?:query\s*=\s*)?["\']([^"\']+)["\']|(?:image\s*=\s*)?["\']([^"\']+)["\']|\w+\s*=\s*["\'][^"\']+["\'])(?:\s*,\s*(?:(?:query\s*=\s*)?["\']([^"\']+)["\']|(?:image\s*=\s*)?["\']([^"\']+)["\']|\w+\s*=\s*["\'][^"\']+["\']))*\s*\)'
        print(f"\nDEBUG - Using search pattern:\n{search_pattern}")
        
        search_calls = re.finditer(search_pattern, code_block)
        search_matches = list(search_calls)  # Convert iterator to list for debugging
        print(f"\nDEBUG - Found {len(search_matches)} search matches")
        
        for match in search_matches:
            search_call = match.group(0)
            print(f"\nDEBUG - Processing search call: {search_call}")
            print(f"DEBUG - Match groups: {match.groups()}")
            
            try:
                action = parse_single_action(search_call)
                print(f"DEBUG - Parsed action result: {action}")
                if action:
                    actions.append(action)
                    print(f"DEBUG - Successfully added action: {action}")
            except Exception as e:
                print(f"DEBUG - Failed to parse search call '{search_call}':")
                print(f"DEBUG - Error: {str(e)}")
                print(f"DEBUG - Traceback: {traceback.format_exc()}")
                continue
    
    # If no actions found in code block, try to find them directly in the text
    if not actions:
        print("\nDEBUG - No actions found in code block, trying direct format")
        # Look for direct action calls in the text
        ACTION_REGISTRY = get_action_registry()
        for action_type in ACTION_REGISTRY:
            pattern = re.compile(rf'({re.escape(action_type.name)}\(.+?\))', re.DOTALL)
            matches = pattern.findall(answer)
            print(f"\nDEBUG - Found {len(matches)} direct matches for {action_type.name}")
            for match in matches:
                print(f"DEBUG - Processing direct match: {match}")
                action = parse_single_action(match)
                if action:
                    actions.append(action)
                    print(f"DEBUG - Successfully added direct action: {action}")
    
    # Only fall back to default search if we have no actions and no reasoning
    if not actions and claim_text and "REASONING:" not in answer:
        print("\nDEBUG - No actions or reasoning found, creating default search")
        print(f"DEBUG - Claim text: {claim_text}")
        Search = get_search_action()
        # For image claims, use the image in the search
        if "<image:" in claim_text:
            image_ref = re.search(r'<image:\d+>', claim_text)
            if image_ref:
                print(f"DEBUG - Found image reference: {image_ref.group(0)}")
                return [Search(image=image_ref.group(0), mode="reverse")]
        actions.append(Search(claim_text))
    
    print(f"\nDEBUG - Final actions list: {actions}")
    return actions[:limit]


def extract_verdict(response: str, classes: Collection[Label]) -> Optional[Label]:
    answer = extract_last_code_span(response)
    answer = re.sub(r'[^\w\-\s]', '', answer).strip().lower()

    if not answer:
        pattern = re.compile(r'\*\*(.*)\*\*', re.DOTALL)
        matches = pattern.findall(response) or ['']
        answer = matches[0]

    try:
        label = Label(answer)
        assert label in classes
        return label

    except ValueError:
        # TODO: Verify if this is necessary
        # Maybe the label is a substring of the response
        for c in classes:
            if c.value in response:
                return c

    return None


def extract_queries(response: str) -> list:
    matches = find_code_span(response)
    queries = []
    for match in matches:
        query = strip_string(match)
        action = Search(f'"{query}"')
        queries.append(action)
    return queries


def extract_reasoning(answer: str) -> str:
    return remove_code_blocks(answer).strip()
