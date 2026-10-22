import { corsHeaders, jsonResponse } from "../_shared/cors.ts";
import { requireAuthenticatedUser } from "../_shared/auth.ts";

Deno.serve(async (request: Request) => {
  if (request.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }
  if (request.method !== "POST") {
    return jsonResponse({ error: "Method not allowed." }, 405);
  }

  const authError = await requireAuthenticatedUser(request);
  if (authError) return authError;

  let body: { question?: unknown; health_check?: unknown };
  try {
    body = await request.json();
  } catch {
    return jsonResponse({ error: "Request body must be valid JSON." }, 400);
  }

  // app.js uses this inexpensive probe to light the UI status indicator.
  // It deliberately returns without making a billable OpenAI request.
  if (body.health_check === true) {
    const ready = Boolean(Deno.env.get("OPENAI_API_KEY"));
    return jsonResponse({ ready }, ready ? 200 : 503);
  }

  const question = typeof body.question === "string" ? body.question.trim() : "";
  if (!question || question.length > 1000) {
    return jsonResponse({ error: "Question must contain 1–1000 characters." }, 400);
  }

  const apiKey = Deno.env.get("OPENAI_API_KEY");
  if (!apiKey) {
    console.error("OPENAI_API_KEY is not configured.");
    return jsonResponse({ error: "Question embedding is not configured." }, 500);
  }

  try {
    const response = await fetch("https://api.openai.com/v1/embeddings", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ model: "text-embedding-3-small", input: question }),
    });

    if (!response.ok) {
      console.error("OpenAI embedding request failed with status:", response.status);
      return jsonResponse({ error: "Could not create an embedding. Please try again." }, 502);
    }

    const result = await response.json();
    const embedding = result?.data?.[0]?.embedding;
    if (!Array.isArray(embedding) || embedding.length !== 1536) {
      console.error("OpenAI returned an unexpected embedding shape.");
      return jsonResponse({ error: "The embedding service returned an unexpected result." }, 502);
    }

    return jsonResponse({ embedding });
  } catch (error) {
    console.error("Embedding request failed:", error);
    return jsonResponse({ error: "Could not create an embedding. Please try again." }, 502);
  }
});
