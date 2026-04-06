import { createClient, type SupabaseClient } from "npm:@supabase/supabase-js@2";
import lessons from "../_shared/lessons.json" with { type: "json" };

type LessonQuiz = {
  prompt: string;
  options: string[];
  answer_index: number;
  explanation: string;
};

type Lesson = {
  lesson_id: string;
  topic_name: string;
  stage: number;
  title: string;
  summary: string;
  explanation: string;
  code_sample: string;
  challenge: string;
  xp_reward: number;
  quiz: LessonQuiz;
};

type UserRecord = {
  id: number;
  username: string;
  xp: number;
};

type LeaderboardRow = {
  username: string;
  xp: number;
  completed_lessons: number;
};

type AppUpdateRow = {
  version: string;
  download_url: string;
  notes: string | null;
  asset_name: string | null;
  wipe_local_state: boolean | null;
  force_update: boolean | null;
};

type ClientMeta = {
  installId: string;
  sessionName: string;
  clientType: string;
  appVersion: string;
  ipAddress: string;
  ipCountry: string;
  userAgent: string;
};

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type, x-admin-key, x-pyquest-app-version, x-pyquest-client-type, x-pyquest-session-name, x-pyquest-install-id",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
};

const lessonList = lessons as Lesson[];
const lessonMap = new Map(lessonList.map((lesson) => [lesson.lesson_id, lesson]));
const lessonCatalog = lessonList.map((lesson) => ({
  lesson_id: lesson.lesson_id,
  topic_name: lesson.topic_name,
  stage: lesson.stage,
  title: lesson.title,
  summary: lesson.summary,
  explanation: lesson.explanation,
  code_sample: lesson.code_sample,
  challenge: lesson.challenge,
  xp_reward: lesson.xp_reward,
  quiz: {
    prompt: lesson.quiz.prompt,
    options: lesson.quiz.options,
  },
}));

let adminClient: SupabaseClient | null = null;

function jsonResponse(payload: Record<string, unknown>, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      ...corsHeaders,
      "Content-Type": "application/json; charset=utf-8",
    },
  });
}

function routePath(url: URL): string {
  const pathname = url.pathname.replace(/\/+$/, "") || "/";
  const prefixes = [
    "/functions/v1/pyquest-api",
    "/pyquest-api",
  ];

  for (const prefix of prefixes) {
    if (pathname === prefix) {
      return "/";
    }
    if (pathname.startsWith(`${prefix}/`)) {
      return pathname.slice(prefix.length) || "/";
    }
  }

  return pathname;
}

async function parseJsonBody(request: Request): Promise<Record<string, unknown>> {
  try {
    const payload = await request.json();
    return payload && typeof payload === "object" ? (payload as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

async function hashPassword(password: string): Promise<string> {
  const bytes = new TextEncoder().encode(password);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function tokenHex(bytes = 24): string {
  return Array.from(crypto.getRandomValues(new Uint8Array(bytes)), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function bearerToken(request: Request): string {
  const header = request.headers.get("Authorization") ?? "";
  return header.startsWith("Bearer ") ? header.slice(7).trim() : "";
}

function firstHeaderValue(header: string | null): string {
  return String(header ?? "")
    .split(",")[0]
    .trim();
}

function clientMeta(request: Request): ClientMeta {
  const installId = String(request.headers.get("X-PyQuest-Install-Id") ?? "").trim();
  const sessionName = String(request.headers.get("X-PyQuest-Session-Name") ?? "").trim();
  const clientType = String(request.headers.get("X-PyQuest-Client-Type") ?? "unknown").trim() || "unknown";
  const appVersion = String(request.headers.get("X-PyQuest-App-Version") ?? "").trim();
  const ipAddress =
    firstHeaderValue(request.headers.get("CF-Connecting-IP")) ||
    firstHeaderValue(request.headers.get("X-Forwarded-For")) ||
    firstHeaderValue(request.headers.get("X-Real-IP"));
  const ipCountry =
    String(request.headers.get("CF-IPCountry") ?? request.headers.get("X-Vercel-IP-Country") ?? "").trim();
  const userAgent = String(request.headers.get("User-Agent") ?? "").trim();

  return {
    installId,
    sessionName,
    clientType,
    appVersion,
    ipAddress,
    ipCountry,
    userAgent,
  };
}

async function recordPresence(
  request: Request,
  path: string,
  eventType: string,
  user: UserRecord | null = null,
): Promise<void> {
  const meta = clientMeta(request);
  if (!meta.installId) {
    return;
  }

  const client = getAdminClient();
  const username = user?.username ?? null;
  const userId = user?.id ?? null;
  const nowIso = new Date().toISOString();
  const sessionName = meta.sessionName || `${meta.clientType}-${meta.installId.slice(0, 8)}`;

  const { error } = await client.from("client_presence").upsert(
    {
      install_id: meta.installId,
      session_name: sessionName,
      client_type: meta.clientType,
      app_version: meta.appVersion,
      username,
      user_id: userId,
      ip_address: meta.ipAddress,
      ip_country: meta.ipCountry,
      user_agent: meta.userAgent,
      last_path: path,
      last_event: eventType,
      last_seen_at: nowIso,
    },
    {
      onConflict: "install_id",
    },
  );
  if (error) {
    throw error;
  }
}

async function recordActivity(
  request: Request,
  path: string,
  eventType: string,
  user: UserRecord | null = null,
  usernameOverride: string | null = null,
): Promise<void> {
  const meta = clientMeta(request);
  const username = usernameOverride ?? user?.username ?? null;
  const userId = user?.id ?? null;
  const sessionName = meta.sessionName || null;
  const client = getAdminClient();
  const { error } = await client.from("activity_logs").insert({
    event_type: eventType,
    request_path: path,
    install_id: meta.installId || null,
    session_name: sessionName,
    client_type: meta.clientType,
    app_version: meta.appVersion,
    username,
    user_id: userId,
    ip_address: meta.ipAddress || null,
    ip_country: meta.ipCountry || null,
    user_agent: meta.userAgent || null,
  });
  if (error) {
    throw error;
  }
}

function requireAdminKey(request: Request): void {
  const configured = Deno.env.get("PYQUEST_ADMIN_API_KEY")?.trim() ?? "";
  if (!configured) {
    throw new Error("Missing PYQUEST_ADMIN_API_KEY secret for admin access.");
  }
  const supplied = String(request.headers.get("X-Admin-Key") ?? "").trim();
  if (!supplied || supplied !== configured) {
    const error = new Error("Unauthorized");
    error.name = "Unauthorized";
    throw error;
  }
}

function getAdminClient(): SupabaseClient {
  if (adminClient !== null) {
    return adminClient;
  }

  const supabaseUrl = Deno.env.get("SUPABASE_URL")?.trim() ?? "";
  const serviceRoleKey =
    Deno.env.get("PYQUEST_SUPABASE_SERVICE_ROLE_KEY")?.trim() ??
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")?.trim() ??
    "";

  if (!supabaseUrl || !serviceRoleKey) {
    throw new Error("Missing SUPABASE_URL or service role secret for the Edge Function.");
  }

  adminClient = createClient(supabaseUrl, serviceRoleKey, {
    auth: {
      autoRefreshToken: false,
      persistSession: false,
    },
  });
  return adminClient;
}

async function currentUser(token: string): Promise<UserRecord | null> {
  if (!token) {
    return null;
  }

  const client = getAdminClient();
  const { data, error } = await client
    .from("sessions")
    .select("user_id, users!sessions_user_id_fkey(id, username, xp)")
    .eq("token", token)
    .maybeSingle();

  if (error) {
    throw error;
  }
  if (!data || !data.users) {
    return null;
  }

  const user = Array.isArray(data.users) ? data.users[0] : data.users;
  if (!user) {
    return null;
  }

  return {
    id: Number(user.id),
    username: String(user.username),
    xp: Number(user.xp),
  };
}

async function signup(request: Request, payload: Record<string, unknown>): Promise<Response> {
  const username = String(payload.username ?? "").trim();
  const password = String(payload.password ?? "");
  if (username.length < 3 || password.length < 4) {
    return jsonResponse(
      { error: "Username must be at least 3 characters and password at least 4 characters." },
      400,
    );
  }

  const client = getAdminClient();
  const passwordHash = await hashPassword(password);
  const { data, error } = await client
    .from("users")
    .insert({ username, password_hash: passwordHash })
    .select("id, username, xp")
    .single();

  if (error) {
    if (error.code === "23505") {
      return jsonResponse({ error: "Username already exists." }, 400);
    }
    throw error;
  }

  const token = tokenHex();
  const { error: sessionError } = await client.from("sessions").insert({
    token,
    user_id: data.id,
  });
  if (sessionError) {
    throw sessionError;
  }

  const user = {
    id: Number(data.id),
    username: String(data.username),
    xp: Number(data.xp ?? 0),
  } satisfies UserRecord;
  await recordPresence(request, "/signup", "signup", user);
  await recordActivity(request, "/signup", "signup", user);

  return jsonResponse(
    {
      token,
      user_id: data.id,
      username: data.username,
      xp: Number(data.xp ?? 0),
    },
    201,
  );
}

async function login(request: Request, payload: Record<string, unknown>): Promise<Response> {
  const username = String(payload.username ?? "").trim();
  const password = String(payload.password ?? "");
  const client = getAdminClient();
  const passwordHash = await hashPassword(password);
  const { data, error } = await client
    .from("users")
    .select("id, username, xp")
    .eq("username", username)
    .eq("password_hash", passwordHash)
    .maybeSingle();

  if (error) {
    throw error;
  }
  if (!data) {
    await recordPresence(request, "/login", "login_failed");
    await recordActivity(request, "/login", "login_failed", null, username || null);
    return jsonResponse({ error: "Invalid username or password." }, 400);
  }

  const token = tokenHex();
  const { error: sessionError } = await client.from("sessions").insert({
    token,
    user_id: data.id,
  });
  if (sessionError) {
    throw sessionError;
  }

  const user = {
    id: Number(data.id),
    username: String(data.username),
    xp: Number(data.xp ?? 0),
  } satisfies UserRecord;
  await recordPresence(request, "/login", "login", user);
  await recordActivity(request, "/login", "login", user);

  return jsonResponse({
    token,
    user_id: data.id,
    username: data.username,
    xp: Number(data.xp ?? 0),
  });
}

async function profile(request: Request): Promise<Response> {
  const user = await currentUser(bearerToken(request));
  if (!user) {
    return jsonResponse({ error: "Unauthorized." }, 401);
  }
  await recordPresence(request, "/profile", "profile", user);

  const client = getAdminClient();
  const { data, error } = await client
    .from("lesson_progress")
    .select("lesson_id")
    .eq("user_id", user.id)
    .order("completed_at", { ascending: false });

  if (error) {
    throw error;
  }

  const completedLessonIds = (data ?? []).map((row) => String(row.lesson_id));
  return jsonResponse({
    user_id: user.id,
    username: user.username,
    xp: user.xp,
    completed_lessons: completedLessonIds.length,
    completed_lesson_ids: completedLessonIds,
  });
}

async function submitLesson(request: Request, payload: Record<string, unknown>): Promise<Response> {
  const user = await currentUser(bearerToken(request));
  if (!user) {
    return jsonResponse({ error: "Unauthorized." }, 401);
  }
  await recordPresence(request, "/submit-lesson", "submit_lesson", user);
  await recordActivity(request, "/submit-lesson", "submit_lesson", user);

  if (!("lesson_id" in payload) || !("selected_index" in payload)) {
    return jsonResponse({ error: "Missing required fields." }, 400);
  }

  const lessonId = String(payload.lesson_id ?? "");
  const selectedIndex = Number(payload.selected_index ?? -1);
  if (!Number.isInteger(selectedIndex)) {
    return jsonResponse({ error: "Missing required fields." }, 400);
  }

  const lesson = lessonMap.get(lessonId);
  if (!lesson) {
    return jsonResponse({ error: "Unknown lesson." }, 400);
  }

  const isCorrect = selectedIndex === lesson.quiz.answer_index;
  const partialXp = Math.max(3, Math.floor(lesson.xp_reward / 4));
  const client = getAdminClient();
  const { data: xpGained, error } = await client.rpc("pyquest_record_lesson_result", {
    target_user_id: user.id,
    target_lesson_id: lessonId,
    selected_score: isCorrect ? 1 : 0,
    full_xp: lesson.xp_reward,
    partial_xp: partialXp,
  });

  if (error) {
    throw error;
  }

  const { data: xpRow, error: xpError } = await client
    .from("users")
    .select("xp")
    .eq("id", user.id)
    .single();
  if (xpError) {
    throw xpError;
  }

  return jsonResponse({
    correct: isCorrect,
    xp_gained: Number(xpGained ?? 0),
    correct_answer_index: lesson.quiz.answer_index,
    explanation: lesson.quiz.explanation,
    new_xp: Number(xpRow.xp ?? 0),
  });
}

async function leaderboard(request: Request): Promise<Response> {
  const user = await currentUser(bearerToken(request));
  await recordPresence(request, "/leaderboard", "leaderboard", user);

  const client = getAdminClient();
  const { data, error } = await client.rpc("pyquest_leaderboard");
  if (error) {
    throw error;
  }

  const rows = (data ?? []) as LeaderboardRow[];
  return jsonResponse({
    leaders: rows.map((row, index) => ({
      rank: index + 1,
      username: row.username,
      xp: Number(row.xp),
      completed_lessons: Number(row.completed_lessons),
    })),
  });
}

async function appUpdate(): Promise<Response> {
  const client = getAdminClient();
  const { data, error } = await client
    .from("app_updates")
    .select("version, download_url, notes, asset_name, wipe_local_state, force_update")
    .eq("slug", "desktop")
    .maybeSingle();

  if (error) {
    throw error;
  }
  if (!data) {
    return jsonResponse({ error: "Update metadata not configured." }, 404);
  }

  const row = data as AppUpdateRow;
  return jsonResponse({
    version: String(row.version),
    download_url: String(row.download_url),
    notes: String(row.notes ?? ""),
    asset_name: String(row.asset_name ?? ""),
    wipe_local_state: Boolean(row.wipe_local_state ?? false),
    force_update: Boolean(row.force_update ?? false),
  });
}

async function adminActivity(request: Request): Promise<Response> {
  requireAdminKey(request);
  const url = new URL(request.url);
  const limit = Math.max(1, Math.min(Number(url.searchParams.get("limit") ?? "50"), 200));
  const client = getAdminClient();

  const [presenceResult, loginResult, activityResult] = await Promise.all([
    client
      .from("client_presence")
      .select(
        "install_id, session_name, client_type, app_version, username, ip_address, ip_country, user_agent, last_path, last_event, first_seen_at, last_seen_at",
      )
      .order("last_seen_at", { ascending: false })
      .limit(limit),
    client
      .from("activity_logs")
      .select(
        "id, created_at, event_type, request_path, username, session_name, client_type, app_version, ip_address, ip_country",
      )
      .in("event_type", ["login", "signup"])
      .order("created_at", { ascending: false })
      .limit(limit),
    client
      .from("activity_logs")
      .select(
        "id, created_at, event_type, request_path, username, session_name, client_type, app_version, ip_address, ip_country",
      )
      .order("created_at", { ascending: false })
      .limit(limit),
  ]);

  if (presenceResult.error) {
    throw presenceResult.error;
  }
  if (loginResult.error) {
    throw loginResult.error;
  }
  if (activityResult.error) {
    throw activityResult.error;
  }

  return jsonResponse({
    active_clients: presenceResult.data ?? [],
    recent_logins: loginResult.data ?? [],
    recent_activity: activityResult.data ?? [],
  });
}

Deno.serve(async (request) => {
  if (request.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }

  const url = new URL(request.url);
  const path = routePath(url);

  try {
    if (request.method === "GET" && path === "/health") {
      return jsonResponse({ status: "ok" });
    }
    if (request.method === "GET" && path === "/lessons") {
      await recordPresence(request, "/lessons", "lessons");
      return jsonResponse({ lessons: lessonCatalog });
    }
    if (request.method === "GET" && path === "/profile") {
      return await profile(request);
    }
    if (request.method === "GET" && path === "/leaderboard") {
      return await leaderboard(request);
    }
    if (request.method === "GET" && path === "/app-update") {
      return await appUpdate();
    }
    if (request.method === "GET" && path === "/admin/activity") {
      return await adminActivity(request);
    }

    if (request.method === "POST" && path === "/signup") {
      return await signup(request, await parseJsonBody(request));
    }
    if (request.method === "POST" && path === "/login") {
      return await login(request, await parseJsonBody(request));
    }
    if (request.method === "POST" && path === "/submit-lesson") {
      return await submitLesson(request, await parseJsonBody(request));
    }

    return jsonResponse({ error: "Not found." }, 404);
  } catch (error) {
    console.error("pyquest-api error", error);
    if (error instanceof Error && error.name === "Unauthorized") {
      return jsonResponse({ error: "Unauthorized." }, 401);
    }
    return jsonResponse({ error: "Server error." }, 500);
  }
});
