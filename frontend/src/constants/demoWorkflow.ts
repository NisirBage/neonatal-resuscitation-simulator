export interface WorkflowStep {
  label: string;
  stateIds: string[];
}

export const PROFESSOR_WORKFLOW_STEPS: WorkflowStep[] = [
  { label: "Baby Born",       stateIds: ["baby_born"] },
  { label: "Positioning",     stateIds: ["put_on_mothers_chest"] },
  { label: "Crying?",         stateIds: ["crying_assessment"] },
  { label: "Apnea?",          stateIds: ["apnea_assessment"] },
  { label: "Heart Rate",      stateIds: ["heart_rate_assessment"] },
  {
    label: "Ventilation",
    stateIds: [
      "ventilation_path",
      "ventilation_in_progress",
      "ventilation_corrective_steps"
    ]
  },
  {
    label: "Reassessment",
    stateIds: [
      "heart_rate_after_ventilation",
      "continue_ventilation_15s"
    ]
  },
  { label: "Complete",        stateIds: ["simulation_complete", "routine_care"] }
];

export type WorkflowStepStatus = "complete" | "current" | "pending";

export function getWorkflowStepIndex(stateId: string | null | undefined): number {
  if (!stateId) return -1;
  return PROFESSOR_WORKFLOW_STEPS.findIndex((step) => step.stateIds.includes(stateId));
}

export function getWorkflowStepStatus(
  stepIndex: number,
  currentStateId: string | null | undefined
): WorkflowStepStatus {
  const currentStepIndex = getWorkflowStepIndex(currentStateId);
  if (currentStepIndex === -1) return "pending";
  if (stepIndex < currentStepIndex) return "complete";
  if (stepIndex === currentStepIndex) return "current";
  return "pending";
}
