export type ActionType = "yes_no" | "text" | "audio" | "instructor";

export interface ScenarioListItem {
  file_name: string;
  id: string;
  name: string;
  version: string;
}

export interface ActionSummary {
  id: string;
  type: ActionType;
  prompt?: string | null;
  options: string[];
  transcript_required: boolean;
  metadata: Record<string, unknown>;
}

export interface TimerSummary {
  id: string;
  duration_seconds: number;
  event: string;
  auto_start: boolean;
  metadata: Record<string, unknown>;
}

export interface TransitionSummary {
  id: string;
  trigger: string;
  target_state: string;
  action_id?: string | null;
  timer_id?: string | null;
  instructor_event?: string | null;
  metadata: Record<string, unknown>;
}

export interface CurrentState {
  id: string;
  name: string;
  description?: string | null;
  actions: ActionSummary[];
  timers: TimerSummary[];
  transitions: TransitionSummary[];
  metadata: Record<string, unknown>;
}

export interface SessionResponse {
  session_id: string;
  scenario_id: string;
  status: string;
  current_state: CurrentState;
}

export interface SessionStateResponse extends SessionResponse {
  history: Array<Record<string, unknown>>;
}

export interface ActiveSessionItem {
  session_id: string;
  scenario_id: string;
  scenario_name: string;
  status: string;
  current_state_id: string;
}

export interface SessionMetrics {
  session_id: string;
  total_duration_seconds: number;
  student_input_count: number;
  voice_input_count: number;
  successful_transition_count: number;
  no_transition_count: number;
  instructor_intervention_count: number;
  timer_event_count: number;
  completion_status: string;
}

export interface RuntimeEvent {
  type: string;
  event_id?: string;
  sequence?: number;
  timestamp?: string;
  source?: string;
  payload?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}
