# Port spec: `email-support-agent` (pattern: LLM routing)

## 1. Source

- Repo/commit: `langchain-ai/docs` @ `5d83d5e690af84ed654a8d4320bf9969af28e39f`
- File: `docs/src/oss/langgraph/thinking-in-langgraph.mdx` (tutorial "Thinking in LangGraph", customer-support email agent). The JS version on the same page (lines 582-634, 688-730, 824-912, 965-991) has the same logic and is not ported separately.
- Code blocks used:
  - state and classification schema: lines 209-233
  - `read_email`, `classify_intent` (LLM call 1 and the routing): lines 527-575
  - `search_documentation`, `bug_tracking` (stubbed, no LLM): lines 645-681
  - `draft_response` (LLM call 2), `human_review` (interrupt), `send_reply`: lines 739-817
  - graph wiring: lines 930-958
- Test input used on the page (`docs/src/code-samples/langgraph/langgraph-thinking-hitl-v2.py:33-34`): `"I was charged twice for my subscription! This is urgent!"`

## 2. Node graph

```
START -> read_email -> classify_intent --(Command goto)--> one of:
   human_review          if intent == 'billing' or urgency == 'critical'      (NO draft LLM call)
   search_documentation  elif intent in ['question', 'feature']  -> draft_response
   bug_tracking          elif intent == 'bug'                     -> draft_response
   draft_response        else  (intent == 'complex')
draft_response --(Command goto)--> human_review if urgency in [high, critical] or intent == 'complex'
                                   else send_reply
human_review --interrupt()--> send_reply (approved) | END (rejected)
send_reply -> END
```

Every route except the static edges is done with `Command(goto=...)` returned from the node (no `add_conditional_edges`).

## 3. Verbatim code and prompts

_Verbatim from `docs/src/oss/langgraph/thinking-in-langgraph.mdx` lines 209-233:_

```python
from typing import TypedDict, Literal

# Define the structure for email classification
class EmailClassification(TypedDict):
    intent: Literal["question", "bug", "billing", "feature", "complex"]
    urgency: Literal["low", "medium", "high", "critical"]
    topic: str
    summary: str

class EmailAgentState(TypedDict):
    # Raw email data
    email_content: str
    sender_email: str
    email_id: str

    # Classification result
    classification: EmailClassification | None

    # Raw search/API results
    search_results: list[str] | None  # List of raw document chunks
    customer_history: dict | None  # Raw customer data from CRM

    # Generated content
    draft_response: str | None
    messages: list[str] | None
```

LLM call 1 (classifier). The prompt is the f-string `classification_prompt`; it is sent as one user message through `with_structured_output(EmailClassification)`:

_Verbatim from `docs/src/oss/langgraph/thinking-in-langgraph.mdx` lines 527-575:_

```python
    from typing import Literal
    from langgraph.graph import StateGraph, START, END
    from langgraph.types import interrupt, Command, RetryPolicy
    from langchain_openai import ChatOpenAI
    from langchain.messages import HumanMessage

    llm = ChatOpenAI(model="gpt-5-nano")

    def read_email(state: EmailAgentState) -> dict:
        """Extract and parse email content"""
        # In production, this would connect to your email service
        return {
            "messages": [HumanMessage(content=f"Processing email: {state['email_content']}")]
        }

    def classify_intent(state: EmailAgentState) -> Command[Literal["search_documentation", "human_review", "draft_response", "bug_tracking"]]:
        """Use LLM to classify email intent and urgency, then route accordingly"""

        # Create structured LLM that returns EmailClassification dict
        structured_llm = llm.with_structured_output(EmailClassification)

        # Format the prompt on-demand, not stored in state
        classification_prompt = f"""
        Analyze this customer email and classify it:

        Email: {state['email_content']}
        From: {state['sender_email']}

        Provide classification including intent, urgency, topic, and summary.
        """

        # Get structured response directly as dict
        classification = structured_llm.invoke(classification_prompt)

        # Determine next node based on classification
        if classification['intent'] == 'billing' or classification['urgency'] == 'critical':
            goto = "human_review"
        elif classification['intent'] in ['question', 'feature']:
            goto = "search_documentation"
        elif classification['intent'] == 'bug':
            goto = "bug_tracking"
        else:
            goto = "draft_response"

        # Store classification as a single dict in state
        return Command(
            update={"classification": classification},
            goto=goto
        )
```

_Verbatim from `docs/src/oss/langgraph/thinking-in-langgraph.mdx` lines 645-681:_

```python
    def search_documentation(state: EmailAgentState) -> Command[Literal["draft_response"]]:
        """Search knowledge base for relevant information"""

        # Build search query from classification
        classification = state.get('classification', {})
        query = f"{classification.get('intent', '')} {classification.get('topic', '')}"

        try:
            # Implement your search logic here
            # Store raw search results, not formatted text
            search_results = [
                "Reset password via Settings > Security > Change Password",
                "Password must be at least 12 characters",
                "Include uppercase, lowercase, numbers, and symbols"
            ]
        except SearchAPIError as e:
            # For recoverable search errors, store error and continue
            search_results = [f"Search temporarily unavailable: {str(e)}"]

        return Command(
            update={"search_results": search_results},  # Store raw results or error
            goto="draft_response"
        )

    def bug_tracking(state: EmailAgentState) -> Command[Literal["draft_response"]]:
        """Create or update bug tracking ticket"""

        # Create ticket in your bug tracking system
        ticket_id = "BUG-12345"  # Would be created via API

        return Command(
            update={
                "search_results": [f"Bug ticket {ticket_id} created"],
                "current_step": "bug_tracked"
            },
            goto="draft_response"
        )
```

LLM call 2 (drafter). The prompt is the f-string `draft_prompt`:

_Verbatim from `docs/src/oss/langgraph/thinking-in-langgraph.mdx` lines 739-817:_

```python
    def draft_response(state: EmailAgentState) -> Command[Literal["human_review", "send_reply"]]:
        """Generate response using context and route based on quality"""

        classification = state.get('classification', {})

        # Format context from raw state data on-demand
        context_sections = []

        if state.get('search_results'):
            # Format search results for the prompt
            formatted_docs = "\n".join([f"- {doc}" for doc in state['search_results']])
            context_sections.append(f"Relevant documentation:\n{formatted_docs}")

        if state.get('customer_history'):
            # Format customer data for the prompt
            context_sections.append(f"Customer tier: {state['customer_history'].get('tier', 'standard')}")

        # Build the prompt with formatted context
        draft_prompt = f"""
        Draft a response to this customer email:
        {state['email_content']}

        Email intent: {classification.get('intent', 'unknown')}
        Urgency level: {classification.get('urgency', 'medium')}

        {chr(10).join(context_sections)}

        Guidelines:
        - Be professional and helpful
        - Address their specific concern
        - Use the provided documentation when relevant
        """

        response = llm.invoke(draft_prompt)

        # Determine if human review needed based on urgency and intent
        needs_review = (
            classification.get('urgency') in ['high', 'critical'] or
            classification.get('intent') == 'complex'
        )

        # Route to appropriate next node
        goto = "human_review" if needs_review else "send_reply"

        return Command(
            update={"draft_response": response.content},  # Store only the raw response
            goto=goto
        )

    def human_review(state: EmailAgentState) -> Command[Literal["send_reply", END]]:
        """Pause for human review using interrupt and route based on decision"""

        classification = state.get('classification', {})

        # interrupt() must come first - any code before it will re-run on resume
        human_decision = interrupt({
            "email_id": state.get('email_id',''),
            "original_email": state.get('email_content',''),
            "draft_response": state.get('draft_response',''),
            "urgency": classification.get('urgency'),
            "intent": classification.get('intent'),
            "action": "Please review and approve/edit this response"
        })

        # Now process the human's decision
        if human_decision.get("approved"):
            return Command(
                update={"draft_response": human_decision.get("edited_response", state.get('draft_response',''))},
                goto="send_reply"
            )
        else:
            # Rejection means human will handle directly
            return Command(update={}, goto=END)

    def send_reply(state: EmailAgentState) -> dict:
        """Send the email response"""
        # Integrate with email service
        print(f"Sending reply: {state['draft_response'][:100]}...")
        return {}
```

_Verbatim from `docs/src/oss/langgraph/thinking-in-langgraph.mdx` lines 930-958:_

```python
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import RetryPolicy

# Create the graph
workflow = StateGraph(EmailAgentState)

# Add nodes with appropriate error handling
workflow.add_node("read_email", read_email)
workflow.add_node("classify_intent", classify_intent)

# Add retry policy for nodes that might have transient failures
workflow.add_node(
    "search_documentation",
    search_documentation,
    retry_policy=RetryPolicy(max_attempts=3)
)
workflow.add_node("bug_tracking", bug_tracking)
workflow.add_node("draft_response", draft_response)
workflow.add_node("human_review", human_review)
workflow.add_node("send_reply", send_reply)

# Add only the essential edges
workflow.add_edge(START, "read_email")
workflow.add_edge("read_email", "classify_intent")
workflow.add_edge("send_reply", END)

# Compile with checkpointer for persistence, in case run graph with Local_Server --> Please compile without checkpointer
memory = MemorySaver()
app = workflow.compile(checkpointer=memory)
```

Model: `ChatOpenAI(model="gpt-5-nano")` (line 533), with no `max_tokens` and no temperature set.

## 4. Routing conditions (exact)

| Decision point | Condition (source) | Target |
|---|---|---|
| after classifier (line 562) | `classification['intent'] == 'billing' or classification['urgency'] == 'critical'` | `human_review` (draft skipped) |
| line 564 | `classification['intent'] in ['question', 'feature']` | `search_documentation` -> `draft_response` |
| line 566 | `classification['intent'] == 'bug'` | `bug_tracking` -> `draft_response` |
| line 568 | otherwise (`complex`) | `draft_response` |
| after draft (lines 775-781) | `urgency in ['high','critical'] or intent == 'complex'` | `human_review`, else `send_reply` |
| human_review (lines 804-811) | `human_decision.get("approved")` | `send_reply`, else `END` |

## 5. Loops / fan-out

None. At most 2 LLM calls per email. The `RetryPolicy(max_attempts=3)` on `search_documentation` (line 944) only retries on exceptions, and that node is a stub.

## 6. Structured output

`EmailClassification(TypedDict)`: `intent: Literal["question","bug","billing","feature","complex"]`, `urgency: Literal["low","medium","high","critical"]`, `topic: str`, `summary: str`. The original gets it through `llm.with_structured_output(...)`, which sends the schema to the model as a tool/JSON schema.

Emulation in constrained text (proposed): append a format instruction to the same user message and ask for exactly four lines:
```
intent: <question|bug|billing|feature|complex>
urgency: <low|medium|high|critical>
topic: <few words>
summary: <one sentence>
```
Routing then uses contains-tests on the LLM output string: `contains(out, "intent: billing")`, `contains(out, "urgency: critical")`, and so on, in the same precedence order as section 4. I keep `topic` and `summary`, even though the downstream code does not use `summary` and uses `topic` only inside a search query whose results are hardcoded. Dropping them would shrink the classifier's output-token count and so change the metadata profile. Proposed `max_tokens`: 80 for the classifier and 400 for the draft. The original sets neither.

## 7. Secret attribute and expected leak

- Secret: the customer's issue category (billing vs. bug vs. question/feature vs. complex) and urgency (critical/high), both derived from private email content.
- Observable effects:
  - Number of LLM calls: 1 for billing or critical (the draft is skipped) vs. 2 for everything else.
  - Input tokens of the draft call: question/feature drafts include 3 hardcoded documentation lines, bug drafts include a ticket line, complex drafts include neither.
  - A HITL pause (latency, or a missing `send_reply`) reveals high/critical urgency or a complex intent.
  - Classifier output tokens vary weakly with the label words.

## 8. Port sketch (neutral pseudo-code, not a committed DSL syntax)

```
cls   = LLM(messages=[user: CLASSIFY_TMPL(email_content, sender_email) + FORMAT_SUFFIX], max_tokens=80)
if contains(cls,"intent: billing") or contains(cls,"urgency: critical"):
    return ESCALATE_TMPL(email_id)                      # stands in for human_review (interrupt)
elif contains(cls,"intent: question") or contains(cls,"intent: feature"):
    ctx = DOCS_STUB                                     # 3 fixed strings from lines 656-658
elif contains(cls,"intent: bug"):
    ctx = "Bug ticket BUG-12345 created"
else:
    ctx = ""
draft = LLM(messages=[user: DRAFT_TMPL(email_content, intent, urgency, ctx)], max_tokens=400)
if contains(cls,"urgency: high") or contains(cls,"intent: complex"):
    return ESCALATE_TMPL(email_id) + draft
return draft
```
`intent`/`urgency` for `DRAFT_TMPL` are filled from the classifier output, with the `.get(..., 'unknown'/'medium')` defaults when missing.

## 9. Deviations from the original

1. `human_review` uses `interrupt()` (human in the loop). The port replaces it with a terminal "escalated" output. No human decision, no resume, and the `approved` -> `send_reply` path is not modelled.
2. Structured output (tool/JSON-schema call) is emulated with a 4-line text format and substring tests. This changes the request size (no tool schema in the request; a format suffix in the prompt instead) and the output-token count.
3. `read_email` appends a `HumanMessage` to `messages` that is never sent to an LLM. It is dropped.
4. `customer_history` is never populated in the source (no node writes it), so the "Customer tier" context line never appears. The port omits it the same way.
5. `max_tokens` is added (80 and 400); the original is unbounded.
6. The model is changed to whatever model the study uses (original: `gpt-5-nano`).

## 10. Dataset

- **Primary: `Tobi-Bueck/customer-support-tickets`.** Verified with `GET https://huggingface.co/api/datasets/Tobi-Bueck/customer-support-tickets` (HTTP 200, not gated).
  - License `cc-by-nc-4.0`: non-commercial, fine for academic measurement but not permissive.
  - Size: 61,765 rows in one `train` split (datasets-server `/info`), about 56 MB. The data is synthetic (the card describes a "Synthetic IT Ticket Generator").
  - Input: `subject` + `body` -> `email_content`. Filter `language == "en"` (28,261 rows).
  - Ground-truth labels for the secret:
    - `queue` (52 values; `Billing and Payments` has 4,874 rows) maps to intent = billing.
    - `priority` (`critical` 1,914, `high` 21,925, `medium` 23,378, `low` 12,765, `very_low` 1,783) maps to urgency.
    - `type` (`Incident` 19,444, `Request` 13,950, `Problem` 10,196, `Change` 4,997) gives a coarse question/bug/feature proxy (Incident/Problem as bug, Request as question, Change as feature). This mapping is my proposal, not part of the dataset.
- **Permissive alternative: `bitext/Bitext-customer-support-llm-chatbot-training-dataset`** (HTTP 200; `cdla-sharing-1.0`; 26,872 rows).
  - Input: `instruction`. Labels: `category` (11 values incl. `PAYMENT`, `INVOICE`, `REFUND`) for billing, and `intent` (27 values).
  - It has no urgency label, so only the billing branch can be scored against ground truth.
