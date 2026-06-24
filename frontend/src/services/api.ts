import type { ActiveSessionItem, ScenarioListItem, SessionMetrics, SessionResponse, SessionStateResponse } from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {})
    },
    ...init
  });

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `Request failed with ${response.status}`);
  }

  return response.json() as Promise<T>;
}

export async function listScenarios(): Promise<ScenarioListItem[]> {
  return request<ScenarioListItem[]>("/api/scenarios/scenarios");
}

export async function startSession(scenarioId: string): Promise<SessionResponse> {
  return request<SessionResponse>("/api/sessions/sessions/start", {
    method: "POST",
    body: JSON.stringify({ scenario_id: scenarioId })
  });
}

export async function getSession(sessionId: string): Promise<SessionStateResponse> {
  return request<SessionStateResponse>(`/api/sessions/sessions/${sessionId}`);
}

export async function submitStudentInput(
  sessionId: string,
  actionId: string,
  response: string | boolean
): Promise<SessionResponse> {
  return request<SessionResponse>(`/api/sessions/sessions/${sessionId}/input`, {
    method: "POST",
    body: JSON.stringify({ action_id: actionId, response })
  });
}

export async function triggerTimer(
  sessionId: string,
  timerId: string
): Promise<SessionResponse> {
  return request<SessionResponse>(`/api/sessions/sessions/${sessionId}/timer/${timerId}`, {
    method: "POST"
  });
}

export async function stopSession(sessionId: string): Promise<SessionResponse> {
  return request<SessionResponse>(`/api/sessions/sessions/${sessionId}/stop`, {
    method: "POST"
  });
}

export async function listSessions(): Promise<ActiveSessionItem[]> {
  return request<ActiveSessionItem[]>("/api/sessions/sessions");
}

export async function sendInstructorEvent(
  sessionId: string,
  eventName: string
): Promise<SessionResponse> {
  return request<SessionResponse>(`/api/sessions/sessions/${sessionId}/instructor`, {
    method: "POST",
    body: JSON.stringify({ event_name: eventName })
  });
}

export async function getSessionMetrics(sessionId: string): Promise<SessionMetrics> {
  return request<SessionMetrics>(`/api/sessions/sessions/${sessionId}/metrics`);
}

export async function downloadSessionCsv(sessionId: string): Promise<Blob> {
  const response = await fetch(
    `${API_BASE_URL}/api/sessions/sessions/${sessionId}/export/csv`
  );

  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `CSV export failed with ${response.status}`);
  }

  return response.blob();
}
