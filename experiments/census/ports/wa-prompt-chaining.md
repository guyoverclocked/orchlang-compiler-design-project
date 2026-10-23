# Port spec: `wa-prompt-chaining` (pattern: gate / prompt chaining)

## 1. Source

- Repo/commit: `langchain-ai/docs` @ `5d83d5e690af84ed654a8d4320bf9969af28e39f`
- File: `docs/src/oss/langgraph/workflows-agents.mdx`, section "Prompt chaining".
  - Python Graph API: lines 183-262
  - Python Functional API: lines 265-312
  - JS Graph API: lines 320-392
  - JS Functional API: lines 395-446 (duplicates, not ported separately)
- Model setup for the whole page: lines 35-47 (`ChatAnthropic(model="claude-sonnet-4-6")`, defaults).

## 2. Node graph

```
START -> generate_joke --check_punchline--> "Pass": END
                                         "Fail": improve_joke -> polish_joke -> END
```

## 3. Verbatim code and prompts

_Verbatim from `docs/src/oss/langgraph/workflows-agents.mdx` lines 35-47:_

```python
import os
import getpass

from langchain_anthropic import ChatAnthropic

def _set_env(var: str):
    if not os.environ.get(var):
        os.environ[var] = getpass.getpass(f"{var}: ")


_set_env("ANTHROPIC_API_KEY")

llm = ChatAnthropic(model="claude-sonnet-4-6")
```

_Verbatim from `docs/src/oss/langgraph/workflows-agents.mdx` lines 183-262:_

```python
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from IPython.display import Image, display


# Graph state
class State(TypedDict):
    topic: str
    joke: str
    improved_joke: str
    final_joke: str


# Nodes
def generate_joke(state: State):
    """First LLM call to generate initial joke"""

    msg = llm.invoke(f"Write a short joke about {state['topic']}")
    return {"joke": msg.content}


def check_punchline(state: State):
    """Gate function to check if the joke has a punchline"""

    # Simple check - does the joke contain "?" or "!"
    if "?" in state["joke"] or "!" in state["joke"]:
        return "Pass"
    return "Fail"


def improve_joke(state: State):
    """Second LLM call to improve the joke"""

    msg = llm.invoke(f"Make this joke funnier by adding wordplay: {state['joke']}")
    return {"improved_joke": msg.content}


def polish_joke(state: State):
    """Third LLM call for final polish"""
    msg = llm.invoke(f"Add a surprising twist to this joke: {state['improved_joke']}")
    return {"final_joke": msg.content}


# Build workflow
workflow = StateGraph(State)

# Add nodes
workflow.add_node("generate_joke", generate_joke)
workflow.add_node("improve_joke", improve_joke)
workflow.add_node("polish_joke", polish_joke)

# Add edges to connect nodes
workflow.add_edge(START, "generate_joke")
workflow.add_conditional_edges(
    "generate_joke", check_punchline, {"Fail": "improve_joke", "Pass": END}
)
workflow.add_edge("improve_joke", "polish_joke")
workflow.add_edge("polish_joke", END)

# Compile
chain = workflow.compile()

# Show workflow
display(Image(chain.get_graph().draw_mermaid_png()))

# Invoke
state = chain.invoke({"topic": "cats"})
print("Initial joke:")
print(state["joke"])
print("\n--- --- ---\n")
if "improved_joke" in state:
    print("Improved joke:")
    print(state["improved_joke"])
    print("\n--- --- ---\n")

    print("Final joke:")
    print(state["final_joke"])
else:
    print("Final joke:")
    print(state["joke"])
```

The Python Functional API variant has inverted gate logic (see section 4):

_Verbatim from `docs/src/oss/langgraph/workflows-agents.mdx` lines 265-312:_

```python
from langgraph.func import entrypoint, task


# Tasks
@task
def generate_joke(topic: str):
    """First LLM call to generate initial joke"""
    msg = llm.invoke(f"Write a short joke about {topic}")
    return msg.content


def check_punchline(joke: str):
    """Gate function to check if the joke has a punchline"""
    # Simple check - does the joke contain "?" or "!"
    if "?" in joke or "!" in joke:
        return "Fail"

    return "Pass"


@task
def improve_joke(joke: str):
    """Second LLM call to improve the joke"""
    msg = llm.invoke(f"Make this joke funnier by adding wordplay: {joke}")
    return msg.content


@task
def polish_joke(joke: str):
    """Third LLM call for final polish"""
    msg = llm.invoke(f"Add a surprising twist to this joke: {joke}")
    return msg.content


@entrypoint()
def prompt_chaining_workflow(topic: str):
    original_joke = generate_joke(topic).result()
    if check_punchline(original_joke) == "Pass":
        return original_joke

    improved_joke = improve_joke(original_joke).result()
    return polish_joke(improved_joke).result()

# Invoke
stream = prompt_chaining_workflow.stream_events("cats", version="v3")
for snapshot in stream.values:
    print(snapshot)
    print("\n")
```

The three prompts are single user strings (`llm.invoke(str)`, no system message):
- `f"Write a short joke about {state['topic']}"`
- `f"Make this joke funnier by adding wordplay: {state['joke']}"`
- `f"Add a surprising twist to this joke: {state['improved_joke']}"`

## 4. Routing condition

- Graph API (lines 204-210) and both JS versions (lines 340-345, 405-411): `if "?" in joke or "!" in joke: return "Pass"` (go to END), else `"Fail"` (improve, then polish).
- Python Functional API (lines 276-282): `if "?" in joke or "!" in joke: return "Fail"`, and then `if check_punchline(original_joke) == "Pass": return original_joke`. The polarity is inverted, which looks like a documentation bug.
- Port: follow the Graph API semantics (Pass when `contains(joke,"?") or contains(joke,"!")`). The inverted variant can be run as an ablation.

## 5. Loops / fan-out

None. Either 1 LLM call or 3.

## 6. Structured output

None. The gate is a deterministic `contains` test on raw LLM text.

## 7. Secret attribute and expected leak

- What leaks directly: whether the first (hidden) generation contains `?` or `!`, i.e. a property of response content. It is fully determined by call count (1 vs 3) and by the presence of follow-up calls whose input tokens equal the first output plus a fixed prefix.
- What we study: inferring the user's topic category (the secret input attribute) from the gate outcome plus output-token counts. Example: entity type of the topic, using DBpedia labels.

## 8. Port sketch (pseudo-code)

```
joke = LLM([user: "Write a short joke about {topic}"], max_tokens=200)
if contains(joke, "?") or contains(joke, "!"):
    return joke
improved = LLM([user: "Make this joke funnier by adding wordplay: {joke}"], max_tokens=300)
final    = LLM([user: "Add a surprising twist to this joke: {improved}"], max_tokens=300)
return final
```

## 9. Deviations

1. `max_tokens` added (original: provider default).
2. The Python Functional API polarity bug is not reproduced by default.
3. The model is changed to the study's model (original `claude-sonnet-4-6`). The gate pass rate depends heavily on model style, since jokes often end in "?" or "!". Report the pass rate per model.

## 10. Dataset

- **`fancyzhx/dbpedia_14`.** Verified with `GET https://huggingface.co/api/datasets/fancyzhx/dbpedia_14` (HTTP 200).
  - License `cc-by-sa-3.0`. Config `dbpedia_14`: train 560,000 / test 70,000.
  - Fields: `title`, `content`, `label` (14 classes: Company, EducationalInstitution, Artist, Athlete, OfficeHolder, MeanOfTransportation, Building, NaturalPlace, Village, Animal, Plant, Album, Film, WrittenWork).
  - Input: `title` -> `topic`. Secret label: `label` (entity category). Sample a balanced subset, e.g. 100 per class, from `test`.
- The original demo topic is `"cats"`. Ground truth for the gate outcome itself comes from the hidden first output (known to the experimenter).
