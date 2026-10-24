"""The agent: Gemini decides which tools to call, our code runs them,
and a guardrail in code checks the critical rules afterwards (option C).

Agent loop (manual, so every step is visible):
  1. Send the conversation + the tool descriptions to Gemini.
  2. If Gemini asks for tools -> run them, add the results, go to 1.
  3. If Gemini answers with text -> it has finished.
  4. Stop anyway after MAX_ITERATIONS rounds.
"""

import inspect
import sys
from dataclasses import dataclass, field

from google import genai
from google.genai import errors, types

from app.config import load_config, load_fallback_models
from app.rules import Expected, evaluate
from app.tools import (
    ACTION_LOG,
    GUARDRAIL_ACTION,
    HUMAN_NOTIFICATIONS,
    SENT_EMAILS,
    deliver_alert,
    is_judgment,
    lookup_shipment,
    make_tools,
    record_action,
    record_guardrail,
    reset_outbox,
)

# Normal case needs ~5 rounds. The limit protects against a confused model
# calling tools forever (cost, repeated emails).
MAX_ITERATIONS = 8

SYSTEM_PROMPT = """You are a customer service agent for a mid-sized logistics operator.
You handle shipment events using ONLY the tools you have.

How to work:
1. ALWAYS start by calling get_shipment. Your tools already work on the
   shipment of this event: you never pass a shipment_id.
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
   the customer's language ("es" = Spanish, "en" = English). The tool already
   knows the customer's address: you only write subject and body.
   The reason: delay_reason is an INTERNAL note for our staff. Never copy it.
   Tell the customer the cause in general, customer-friendly words (e.g. "a
   vehicle breakdown", "congestion at the port"), written in the customer's
   language, with NO internal details: no police reports, no people's names,
   no names of our warehouses or distribution centres, no internal processes.
   New delivery date: if new_eta has a date, give it as the new estimated
   delivery date. If new_eta is empty, say you will let them know the new
   date as soon as you have it. Never invent or estimate a date yourself.
   The ONLY exceptions, where you do NOT send the email:
   - the data is missing or inconsistent (no contact_email, customer not
     found, new_eta that is not a valid YYYY-MM-DD date): only escalate.
   - you escalate by judgment (rule 6).
   In both cases, and also if send_customer_email fails or is refused, pass
   the email you would have sent as email_draft in notify_human ("Subject:
   ..." line, blank line, body; same style rules): the human gets the work
   half done and may reach the customer another way.
4. ALSO escalate with notify_human if ANY of these is true:
   - delay_hours > 24
   - customer priority is "alta"
   - data is missing or inconsistent (no contact_email, customer not found,
     new_eta that is not a valid YYYY-MM-DD date...)
   The escalation message must include the customer name and exactly which
   rule applies with its value (e.g. "delay_hours 30 > 24"). The code also
   attaches the rules it checked; never guess a value you did not see.
   Whenever the customer was NOT emailed, include email_draft (rule 3).
5. Never invent data (new dates, compensations, discounts) that is not in the
   tool results.
6. Judgment. These rules can't foresee everything. If delay_reason describes
   something serious for the customer (theft, loss or damage of the goods, an
   accident, no way to estimate the delivery), ALSO escalate with
   notify_human, even if no rule in 4 applies (and also if one does).
   Start the message with "JUDGMENT:" and explain why in one or two sentences
   (mention any rule from 4 that also applies). Do NOT send the email: pass
   it as email_draft ("Subject: ..." line, blank line, body; same style
   rules) so a human reviews it first. Ordinary causes (breakdown, traffic, weather, congestion) are NOT
   judgment cases: follow rules 3 and 4.

Email style:
- Greet the customer by their company name (never "Dear customer").
- Separate paragraphs with line breaks.
- Never mention internal processes (such as escalation) and never promise
  actions that are not in the data.

Examples:
- delay 30 h, normal customer, has contact_email ->
  get_shipment -> send_customer_email -> log_action(email_sent)
  -> notify_human -> log_action(escalated) -> one-line summary.
- customer has no contact_email ->
  get_shipment -> notify_human("...", email_draft="Subject: ...")
  -> log_action(escalated) -> one-line summary.
- delay 6 h, delay_reason says the goods were lost ->
  get_shipment -> notify_human("JUDGMENT: ...", email_draft="Subject: ...")
  -> log_action(escalated) -> one-line summary.
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


def execute_tool(tools: dict, name: str, args: dict) -> dict:
    """Run the tool the model asked for. Never let an exception stop the loop.

    Three kinds of failure, told apart on purpose:
    - unknown tool or arguments that don't match its signature -> the AGENT's
      mistake ("agent_error"): checked BEFORE calling, so a TypeError raised
      inside a tool (a real bug or a provider crash) is never blamed on it;
    - an exception inside the tool -> "technical" (not the agent's fault);
    - a tool's own validation (e.g. empty subject) -> plain ok=False.
    """
    tool = tools.get(name)
    if tool is None:
        return {"ok": False, "error": f"unknown tool {name!r}, available: {sorted(tools)}",
                "agent_error": True}
    signature = inspect.signature(tool)
    try:
        signature.bind(**args)  # same check Python does on a call, without calling
    except TypeError as error:
        # e.g. the model invents shipment_id or forgets subject. The expected
        # signature goes back to the model so it can fix the call next round.
        return {"ok": False,
                "error": f"invalid arguments for {name}: {error}. Expected: {name}{signature}",
                "agent_error": True}
    try:
        return tool(**args)
    except Exception as error:  # returned to the model as data, like any error
        # "technical": the tool crashed (e.g. provider down). Not the same as a
        # validation error (bad input from the model): the guardrail treats it
        # as a legitimate reason to escalate, not as an agent mistake.
        return {
            "ok": False,
            "error": f"tool {name} failed: {type(error).__name__}: {error}",
            "technical": True,
        }


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


def run_agent(
    shipment_id: str,
    client: genai.Client | None = None,
    model: str | None = None,
    fallback_models: list[str] | None = None,
    event_id: str = "",
) -> AgentRun:
    """Handle one shipment event with the agent loop.

    event_id (phase 4): the webhook notice that started this run, if any.
    It only travels inside the tools to build the email idempotency key.
    """
    if client is None or model is None:
        api_key, model = load_config()
        client = genai.Client(api_key=api_key)
    if fallback_models is None:
        fallback_models = load_fallback_models()
    # Main model first, then the backups (without repeating the main one).
    models = [model] + [name for name in fallback_models if name != model]

    # Tools for THIS shipment only: the id travels inside them, the model never
    # writes it (so it cannot change it).
    tools = make_tools(shipment_id, event_id)

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        # The SDK turns each function (name, typed params, docstring) into the
        # tool description the model reads.
        tools=list(tools.values()),
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
            result = execute_tool(tools, call.name, args)
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


def apply_guardrail(shipment_id: str, run: AgentRun | None = None) -> GuardrailReport:
    """Compare what the agent DID (the outbox) with what rules.py says SHOULD happen.

    `run` lets us see what the agent TRIED (tool_calls), not only what worked:
    "didn't try" and "tried but the tool failed" are different things.
    """
    # 1. What should happen: same facts the agent saw, judged by code (no LLM).
    try:
        facts = lookup_shipment(shipment_id)
    except Exception as error:
        # The data source failed (e.g. the Sheet is not shared). We can't
        # judge the case, and it's not the agent's fault: a human must know.
        facts = {"ok": False, "error": f"{type(error).__name__}: {error}", "technical": True}
        print(f"[GUARDRAIL] could not read the shipment data: {facts['error']}")
    data_unreadable = bool(facts.get("technical"))
    expected = evaluate(facts.get("shipment"), facts.get("customer"))
    report = GuardrailReport(expected=expected)

    # 2. What really happened: successful actions only (a rejected email didn't happen).
    did_email = bool(SENT_EMAILS)
    did_escalate = bool(HUMAN_NOTIFICATIONS)
    # Only the agent's own actions count as "logged": an informative
    # "guardrail" row (e.g. the alert went by email, phase 5) written during
    # the run must not hide that the agent logged nothing.
    did_log = any(row["action"] != GUARDRAIL_ACTION for row in ACTION_LOG)
    # Escalations by judgment (rule 6): the agent saw something serious the
    # rules don't cover. rules.py can't predict them, so they are accepted.
    judgment_alerts = [n for n in HUMAN_NOTIFICATIONS if is_judgment(n["message"])]
    judgment = bool(judgment_alerts)
    # Technical failures: a tool crashed (e.g. email provider down). Not the
    # agent's fault, and a legitimate reason for the agent to escalate.
    calls = run.tool_calls if run else []
    failed_tools = sorted({call.name for call in calls if call.result.get("technical")})
    technical_failure = bool(failed_tools)
    for name in failed_tools:  # informative, to measure how often providers fail
        record_guardrail(shipment_id, f"technical failure in {name} (not an agent error)")
    # Agent errors: unknown tool or invalid arguments. Only recorded (the
    # agent got the error back and could retry): measures how often it fails.
    invalid_calls = sorted({call.name for call in calls if call.result.get("agent_error")
                            and not call.result.get("refused_by_rules")})
    for name in invalid_calls:
        record_guardrail(shipment_id, f"agent error: invalid call to {name}")
    # Email refused BEFORE sending (prevent > detect): nothing reached the
    # customer, but the agent tried. Recorded separately to measure it.
    refused = [call for call in calls if call.result.get("refused_by_rules")]
    if refused:
        record_guardrail(shipment_id, "agent error: tried to email against the rules (refused)",
                         refused[0].result["error"][:300])

    # 3. Compare. Under-escalating is costly -> fix it. Over-escalating is cheap -> record it.
    must_escalate: list[str] = []
    if data_unreadable:
        must_escalate.append("shipment data could not be read (technical failure)")
    if expected.escalate and not did_escalate:
        must_escalate.append("; ".join(expected.reasons))
    if (did_escalate and not expected.escalate and not judgment
            and not technical_failure and not data_unreadable):
        report.discrepancies.append("agent escalated but no rule requires it")
    if judgment:
        # Always recorded (not an error): lets us measure how often the agent
        # uses judgment; repeated situations should become rules in rules.py.
        record_guardrail(shipment_id, "judgment escalation (accepted)",
                         judgment_alerts[0]["message"][:300])
        if did_email:
            report.discrepancies.append("agent emailed the customer despite escalating by judgment")
    # Escalating by judgment replaces the email (the draft goes to the human).
    if expected.send_email and not did_email and not judgment:
        if "send_customer_email" in failed_tools:
            # It tried and the provider failed: not a discrepancy, but the
            # customer still has no notice, so a human must know.
            must_escalate.append("customer could not be emailed (technical failure)")
        else:
            report.discrepancies.append("agent did not email the customer")
            must_escalate.append("customer was not emailed, a human must contact them")
    # Decision 2: every escalation without an email carries the draft, so the
    # human gets the work half done. Only recorded: an alert is never blocked.
    if (did_escalate and not did_email and expected.action_required
            and not any(n["email_draft"].strip() for n in HUMAN_NOTIFICATIONS)):
        report.discrepancies.append("escalated without emailing and without an email draft")
    if did_email and not expected.send_email:
        report.discrepancies.append("agent emailed the customer but the rules say it should not")
        must_escalate.append("customer was emailed against the rules")

    for discrepancy in report.discrepancies:
        record_guardrail(shipment_id, f"guardrail: {discrepancy}")

    # Only alert if the human doesn't have the case yet: never two alerts for
    # one shipment. If the agent already escalated, the discrepancies above
    # are recorded and that's all.
    # The agent's own alert failed (e.g. Telegram down): its message and its
    # email draft would be lost, so the guardrail tries once more with them.
    # A duplicate alert is cheap (unlike a duplicate email to a customer).
    failed_alert = next((call for call in calls
                         if call.name == "notify_human" and call.result.get("technical")), None)
    if failed_alert and not did_escalate:
        must_escalate.append("the agent's alert could not be delivered (technical failure)")

    if must_escalate and not did_escalate:
        reason = " | ".join(must_escalate)
        message = f"[GUARDRAIL] {reason}"
        draft = ""
        if failed_alert:
            message += f"\n\nAgent's message: {failed_alert.args.get('message', '')}"
            draft = failed_alert.args.get("email_draft", "")
        try:
            deliver_alert(shipment_id, message, draft, author="guardrail, code")
        except Exception as error:
            # The channel to reach the human is the one failing: never crash,
            # leave it in the log (last resort) and say it loudly.
            detail = f"{type(error).__name__}: {error}"
            print(f"\n!!! HUMAN ALERT NOT DELIVERED for {shipment_id}: {detail}\n")
            record_action(shipment_id, "error", f"human alert could NOT be delivered: {reason}",
                          detail)
            report.corrections.append(f"alert by code FAILED ({detail}): {reason}")
        else:
            record_action(shipment_id, "escalated", f"guardrail correction: {reason}",
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
        result = record_action(shipment_id, action,
                               "guardrail correction: agent did not log its action",
                               "row written by code")
        if result.get("ok"):
            report.corrections.append(f"missing log written by code ({action})")
        else:  # the data source is down: say so, never claim it was saved
            report.corrections.append(f"missing log could NOT be written ({action}): {result['error']}")

    return report


def describe_failed_calls(run: AgentRun) -> list[str]:
    """One line per failed tool call: arguments, error and whose fault it is."""
    lines = []
    for index, call in enumerate(run.tool_calls, 1):
        if call.result.get("ok") is not False:
            continue
        if call.result.get("technical"):
            kind = "technical"
        elif call.result.get("refused_by_rules"):
            kind = "agent: refused by the rules"
        elif call.result.get("agent_error"):
            kind = "agent: invalid call"
        else:
            kind = "rejected by the tool"
        lines.append(f"  FAILED {index}. {call.name}({call.args}) -> "
                     f"{call.result.get('error')} [{kind}]")
    return lines


def handle_shipment(
    shipment_id: str,
    client: genai.Client | None = None,
    model: str | None = None,
    event_id: str = "",
) -> tuple[AgentRun, GuardrailReport]:
    """Full flow for one shipment: clean id -> empty outbox -> agent -> guardrail.

    event_id: from the webhook (phase 4); "" when run by hand or by scripts.
    """
    # Normalise the FORMAT in code (our rule: ids are uppercase, no spaces).
    # Never "guess" a similar id: if it doesn't exist, it is an error.
    shipment_id = shipment_id.strip().upper()
    reset_outbox()
    run = run_agent(shipment_id, client=client, model=model, event_id=event_id)
    report = apply_guardrail(shipment_id, run)
    return run, report


if __name__ == "__main__":
    # Quick manual test: python -m app.agent ENV-1002
    sid = sys.argv[1] if len(sys.argv) > 1 else "ENV-1001"
    result, guard = handle_shipment(sid)
    print(f"\n--- {sid}: {result.iterations} rounds, limit hit: {result.hit_iteration_limit}, model: {result.model_used}")
    for i, c in enumerate(result.tool_calls, 1):
        print(f"{i}. {c.name}({c.args}) -> ok={c.result.get('ok')}")
    for line in describe_failed_calls(result):
        print(line)
    print(f"Final: {result.final_text}")
    print(f"Guardrail intervened: {guard.intervened}")
    for item in guard.corrections:
        print(f"  correction: {item}")
    for item in guard.discrepancies:
        print(f"  discrepancy: {item}")
