# Port spec: `wa-orchestrator-worker` (pattern: orchestrator-worker / dynamic fan-out with `Send`)

## 1. Source

- Repo/commit: `langchain-ai/docs` @ `5d83d5e690af84ed654a8d4320bf9969af28e39f`
- File: `docs/src/oss/langgraph/workflows-agents.mdx`, section "Orchestrator-worker".
  - Python Graph API tab: lines 1118-1139 (schema + planner)
  - "Creating workers in LangGraph" (Send-based graph): lines 1315-1414
  - Python Functional API: lines 1142-1216
  - JS: lines 1224-1303 and 1419-1507 (duplicates)
- Model: lines 35-47 (`ChatAnthropic(model="claude-sonnet-4-6")`).

## 2. Node graph

```
START -> orchestrator (planner LLM, structured Sections)
      --assign_workers: [Send("llm_call", {"section": s}) for s in sections]-->  llm_call x |sections|  (parallel)
      -> synthesizer (string join, no LLM) -> END
```

## 3. Verbatim code and prompts

_Verbatim from `docs/src/oss/langgraph/workflows-agents.mdx` lines 1118-1139:_

```python
from typing import Annotated, List
import operator


# Schema for structured output to use in planning
class Section(BaseModel):
    name: str = Field(
        description="Name for this section of the report.",
    )
    description: str = Field(
        description="Brief overview of the main topics and concepts to be covered in this section.",
    )


class Sections(BaseModel):
    sections: List[Section] = Field(
        description="Sections of the report.",
    )


# Augment the LLM with schema for structured output
planner = llm.with_structured_output(Sections)
```

_Verbatim from `docs/src/oss/langgraph/workflows-agents.mdx` lines 1315-1414:_

```python
from langgraph.types import Send


# Graph state
class State(TypedDict):
    topic: str  # Report topic
    sections: list[Section]  # List of report sections
    completed_sections: Annotated[
        list, operator.add
    ]  # All workers write to this key in parallel
    final_report: str  # Final report


# Worker state
class WorkerState(TypedDict):
    section: Section
    completed_sections: Annotated[list, operator.add]


# Nodes
def orchestrator(state: State):
    """Orchestrator that generates a plan for the report"""

    # Generate queries
    report_sections = planner.invoke(
        [
            SystemMessage(content="Generate a plan for the report."),
            HumanMessage(content=f"Here is the report topic: {state['topic']}"),
        ]
    )

    return {"sections": report_sections.sections}


def llm_call(state: WorkerState):
    """Worker writes a section of the report"""

    # Generate section
    section = llm.invoke(
        [
            SystemMessage(
                content="Write a report section following the provided name and description. Include no preamble for each section. Use markdown formatting."
            ),
            HumanMessage(
                content=f"Here is the section name: {state['section'].name} and description: {state['section'].description}"
            ),
        ]
    )

    # Write the updated section to completed sections
    return {"completed_sections": [section.content]}


def synthesizer(state: State):
    """Synthesize full report from sections"""

    # List of completed sections
    completed_sections = state["completed_sections"]

    # Format completed section to str to use as context for final sections
    completed_report_sections = "\n\n---\n\n".join(completed_sections)

    return {"final_report": completed_report_sections}


# Conditional edge function to create llm_call workers that each write a section of the report
def assign_workers(state: State):
    """Assign a worker to each section in the plan"""

    # Kick off section writing in parallel via Send() API
    return [Send("llm_call", {"section": s}) for s in state["sections"]]


# Build workflow
orchestrator_worker_builder = StateGraph(State)

# Add the nodes
orchestrator_worker_builder.add_node("orchestrator", orchestrator)
orchestrator_worker_builder.add_node("llm_call", llm_call)
orchestrator_worker_builder.add_node("synthesizer", synthesizer)

# Add edges to connect nodes
orchestrator_worker_builder.add_edge(START, "orchestrator")
orchestrator_worker_builder.add_conditional_edges(
    "orchestrator", assign_workers, ["llm_call"]
)
orchestrator_worker_builder.add_edge("llm_call", "synthesizer")
orchestrator_worker_builder.add_edge("synthesizer", END)

# Compile the workflow
orchestrator_worker = orchestrator_worker_builder.compile()

# Show the workflow
display(Image(orchestrator_worker.get_graph().draw_mermaid_png()))

# Invoke
state = orchestrator_worker.invoke({"topic": "Create a report on LLM scaling laws"})

from IPython.display import Markdown
Markdown(state["final_report"])
```

Functional API variant. Note the different, shorter worker system prompt `"Write a report section."`:

_Verbatim from `docs/src/oss/langgraph/workflows-agents.mdx` lines 1142-1216:_

```python
from typing import List


# Schema for structured output to use in planning
class Section(BaseModel):
    name: str = Field(
        description="Name for this section of the report.",
    )
    description: str = Field(
        description="Brief overview of the main topics and concepts to be covered in this section.",
    )


class Sections(BaseModel):
    sections: List[Section] = Field(
        description="Sections of the report.",
    )


# Augment the LLM with schema for structured output
planner = llm.with_structured_output(Sections)


@task
def orchestrator(topic: str):
    """Orchestrator that generates a plan for the report"""
    # Generate queries
    report_sections = planner.invoke(
        [
            SystemMessage(content="Generate a plan for the report."),
            HumanMessage(content=f"Here is the report topic: {topic}"),
        ]
    )

    return report_sections.sections


@task
def llm_call(section: Section):
    """Worker writes a section of the report"""

    # Generate section
    result = llm.invoke(
        [
            SystemMessage(content="Write a report section."),
            HumanMessage(
                content=f"Here is the section name: {section.name} and description: {section.description}"
            ),
        ]
    )

    # Write the updated section to completed sections
    return result.content


@task
def synthesizer(completed_sections: list[str]):
    """Synthesize full report from sections"""
    final_report = "\n\n---\n\n".join(completed_sections)
    return final_report


@entrypoint()
def orchestrator_worker(topic: str):
    sections = orchestrator(topic).result()
    section_futures = [llm_call(section) for section in sections]
    final_report = synthesizer(
        [section_fut.result() for section_fut in section_futures]
    ).result()
    return final_report

# Invoke
report = orchestrator_worker.invoke("Create a report on LLM scaling laws")
from IPython.display import Markdown
Markdown(report)
```

## 4. Routing / fan-out condition

`assign_workers` (lines 1381-1385) returns one `Send` per element of the LLM-produced `state["sections"]`. The number of worker calls equals `len(report_sections.sections)`, chosen by the planner LLM. With an empty list, no workers run. The `synthesizer` joins `completed_sections` with `"\n\n---\n\n"`.

## 5. Bounds

- **Original: unbounded K.** Nothing caps the number of sections.
- **Proposed: K <= 8 workers** ("for up to 8 items of the planner's list"). Justification: the DSL needs a static bound. Typical report outlines from a "Generate a plan for the report." prompt have about 3-8 sections, though this is to be measured. Truncation is observable, so log the planner's raw section count and report the saturation rate.
- No loops.

## 6. Structured output

`Sections(BaseModel)`: `sections: List[Section]` ("Sections of the report."), where `Section` has `name: str` ("Name for this section of the report.") and `description: str` ("Brief overview of the main topics and concepts to be covered in this section.").

Emulation: append a format instruction to the planner's system message: "Return one section per line as `<name> :: <description>`". The fan-out iterates over the lines (up to K); `name` and `description` are split on `::`. If the DSL cannot split strings, give each worker the whole line and use the template `Here is the section name: {line}` (deviation). Proposed `max_tokens`: planner 400, worker 600.

## 7. Secret attribute and expected leak

The number of worker calls (equal to the number of LLM-planned sections), each worker's output length, and the planner's output tokens reveal how the planner decomposed the (private) topic. The secret is the topic's category; DBpedia labels are the proxy (persons vs. places vs. works). The aggregator is not an LLM, so the final answer is not sent to the provider again.

## 8. Port sketch

```
plan = LLM([system: "Generate a plan for the report." + SECTIONS_FORMAT_SUFFIX,
            user:   "Here is the report topic: {topic}"], max_tokens=400)
for each line in first_k_lines(plan, 8):          # bounded fan-out over LLM-produced list
    sec[i] = LLM([system: "Write a report section following the provided name and description. Include no preamble for each section. Use markdown formatting.",
                  user:   "Here is the section name: {name} and description: {description}"], max_tokens=600)
return join(sec, "\n\n---\n\n")
```

## 9. Deviations

1. A bound of K=8 is added.
2. Structured list output is emulated as line-delimited text. In the original, the provider receives a JSON schema (tool definition), so request and response sizes differ.
3. The Graph API worker system prompt is used, not the Functional one.
4. The original runs workers in parallel. Latency side channels differ if the DSL runtime serializes the fan-out, so record whether execution is parallel.
5. `max_tokens` is added and the model is changed.

## 10. Dataset

- **`fancyzhx/dbpedia_14`.** Verified HTTP 200; `cc-by-sa-3.0`; train 560,000 / test 70,000.
  - Input: `title` -> topic, used in the original demo's form (`"Create a report on LLM scaling laws"` -> use `"Create a report on {title}"`).
  - Secret: `label` (14 classes). Optionally also `content` length as a "topic richness" covariate.
- Alternative if a sensitive-topic framing is wanted: **`keivalya/MedQuad-MedicalQnADataset`** (HTTP 200; 16,407 rows; fields `qtype` (16 types), `Question`, `Answer`). Its HF card declares no license; the upstream MedQuAD is distributed by NIH sources. Check the license before use.
