"""The agent: Gemini decides which tools to call, our code runs them.

Agent loop (manual, so every step is visible):
  1. Send the conversation + the tool descriptions to Gemini.
  2. If Gemini asks for tools -> run them, add the results, go to 1.
  3. If Gemini answers with text -> it has finished.
  4. Stop anyway after MAX_ITERATIONS rounds.
"""

import sys
from dataclasses import dataclass, field

from google import genai
from google.genai import types

from app.config import load_config
from app.tools import TOOLS, get_shipment, log_action, notify_human, send_customer_email

# Normal case needs ~5 rounds. The limit protects against a confused model
# calling tools forever (cost, repeated emails).
MAX_ITERATIONS = 8

SYSTEM_PROMPT = """You are a customer service agent for a mid-sized logistics operator.
You handle shipment events using ONLY the tools you have.

How to work:
1. ALWAYS start by calling get_shipment with the shipment_id you receive.
2. Decide what to do with the business rules below and act with the tools.
3. Record EVERY action you take with log_action (one call per action).
4. When you are done, reply with a one-line summary and call no more tools.

Business rules:
1. Only act on shipments with status "retrasado". Otherwise log "no_action"
   and do nothing else.
2. If the shipment does not exist, log "error" and do nothing else
   (no email, no escalation).
3. For delayed shipments ALWAYS email the customer (send_customer_email):
   apologise, explain the reason, and state the delay (delay_hours) and the
   original expected_date. Professional tone, in the customer's language
   ("es" = Spanish, "en" = English).
4. ESCALATE with notify_human if ANY of these is true:
   - delay_hours > 24
   - customer priority is "alta"
   - data is missing or inconsistent (no contact_email, customer not found...).
     In that case do NOT email the customer: only escalate.
   The escalation message must include the shipment_id, the customer name and
   exactly which rule applies with its value (e.g. "delay_hours 30 > 24").
5. Never invent data (new dates, compensations, discounts) that is not in the
   tool results.

Email style:
- Greet the customer by their company name (never "Dear customer").
- Separate paragraphs with line breaks.
- Never mention internal processes (such as escalation) and never promise
  actions that are not in the data.
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


def execute_tool(name: str, args: dict) -> dict:
    """Run the tool the model asked for. Never let an exception stop the loop."""
    tool = TOOLS.get(name)
    if tool is None:
        return {"ok": False, "error": f"unknown tool {name!r}"}
    try:
        return tool(**args)
    except Exception as error:  # returned to the model as data, like any error
        return {"ok": False, "error": f"tool {name} failed: {type(error).__name__}: {error}"}


def run_agent(
    shipment_id: str,
    client: genai.Client | None = None,
    model: str | None = None,
) -> AgentRun:
    """Handle one shipment event with the agent loop."""
    if client is None or model is None:
        api_key, model = load_config()
        client = genai.Client(api_key=api_key)

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
    run = AgentRun(shipment_id=shipment_id)

    for iteration in range(1, MAX_ITERATIONS + 1):
        run.iterations = iteration
        response = client.models.generate_content(model=model, contents=contents, config=config)

        calls = response.function_calls
        if not calls:  # plain text = the model has finished
            run.final_text = response.text or ""
            return run

        # Keep the model's turn (with its tool requests) in the conversation.
        contents.append(response.candidates[0].content)

        result_parts = []
        for call in calls:
            args = dict(call.args or {})
            result = execute_tool(call.name, args)
            run.tool_calls.append(ToolCall(name=call.name, args=args, result=result))
            result_parts.append(types.Part.from_function_response(name=call.name, response=result))
        # Send the results back so the model can decide the next step.
        # Gemini only accepts "user" and "model" turns: tool results travel
        # on our side of the conversation, as "user".
        contents.append(types.Content(role="user", parts=result_parts))

    run.hit_iteration_limit = True
    return run


if __name__ == "__main__":
    # Quick manual test: python -m app.agent ENV-1002
    sid = sys.argv[1] if len(sys.argv) > 1 else "ENV-1001"
    result = run_agent(sid)
    print(f"\n--- {sid}: {result.iterations} rounds, limit hit: {result.hit_iteration_limit}")
    for i, c in enumerate(result.tool_calls, 1):
        print(f"{i}. {c.name}({c.args}) -> ok={c.result.get('ok')}")
    print(f"Final: {result.final_text}")
