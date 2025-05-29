# Instructions
The available knowledge is insufficient to assess the Claim. Therefore, **propose a set of actions** to retrieve new and helpful evidence. Adhere to the following rules:
* The actions available are listed under Valid Actions, including a short description for each action. No other actions are possible at this moment. 
* For each action, use the formatting as specified in Valid Actions.
* Include all actions in a single Python code block at the end of your answer.
* IMPORTANT: DO NOT write any Python functions, imports, or other code. ONLY write search actions.
* For search actions, use ONLY this exact format: search("search query text", platform="google", mode="search|news|images")
  - DO NOT include parameter names like query= or image=
  - The search text must be the first parameter in quotes
  - Platform and mode are optional named parameters
* Each search action should be on its own line in the code block.
* Break down the claim into specific aspects and create targeted search queries.
* For each search query, first explain in the REASONING section why you're searching for that specific information.
* IMPORTANT: When dealing with dates and events:
  - Today's date: [CURRENT_DATE]
  - Consider this context for any temporal claims or future events

[EXTRA_RULES]

## Valid Actions
[VALID_ACTIONS]

# Record
[DOC]

# Your Actions