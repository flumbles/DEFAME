# Instructions
The available knowledge is insufficient to assess the Claim. Therefore, **propose a set of actions** to retrieve new and helpful evidence. Adhere to the following rules:
* The actions available are listed under Valid Actions, including a short description for each action. No other actions are possible at this moment. 
* For each action, use the formatting as specified in Valid Actions.
* Include all actions in a single Python code block at the end of your answer.
* IMPORTANT: DO NOT write any Python functions, imports, or other code. ONLY write search actions.
* For search actions, use these exact formats:
  1. Text search: search("search query text", platform="google", mode="search")
  2. Image search: search("<image:N>", platform="google", mode="reverse")
  3. Combined search: search("search query text", "<image:N>", platform="google", mode="reverse")
* Each search action should be on its own line in the code block.
* Break down the claim into specific aspects and create targeted search queries.
* For each search query, first explain in the REASONING section why you're searching for that specific information.
* IMPORTANT: When dealing with dates and events:
  - Today's date: [CURRENT_DATE]
  - Consider this context for any temporal claims or future events
* For claims containing images:
  - Always use reverse image search first to verify the image's authenticity and context
  - Then use combined text+image search to find more specific related content

[EXTRA_RULES]
Very Important: Use at most 2 search queries per iteration. Make each search query as specific and targeted as possible.

## Valid Actions
[VALID_ACTIONS]

# Record
[DOC]

# Your Actions
