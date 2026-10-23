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

RAG retrieves relevant source passages at question time and gives them to a language model as context. Fine-tuning trains a model on examples to change its behavior. It can teach a style or repeated task pattern, but it does not automatically provide a current, inspectable source for each answer. RAG fits conference talks because the content can be searched and cited without training a model on the whole collection, and the source material can be updated independently. Fine-tuning may be a better fit when the main goal is consistent behavior, format, or style across many examples rather than looking up a changing collection of facts. [OpenAI's fine-tuning guide](https://platform.openai.com/docs/guides/fine-tuning)

### 5. AI-assisted development — draft to review

My AI assistant helped me break the project into manageable steps, troubleshoot the Supabase setup, and explain how the database, authentication, Edge Functions, and RAG search fit together. It also helped me understand security concepts such as keeping private keys on the server and using Row Level Security to control database access.

I had to guide the assistant by reminding it to follow the Canvas requirements, keep planned OpenAI spending under $1, and limit GitHub changes to my approved repository. I also corrected the OpenAI key after discovering that the earlier key was wrong. This showed me that AI assistance still needs clear constraints and human checking.

I learned how a RAG application connects semantic search with an AI-generated answer, and why the retrieved passages and citations need to be checked. I also learned to verify the deployed configuration and sign-in flow instead of assuming that a local code setting automatically works on the live site.

Review this draft and change anything that does not match your own experience or wording before submitting.

## Current verification state

- Supabase contains 25,696 sentence records from 431 talks, and all 25,696 rows have 1536-dimensional embeddings.
- The schema applies RLS to the sentence and page-view tables. The browser uses only the public Supabase key; the service key and OpenAI key stay server-side.
- The private OpenAI budget ledger is installed. Bulk embedding generation is capped at $0.40 and website calls are capped at $0.55, keeping this project's planned OpenAI usage under $1.
- The saved OpenAI key authenticated successfully and is configured as a Supabase Edge Function secret.
- The current `embed-question` and `generate-answer` functions are deployed with manual user authentication and budget reservations.
- Supabase Auth now uses the GitHub Pages URL as its Site URL and allows that exact return URL plus the course's `http://localhost:5500/` development URL.
- A signed-in live RAG question, its observed retrieval result, and the screenshot remain to be added after verification.
