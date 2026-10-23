# Conference RAG Submission Notes

Use these notes to finish the Canvas submission. Replace bracketed items with your own details and verify the live app before claiming that semantic search or RAG works.

## Deliverables

- Repository: https://github.com/Nivlac17/conference-rag
- Live site: https://nivlac17.github.io/conference-rag/
- Working RAG screenshot: [capture after the signed-in end-to-end query succeeds]
- Custom feature: Matched Excerpt Viewer (description below)
- Reflection: Review and personalize the draft answers below
- Agent transcript: Attach or export the relevant Codex conversation as required by Canvas

## Custom feature: Matched Excerpt Viewer

Each generated answer lists source talks. The expandable “View matched excerpts” area shows the retrieved sentences that made each talk relevant. This makes the evidence behind an answer easier to inspect and gives readers a direct route from a generated summary to the supporting talk.

## Reflection draft

### 1. Security architecture

The browser receives the Supabase project URL and publishable (anon) key from `config.public.json`. The key identifies the project but does not grant administrator access. Row Level Security (RLS) is the database boundary: browser requests are evaluated under the signed-in user's JWT and the policies on each table. The service-role/secret key bypasses RLS, so anyone who obtained it could read or change data with elevated access; it must stay server-side and out of GitHub. The OpenAI key is held as a Supabase Edge Function secret. The browser sends requests to an Edge Function, which checks the user's JWT before calling OpenAI, so the key is not shipped to the browser.

Flow: browser (public Supabase config, user JWT) → authenticated Edge Function (server-side OpenAI secret and usage reservation) → OpenAI. Supabase RLS separately controls database reads and writes. A private database ledger reserves estimated maximum API costs before each website call and caps website reservations at $0.55; the bulk embedding script separately stops at $0.40.

### 2. Edge Functions and the secure middle

Calling OpenAI directly from browser code would expose the API key to every site visitor and let others use the account's quota. The browser instead sends the question to an Edge Function. The function verifies the Supabase JWT, reads the OpenAI secret from its server environment, makes the API request, and returns the result. JWT verification establishes which signed-in user made the request; it does not itself impose a usage cap. This server-side pattern is useful whenever an application needs to protect credentials or enforce server-side rules while still providing a browser interface.

### 3. Keyword search and semantic search

Keyword search uses SQL `ILIKE` and is useful when a reader remembers an exact phrase, name, or term. It can miss a paraphrase that uses different words. Semantic search compares vector embeddings, so it can retrieve passages with related meaning even when they do not share the query's exact wording. For example, an exact search for “comfort in grief” can miss a passage that says “the Lord can strengthen us after a loss”; semantic search may find it because the wording is conceptually related. Embeddings represent text as vectors learned from language patterns, and cosine similarity ranks vectors pointing in similar directions. Add one example from your live query after verification: what you asked, which talks were retrieved, and whether the results matched what you expected.

### 4. RAG and fine-tuning

RAG retrieves relevant source passages at question time and gives them to a language model as context. Fine-tuning updates model weights using examples, which can teach a model a style or repeated task pattern but does not automatically provide a current, inspectable source for each answer. RAG fits conference talks because the content can be searched and cited without training a model on the whole collection, and the source material can be updated independently. Fine-tuning may be a better fit when the main goal is consistent behavior, format, or style across many examples rather than looking up a changing collection of facts. [Add a course-specific point or a source you consulted if Canvas expects research citations.]

### 5. AI-assisted development — personalize this section

Complete these statements in your own words:

- The assistant helped me by: [specific useful example]
- I had to guide or correct it when: [specific example]
- I learned that: [what you now understand or would do differently]

## Current verification state

- Supabase contains 25,696 sentence records from 431 talks, and all 25,696 rows have 1536-dimensional embeddings.
- The schema applies RLS to the sentence and page-view tables. The browser uses only the public Supabase key; the service key and OpenAI key stay server-side.
- The private OpenAI budget ledger is installed. Bulk embedding generation is capped at $0.40 and website calls are capped at $0.55, keeping this project's planned OpenAI usage under $1.
- The saved OpenAI key authenticated successfully and is configured as a Supabase Edge Function secret.
- The current `embed-question` and `generate-answer` functions are deployed with manual user authentication and budget reservations.
- A signed-in live RAG question, its observed retrieval result, and the screenshot remain to be added after verification.
