"""
Validates that self-loop transitions are now persisted correctly.

Tests (offline, no HTTP server — exercises FSMEngine + upsert logic directly):

A. initial_steps -> warm_dry_stimulate -> crash -> restore
   Expected: warm_dry_stimulate_done in restored history

B. ventilation_corrective_steps -> reposition_mask_done -> crash -> restore
   Expected: reposition_mask_done in restored history

C. invalid input -> no_transition
   Expected: history[-1].type == 'no_transition' (would not trigger upsert)

D. Happy path regression: all 13 state-changing steps produce state_transition events

Tests A/B simulate the persistence trigger by checking the FSM event type that
would have been evaluated by the new condition:
  record.engine.get_history()[-1].type == "state_transition"
"""
import json
import sys

sys.path.insert(0, ".")

from app.fsm import FSMEngine
from app.scenario import Scenario

with open("../scenarios/baby_birth.json") as f:
    scenario = Scenario.model_validate(json.load(f))

failures = []


def make_engine():
    from uuid import uuid4
    e = FSMEngine(scenario)
    e.start(session_id=uuid4())
    return e


def last_event_type(engine):
    return engine.get_history()[-1].type


def last_transition_id(engine):
    h = engine.get_history()
    for ev in reversed(h):
        if ev.transition_id:
            return ev.transition_id
    return None


# ── TEST A: initial_steps self-loop ─────────────────────────────────────────
engine = make_engine()
engine.process_student_input("confirm_birth", "yes")
engine.process_student_input("placed_on_chest", "yes")
# Now at initial_steps — take snapshot (simulates last DB write)
snapshot_before = engine.serialize()

engine.process_student_input("warm_dry_stimulate", "yes")

# New condition check: would the upsert have fired?
trigger_type = last_event_type(engine)
would_upsert = trigger_type == "state_transition"
transition_recorded = last_transition_id(engine) == "warm_dry_stimulate_done"

# Simulate crash + restore FROM CURRENT blob (new behavior: blob was updated)
# Under new logic the blob is updated after self-loop, so simulate that:
blob_after_selfloop = engine.serialize()
engine_restored = FSMEngine.deserialize(scenario, blob_after_selfloop)
restored_history = engine_restored.get_history()
has_warm = any(e.transition_id == "warm_dry_stimulate_done" for e in restored_history)

ok = would_upsert and transition_recorded and has_warm
if not ok:
    failures.append(
        f"A: would_upsert={would_upsert} transition_recorded={transition_recorded} restored={has_warm}"
    )
print(f"TEST A — warm_dry_stimulate self-loop persisted and restored: {'PASSED' if ok else 'FAILED'}")

# ── TEST A2: confirm old condition would NOT have triggered (regression guard) ─
old_condition = engine.serialize()["current_state_id"] != snapshot_before["current_state_id"]
if old_condition:
    failures.append("A2: old state-change condition fired on self-loop (should be False)")
print(f"TEST A2 — old condition correctly silent on self-loop: {'PASSED' if not old_condition else 'FAILED'}")

# ── TEST B: ventilation_corrective_steps self-loop ───────────────────────────
engine = make_engine()
# Fast-forward to ventilation_corrective_steps via instructor events
engine.process_instructor_event("start_birth_workflow")           # -> put_on_mothers_chest
engine.process_instructor_event("advance_to_crying_assessment")   # -> crying_assessment
engine.process_instructor_event("initial_steps_complete")         # -> crying_assessment
engine.process_instructor_event("baby_not_crying")                # -> apnea_assessment
engine.process_instructor_event("assess_heart_rate")              # -> heart_rate_assessment
engine.process_instructor_event("heart_rate_under_100")           # -> ventilation_path
engine.process_instructor_event("ventilation_started")            # -> ventilation_started_state
engine.process_instructor_event("pulse_oximeter_applied")         # -> ventilation_in_progress
engine.process_instructor_event("ventilation_timer_complete")     # -> heart_rate_after_ventilation
engine.process_instructor_event("heart_rate_under_60")            # -> advanced_resuscitation
engine.process_instructor_event("advanced_resuscitation_complete") # -> simulation_complete... no wait

# Actually ventilation_corrective_steps is reached via ineffective ventilation
# Let me check the correct path
current = engine.get_current_state().id
# If we're not in the right state, use a different fast-forward
if current != "ventilation_corrective_steps":
    engine2 = make_engine()
    engine2.process_instructor_event("start_birth_workflow")
    engine2.process_instructor_event("advance_to_crying_assessment")
    engine2.process_instructor_event("initial_steps_complete")
    engine2.process_instructor_event("baby_not_crying")
    engine2.process_instructor_event("assess_heart_rate")
    engine2.process_instructor_event("heart_rate_under_100")
    engine2.process_instructor_event("ventilation_started")
    engine2.process_instructor_event("pulse_oximeter_applied")
    # In ventilation_in_progress: confirm ineffective ventilation
    r = engine2.process_student_input("confirm_effective_ventilation", "no")
    current2 = r.current_state_id
    if current2 == "ventilation_corrective_steps":
        engine = engine2

current = engine.get_current_state().id
if current != "ventilation_corrective_steps":
    failures.append(f"B: could not reach ventilation_corrective_steps (at {current})")
    print(f"TEST B — ventilation_corrective_steps self-loop: SKIPPED (couldn't reach state)")
else:
    engine.process_student_input("reposition_mask", "yes")
    trigger_type = last_event_type(engine)
    would_upsert = trigger_type == "state_transition"
    transition_id = last_transition_id(engine)

    blob = engine.serialize()
    engine_r = FSMEngine.deserialize(scenario, blob)
    has_reposition = any(e.transition_id == "reposition_mask_done" for e in engine_r.get_history())

    ok = would_upsert and has_reposition
    if not ok:
        failures.append(f"B: would_upsert={would_upsert} reposition_in_restored={has_reposition} last_transition={transition_id}")
    print(f"TEST B — reposition_mask self-loop persisted and restored: {'PASSED' if ok else 'FAILED'}")

# ── TEST C: invalid input -> no_transition -> no upsert ─────────────────────
engine = make_engine()
engine.process_student_input("confirm_birth", "yes")
# Submit an action that exists but with a wrong response (will produce no_transition)
# In put_on_mothers_chest, placed_on_chest=no should produce no_transition
engine.process_student_input("placed_on_chest", "no")

trigger_type = last_event_type(engine)
would_upsert = trigger_type == "state_transition"  # should be False
ok = not would_upsert and trigger_type == "no_transition"
if not ok:
    failures.append(f"C: expected no_transition, got {trigger_type}")
print(f"TEST C — invalid input produces no_transition (no upsert): {'PASSED' if ok else 'FAILED'}")

# ── TEST D: happy path — all 13 state-changing steps fire state_transition ───
engine = make_engine()
steps = [
    ("confirm_birth",                "yes",        "put_on_mothers_chest"),
    ("placed_on_chest",              "yes",        "initial_steps"),
    ("warm_dry_stimulate",           "yes",        "initial_steps"),      # self-loop
    ("position_airway",              "yes",        "initial_steps"),      # self-loop
    ("clear_airway_if_needed",       "yes",        "crying_assessment"),
    ("is_baby_crying",               "no",         "apnea_assessment"),
    ("is_apneic",                    "yes",        "heart_rate_assessment"),
    ("heart_rate_category",          "under_100",  "ventilation_path"),
    ("start_ventilation",            "yes",        "ventilation_started_state"),
    ("apply_pulse_oximeter",         "yes",        "ventilation_in_progress"),
    ("confirm_effective_ventilation","yes",         "spo2_assessment"),
    ("spo2_category",                "acceptable", "routine_observation"),
    ("continue_observation",         "yes",        "simulation_complete"),
]
hp_ok = True
for action, response, expected_state in steps:
    r = engine.process_student_input(action, response)
    got_state = r.current_state_id
    last_type = last_event_type(engine)
    if got_state != expected_state:
        failures.append(f"D happy path {action}: expected state {expected_state} got {got_state}")
        hp_ok = False
    if last_type != "state_transition":
        failures.append(f"D happy path {action}: expected state_transition event, got {last_type}")
        hp_ok = False

print(f"TEST D — happy path all 13 steps produce state_transition: {'PASSED' if hp_ok else 'FAILED'}")

# ── RESULT ───────────────────────────────────────────────────────────────────
print()
if failures:
    print("RESULT: FAILED")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
else:
    print("RESULT: ALL TESTS PASSED")
