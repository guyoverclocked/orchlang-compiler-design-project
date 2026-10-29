# Port spec: `calculator-react-agent` (pattern: ReAct tool loop)

## 1. Source

- Repo/commit: `langchain-ai/docs` @ `5d83d5e690af84ed654a8d4320bf9969af28e39f`
- Files:
  - `docs/src/oss/langgraph/workflows-agents.mdx`, section "Agents":
    - tools: lines 1814-1854
    - Python Graph API: lines 1859-1933
    - Python Functional API: lines 1936-1989
  - `docs/src/oss/langgraph/quickstart.mdx`, the same calculator agent:
    - model + tools: lines 74-121
    - state with an `llm_calls` counter: lines 202-209
    - Graph API tab: lines 66-763
    - Functional API tab: lines 765-1264
- The JS versions are duplicates.
- Model: workflows-agents uses `ChatAnthropic(model="claude-sonnet-4-6")` (lines 35-47); quickstart uses `init_chat_model("claude-sonnet-4-6", temperature=0)` (lines 78-81).

## 2. Node graph

```
START -> llm_call --should_continue--> tool_node -> llm_call   (repeat while the last AIMessage has tool_calls)
                                    \-> END                    (no tool calls)
```

## 3. Verbatim code and prompts

_Verbatim from `docs/src/oss/langgraph/workflows-agents.mdx` lines 1814-1854:_

```python
from langchain.tools import tool


# Define tools
@tool
def multiply(a: int, b: int) -> int:
    """Multiply `a` and `b`.

    Args:
        a: First int
        b: Second int
    """
    return a * b


@tool
def add(a: int, b: int) -> int:
    """Adds `a` and `b`.

    Args:
        a: First int
        b: Second int
    """
    return a + b


@tool
def divide(a: int, b: int) -> float:
    """Divide `a` and `b`.

    Args:
        a: First int
        b: Second int
    """
    return a / b


# Augment the LLM with tools
tools = [add, multiply, divide]
tools_by_name = {tool.name: tool for tool in tools}
llm_with_tools = llm.bind_tools(tools)
```

_Verbatim from `docs/src/oss/langgraph/workflows-agents.mdx` lines 1859-1933:_

```python
from langgraph.graph import MessagesState
from langchain.messages import SystemMessage, HumanMessage, ToolMessage


# Nodes
def llm_call(state: MessagesState):
    """LLM decides whether to call a tool or not"""

    return {
        "messages": [
            llm_with_tools.invoke(
                [
                    SystemMessage(
                        content="You are a helpful assistant tasked with performing arithmetic on a set of inputs."
                    )
                ]
                + state["messages"]
            )
        ]
    }


def tool_node(state: MessagesState):
    """Performs the tool call"""

    result = []
    for tool_call in state["messages"][-1].tool_calls:
        tool = tools_by_name[tool_call["name"]]
        observation = tool.invoke(tool_call["args"])
        result.append(ToolMessage(content=observation, tool_call_id=tool_call["id"]))
    return {"messages": result}


# Conditional edge function to route to the tool node or end based upon whether the LLM made a tool call
def should_continue(state: MessagesState) -> Literal["tool_node", END]:
    """Decide if we should continue the loop or stop based upon whether the LLM made a tool call"""

    messages = state["messages"]
    last_message = messages[-1]

    # If the LLM makes a tool call, then perform an action
    if last_message.tool_calls:
        return "tool_node"

    # Otherwise, we stop (reply to the user)
    return END


# Build workflow
agent_builder = StateGraph(MessagesState)

# Add nodes
agent_builder.add_node("llm_call", llm_call)
agent_builder.add_node("tool_node", tool_node)

# Add edges to connect nodes
agent_builder.add_edge(START, "llm_call")
agent_builder.add_conditional_edges(
    "llm_call",
    should_continue,
    ["tool_node", END]
)
agent_builder.add_edge("tool_node", "llm_call")

# Compile the agent
agent = agent_builder.compile()

# Show the agent
display(Image(agent.get_graph(xray=True).draw_mermaid_png()))

# Invoke
messages = [HumanMessage(content="Add 3 and 4.")]
messages = agent.invoke({"messages": messages})
for m in messages["messages"]:
    m.pretty_print()
```

_Verbatim from `docs/src/oss/langgraph/quickstart.mdx` lines 74-121:_

```python
from langchain.tools import tool
from langchain.chat_models import init_chat_model


model = init_chat_model(
    "claude-sonnet-4-6",
    temperature=0
)


# Define tools
@tool
def multiply(a: int, b: int) -> int:
    """Multiply `a` and `b`.

    Args:
        a: First int
        b: Second int
    """
    return a * b


@tool
def add(a: int, b: int) -> int:
    """Adds `a` and `b`.

    Args:
        a: First int
        b: Second int
    """
    return a + b


@tool
def divide(a: int, b: int) -> float:
    """Divide `a` and `b`.

    Args:
        a: First int
        b: Second int
    """
    return a / b


# Augment the LLM with tools
tools = [add, multiply, divide]
tools_by_name = {tool.name: tool for tool in tools}
model_with_tools = model.bind_tools(tools)
```

The system prompt (identical in all variants): `"You are a helpful assistant tasked with performing arithmetic on a set of inputs."`. The user turn is the raw question (demo: `"Add 3 and 4."`). The tool descriptions sent to the model are the docstrings above (e.g. ``Multiply `a` and `b`.``) together with the int/float argument schemas.

## 4. Routing condition

`should_continue` (lines 1893-1905): `if last_message.tool_calls: return "tool_node"`, else `END`. The tool node executes every tool call of the last message, in order (lines 1881-1889).

## 5. Loop bound

- **Original: unbounded.** It runs until the model stops emitting tool calls, capped only by `recursion_limit` (10007 by default in langgraph 1.2.16, `_config.py:32`; the docs state 1000, `graph-api.mdx:1502`). The Functional API is a bare `while True` (line 1969).
- **Proposed: at most N = 10 LLM turns, i.e. at most 9 tool rounds.** Justification from the chosen dataset: in GSM8K `test` (1,319 problems), the number of `<<...>>` calculator annotations per reference solution is 0:18, 1:65, 2:357, 3:364, 4:290, 5:138, 6:57, 7:21, 8:9. Median 3, p95 6, max 8 (computed from the datasets-server `/rows` API, 2026-10-23). So 10 turns covers every reference solution with one sequential tool call per step plus a final answer. Report the saturation rate.

## 6. Structured output / tool calling

The original uses native tool calling (`bind_tools`), with no structured output. A DSL without native tool calling needs a text protocol (deviation):
- Inline the three tool signatures and docstrings in the system message.
- Instruct the model to answer either `CALL <add|multiply|divide> <a> <b>` (one call per turn) or `FINAL: <answer>`.
- Loop "up to 10 iterations until `contains(out, "FINAL:")`". A deterministic `calculator(out)` tool parses the CALL line and returns the result string, which is appended as the next user/tool message.

Note that the tool schemas declare `int` arguments. GSM8K needs decimals and the model will pass floats; the original LangChain tools would coerce or validate them. Keep the tools' behaviour: `add`, `multiply`, `divide` with `a / b` float division.

## 7. Secret attribute and expected leak

- Number of LLM calls = 1 + number of tool rounds. Input tokens grow per round (the whole history is resent each turn).
- These reveal the problem's arithmetic complexity (ground truth: number of `<<>>` steps in GSM8K), whether the query needed arithmetic at all, and possibly coarse answer magnitude via tool-result token lengths.
- The secret: the private numeric problem's structure, i.e. step count and operation mix.

## 8. Port sketch

```
hist = [system: SYS + TOOL_PROTOCOL, user: question]
repeat up to 10:
    out = LLM(hist, max_tokens=200)
    if contains(out, "FINAL:"): break
    obs = calculator(out)                  # deterministic tool: parse "CALL op a b"
    hist = hist + [assistant: out, user: "Result: " + obs]
return out
```

## 9. Deviations

1. Native tool calling (tool schemas in the request, `tool_calls` in the response, `ToolMessage`s) becomes a text protocol. This changes input and output token counts, and parallel tool calls in one turn (allowed by the original tool node, lines 1881-1889) become one call per turn.
2. A bound of N=10 is added.
3. `max_tokens` is added and the model is changed (original `claude-sonnet-4-6`, temperature 0 in quickstart).
4. The quickstart's `llm_calls` state counter is dropped. It is bookkeeping only.

## 10. Dataset

- **`openai/gsm8k`.** Verified HTTP 200 at `https://huggingface.co/api/datasets/openai/gsm8k`.
  - License `mit`. Config `main`: train 7,473 / test 1,319 (about 4.7 MB).
  - Input: `question`. Ground truth: `answer`. The final value is after `####`, and the count of `<<expr=val>>` annotations is the step-count label for the secret attribute.
