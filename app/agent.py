"""The agent: Gemini decides which tools to call, our code runs them,
and a guardrail in code checks the critical rules afterwards (option C).

Agent loop (manual, so every step is visible):
  1. Send the conversation + the tool descriptions to Gemini.
  2. If Gemini asks for tools -> run them, add the results, go to 1.
  3. If Gemini answers with text -> it has finished.
  4. Stop anyway after MAX_ITERATIONS rounds.
"""

import sys
from dataclasses import dataclass, field

from google import genai
from google.genai import errors, types

from app.config import load_config, load_fallback_models
from app.rules import Expected, evaluate
from app.tools import (
    ACTION_LOG,
    HUMAN_NOTIFICATIONS,
    SENT_EMAILS,
    TOOLS,
    get_shipment,
    log_action,
    notify_human,
    record_guardrail,
    reset_outbox,
    send_customer_email,
)

# Normal case needs ~5 rounds. The limit protects against a confused model
# calling tools forever (cost, repeated emails).
MAX_ITERATIONS = 8

SYSTEM_PROMPT = """You are a customer service agent for a mid-sized logistics operator.
You handle shipment events using ONLY the tools you have.

How to work:
1. ALWAYS start by calling get_shipment with the shipment_id you receive.
   Use that shipment_id EXACTLY as received in every tool call: never
   modify, reformat or "correct" it.
2. Decide what to do with the business rules below and act with the tools.
3. Record EVERY action you take with log_action (one call per action).
4. When you are done, reply with a one-line summary and call no more tools.

Business rules:
1. Only act on shipments with status "retrasado". Otherwise log "no_action"
   and do nothing else.
2. If the shipment does not exist, log "error" and do nothing else
   (no email, no escalation).
3. For delayed shipments ALWAYS email the customer (send_customer_email),
   EVEN WHEN you also escalate: apologise, explain the reason, and state the
   delay (delay_hours) and the original expected_date. Professional tone, in
   the customer's language ("es" = Spanish, "en" = English).
   The ONLY exception: the customer has no contact_email or does not exist.
   Then do NOT email; only escalate.
4. ALSO escalate with notify_human if ANY of these is true:
   - delay_hours > 24
   - customer priority is "alta"
   - data is missing or inconsistent (no contact_email, customer not found...)
   The escalation message must include the shipment_id, the customer name and
   exactly which rule applies with its value (e.g. "delay_hours 30 > 24").
5. Never invent data (new dates, compensations, discounts) that is not in the
   tool results.

Email style:
- Greet the customer by their company name (never "Dear customer").
- Separate paragraphs with line breaks.
- Never mention internal processes (such as escalation) and never promise
  actions that are not in the data.

Example: delay 30 h, normal customer, has contact_email ->
get_shipment -> send_customer_email -> log_action(email_sent)
-> notify_human -> log_action(escalated) -> one-line summary.
"""


@dataclass
class ToolCall:
    """One tool call made during the run."""

    name: str
    args: dict
    result: dict


@dataclass
class AgentRun:
    """Everything that happened in one run of the agent."""

    shipment_id: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    final_text: str = ""
    iterations: int = 0
    hit_iteration_limit: bool = False
    model_used: str = ""


def execute_tool(name: str, args: dict) -> dict:
    """Run the tool the model asked for. Never let an exception stop the loop."""
    tool = TOOLS.get(name)
    if tool is None:
        return {"ok": False, "error": f"unknown tool {name!r}"}
    try:
        return tool(**args)
    except Exception as error:  # returned to the model as data, like any error
        return {"ok": False, "error": f"tool {name} failed: {type(error).__name__}: {error}"}


def _should_switch_model(error: errors.APIError) -> bool:
    """5xx = Google's side (overloaded). 429 = quota, which is PER MODEL.

    Any other 4xx is our fault (bad request, bad key...): another model
    won't fix it, so we don't switch.
    """
    return isinstance(error, errors.ServerError) or error.code == 429


def _generate(client, run: AgentRun, models: list[str], contents, config):
    """Call Gemini; if the model is overloaded or out of quota, move to the
    next one in the list and keep it for the rest of this run."""
    while True:
        try:
            return client.models.generate_content(
                model=models[0], contents=contents, config=config
            )
        except errors.APIError as error:
            if not _should_switch_model(error) or len(models) == 1:
                raise
            print(f"[FALLBACK] {models[0]} failed ({error.code}), switching to {models[1]}")
            models.pop(0)  # the backup becomes the model for the rest of the run
            run.model_used = models[0]


def check_shipment_id(args: dict, expected: str) -> dict | None:
    """Block a tool call whose shipment_id differs from the event's one.

    The prompt asks the model not to change it; this makes sure in code.
    Returns an error for the model, or None if the call can run.
    """
    given = args.get("shipment_id")
    if given is not None and given != expected:
        return {
            "ok": False,
            "error": f"shipment_id must be exactly {expected!r}, got {given!r}. "
            "Use it unchanged.",
        }
    return None


def run_agent(
    shipment_id: str,
    client: genai.Client | None = None,
    model: str | None = None,
    fallback_models: list[str] | None = None,
) -> AgentRun:
    """Handle one shipment event with the agent loop."""
    if client is None or model is None:
        api_key, model = load_config()
        client = genai.Client(api_key=api_key)
    if fallback_models is None:
        fallback_models = load_fallback_models()
    # Main model first, then the backups (without repeating the main one).
    models = [model] + [name for name in fallback_models if name != model]

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        # The SDK turns each function (name, typed params, docstring) into the
        # tool description the model reads.
        tools=[get_shipment, send_customer_email, notify_human, log_action],
        # We run the loop ourselves: visible steps, our own limit, guardrail later.
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    # The conversation grows each round: user -> model -> tool results -> model...
    contents: list[types.Content] = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=f"New shipment event. shipment_id: {shipment_id}")],
        )
    ]
    run = AgentRun(shipment_id=shipment_id, model_used=models[0])

    for iteration in range(1, MAX_ITERATIONS + 1):
        run.iterations = iteration
        response = _generate(client, run, models, contents, config)

        calls = response.function_calls
        if not calls:  # plain text = the model has finished
            run.final_text = response.text or ""
            return run

        # Keep the model's turn (with its tool requests) in the conversation.
        contents.append(response.candidates[0].content)

        result_parts = []
        for call in calls:
            args = dict(call.args or {})
            # Wrong shipment_id -> the tool is NOT run, the model gets an error.
            result = check_shipment_id(args, shipment_id) or execute_tool(call.name, args)
            run.tool_calls.append(ToolCall(name=call.name, args=args, result=result))
            result_parts.append(types.Part.from_function_response(name=call.name, response=result))
        # Send the results back so the model can decide the next step.
        # Gemini only accepts "user" and "model" turns: tool results travel
        # on our side of the conversation, as "user".
        contents.append(types.Content(role="user", parts=result_parts))

    run.hit_iteration_limit = True
    return run


@dataclass
class GuardrailReport:
    """What the guardrail found and fixed after the agent finished."""

    expected: Expected
    corrections: list[str] = field(default_factory=list)  # fixed by code
    discrepancies: list[str] = field(default_factory=list)  # only recorded

    @property
    def intervened(self) -> bool:
        return bool(self.corrections or self.discrepancies)


def apply_guardrail(shipment_id: str) -> GuardrailReport:
    """Compare what the agent DID (the outbox) with what rules.py says SHOULD happen."""
    # 1. What should happen: same facts the agent saw, judged by code (no LLM).
    facts = get_shipment(shipment_id)
    expected = evaluate(facts.get("shipment"), facts.get("customer"))
    report = GuardrailReport(expected=expected)

    # 2. What really happened: successful actions only (a rejected email didn't happen).
    did_email = bool(SENT_EMAILS)
    did_escalate = bool(HUMAN_NOTIFICATIONS)
    did_log = bool(ACTION_LOG)

    # 3. Compare. Under-escalating is costly -> fix it. Over-escalating is cheap -> record it.
    must_escalate: list[str] = []
    if expected.escalate and not did_escalate:
        must_escalate.append("; ".join(expected.reasons))
    if did_escalate and not expected.escalate:
        report.discrepancies.append("agent escalated but no rule requires it")
    if expected.send_email and not did_email:
        report.discrepancies.append("agent did not email the customer")
        must_escalate.append("customer was not emailed, a human must contact them")
    if did_email and not expected.send_email:
        report.discrepancies.append("agent emailed the customer but the rules say it should not")
        must_escalate.append("customer was emailed against the rules")

    for discrepancy in report.discrepancies:
        record_guardrail(shipment_id, f"guardrail: {discrepancy}")

    if must_escalate:
        reason = " | ".join(must_escalate)
        notify_human(f"[GUARDRAIL] {shipment_id}: {reason}")
        log_action(shipment_id, "escalated", f"guardrail correction: {reason}",
                   "escalated by code, the agent did not do it")
        report.corrections.append(f"escalated by code: {reason}")

    # Rule 4: every case leaves a trace. If the agent logged nothing, code does.
    if not did_log:
        if facts.get("ok") is False:
            action = "error"
        elif not expected.action_required:
            action = "no_action"
        elif did_email:
            action = "email_sent"
        elif did_escalate:
            action = "escalated"
        else:
            action = "error"
        log_action(shipment_id, action, "guardrail correction: agent did not log its action",
                   "row written by code")
        report.corrections.append(f"missing log written by code ({action})")

    return report


def handle_shipment(
    shipment_id: str,
    client: genai.Client | None = None,
    model: str | None = None,
) -> tuple[AgentRun, GuardrailReport]:
    """Full flow for one shipment: clean id -> empty outbox -> agent -> guardrail."""
    # Normalise the FORMAT in code (our rule: ids are uppercase, no spaces).
    # Never "guess" a similar id: if it doesn't exist, it is an error.
    shipment_id = shipment_id.strip().upper()
    reset_outbox()
    run = run_agent(shipment_id, client=client, model=model)
    report = apply_guardrail(shipment_id)
    return run, report


if __name__ == "__main__":
    # Quick manual test: python -m app.agent ENV-1002
    sid = sys.argv[1] if len(sys.argv) > 1 else "ENV-1001"
    result, guard = handle_shipment(sid)
    print(f"\n--- {sid}: {result.iterations} rounds, limit hit: {result.hit_iteration_limit}, model: {result.model_used}")
    for i, c in enumerate(result.tool_calls, 1):
        print(f"{i}. {c.name}({c.args}) -> ok={c.result.get('ok')}")
    print(f"Final: {result.final_text}")
    print(f"Guardrail intervened: {guard.intervened}")
    for item in guard.corrections:
        print(f"  correction: {item}")
    for item in guard.discrepancies:
        print(f"  discrepancy: {item}")
