import { jsonResponse } from "./cors.ts";

/** Verify the caller's Supabase access token with Supabase Auth. */
export async function requireAuthenticatedUser(request: Request): Promise<Response | null> {
  const authorization = request.headers.get("Authorization");
  if (!authorization?.startsWith("Bearer ")) {
    return jsonResponse({ error: "Sign in is required." }, 401);
  }

  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const anonKey = Deno.env.get("SUPABASE_ANON_KEY");
  if (!supabaseUrl || !anonKey) {
    console.error("Supabase Auth verification is not configured.");
    return jsonResponse({ error: "Authentication is temporarily unavailable." }, 500);
  }

  try {
    const response = await fetch(`${supabaseUrl.replace(/\/$/, "")}/auth/v1/user`, {
      method: "GET",
      headers: {
        apikey: anonKey,
        Authorization: authorization,
      },
    });
    if (!response.ok) {
      return jsonResponse({ error: "Your session is invalid or expired. Please sign in again." }, 401);
    }

    const user = await response.json();
    return user?.id ? null : jsonResponse({ error: "Your session is invalid." }, 401);
  } catch (error) {
    console.error("Supabase Auth verification failed:", error);
    return jsonResponse({ error: "Authentication is temporarily unavailable." }, 502);
  }
}
