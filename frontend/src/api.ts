/**
 * The ONLY file that asks the backend for data. Every screen imports from here.
 *
 * It has an internal switch between fake data and the real backend:
 *   - fake (default): answers come from src/mockData.ts, no backend needed.
 *   - real: fetch() calls to the FastAPI backend.
 * Change it with VITE_USE_MOCK in frontend/.env.local (see .env.example), then
 * restart `npm run dev`. The screens do not change.
 */
import { MOCK_DRAFTS, MOCK_JOBS, MOCK_LEADS, MOCK_USERS } from "./mockData";
import type { Draft, Job, Lead, TokenOut, User } from "./types";

/** true = fake data. Only the exact text "false" switches to the real backend. */
export const USE_MOCK: boolean = import.meta.env.VITE_USE_MOCK !== "false";
const API_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

/**
 * Paths of the real backend. PROPOSAL: the backend has no routes yet (backend/api
 * is empty). When they exist, fix the paths here, in this one place.
 */
const ENDPOINTS = {
  login: "/api/auth/login",
  me: "/api/auth/me",
  jobs: "/api/jobs",
  leads: "/api/leads",
  leadDraft: (leadId: number) => `/api/leads/${leadId}/draft`,
};

// ---------- login token ----------

const TOKEN_KEY = "openrec_token";

function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}
function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

// ---------- real backend ----------

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(API_URL + path, { ...init, headers });
  if (!response.ok) {
    throw new ApiError(response.status, (await response.text()) || response.statusText);
  }
  return (await response.json()) as T;
}

// ---------- fake backend ----------

const MOCK_DELAY_MS = 150; // small delay, so loading states can be seen and tested

async function mock<T>(value: T): Promise<T> {
  await new Promise((resolve) => setTimeout(resolve, MOCK_DELAY_MS));
  return structuredClone(value); // a copy, so a screen cannot change the fake data
}

function mockUserFromToken(): User | null {
  const token = getToken();
  if (!token?.startsWith("mock:")) return null;
  return MOCK_USERS.find((u) => u.user_id === Number(token.slice(5))) ?? null;
}

// ---------- what the screens call ----------

/** Log in. Real: POST login, then ask who we are. Fake: any password, the email picks the user. */
export async function login(email: string, password: string): Promise<User> {
  if (USE_MOCK) {
    const user = MOCK_USERS.find((u) => u.email === email.trim().toLowerCase());
    if (!user || !password) {
      // like the real screen: do not say which field is wrong
      throw new ApiError(401, "Wrong email or password");
    }
    setToken(`mock:${user.user_id}`);
    return mock(user);
  }
  const body = JSON.stringify({ email: email.trim().toLowerCase(), password });
  const token = await request<TokenOut>(ENDPOINTS.login, { method: "POST", body });
  setToken(token.access_token);
  return request<User>(ENDPOINTS.me);
}

export async function logout(): Promise<void> {
  clearToken();
}

/** The logged-in user, or null if nobody is logged in (or the token expired). */
export async function getCurrentUser(): Promise<User | null> {
  if (!getToken()) return null;
  if (USE_MOCK) {
    const user = mockUserFromToken();
    if (!user) clearToken();
    return user ? mock(user) : null;
  }
  try {
    return await request<User>(ENDPOINTS.me);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      clearToken();
      return null;
    }
    throw error;
  }
}

export function getJobs(): Promise<Job[]> {
  return USE_MOCK ? mock(MOCK_JOBS) : request<Job[]>(ENDPOINTS.jobs);
}

/** Leads ordered by lead score, highest first. */
export function getLeads(): Promise<Lead[]> {
  if (USE_MOCK) return mock([...MOCK_LEADS].sort((a, b) => b.lead_score - a.lead_score));
  return request<Lead[]>(ENDPOINTS.leads);
}

/** The newest draft of a lead, or null if it has none yet. */
export async function getLeadDraft(leadId: number): Promise<Draft | null> {
  if (USE_MOCK) {
    const drafts = MOCK_DRAFTS.filter((d) => d.lead_id === leadId);
    return mock(drafts.sort((a, b) => b.version - a.version)[0] ?? null);
  }
  try {
    return await request<Draft>(ENDPOINTS.leadDraft(leadId));
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}