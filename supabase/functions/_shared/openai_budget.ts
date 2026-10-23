type ReservationResult = "reserved" | "exhausted" | "unavailable";

function getServiceKey(): string | null {
  const legacyKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (legacyKey) return legacyKey;

  // Current Supabase projects expose named secret keys as a JSON object.
  try {
    const keys = JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS") ?? "{}");
    if (typeof keys.default === "string") return keys.default;
    const values = Object.values(keys);
    return values.length === 1 && typeof values[0] === "string" ? values[0] : null;
  } catch {
    return null;
  }
}

/** Atomically reserve estimated OpenAI spend. Fail closed if the DB gate is unavailable. */
export async function reserveOpenAIBudget(amountUsd: number): Promise<ReservationResult> {
  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const serviceKey = getServiceKey();
  if (!supabaseUrl || !serviceKey || !Number.isFinite(amountUsd) || amountUsd <= 0) {
    return "unavailable";
  }

  try {
    const response = await fetch(`${supabaseUrl.replace(/\/$/, "")}/rest/v1/rpc/reserve_openai_budget`, {
      method: "POST",
      headers: {
        apikey: serviceKey,
        Authorization: `Bearer ${serviceKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ p_amount: amountUsd }),
    });
    if (!response.ok) return "unavailable";
    const reserved: unknown = await response.json();
    return reserved === true ? "reserved" : "exhausted";
  } catch {
    return "unavailable";
  }
}
