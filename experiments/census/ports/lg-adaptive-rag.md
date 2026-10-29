# Port spec: `lg-adaptive-rag` (pattern: adaptive / self-reflective RAG: router + doc grading + hallucination/answer graders + rewrite loops)

## 1. Source

- Repo/commit: `langchain-ai/langgraph` @ `eb066bd31a2bf01fc0cd58256df4800a3695c233`
- File: `langgraph/examples/rag/langgraph_adaptive_rag.ipynb`. Line numbers are raw `.ipynb` JSON lines.
  - index: 113-148
  - router: 175-215
  - retrieval grader: 233-265
  - generator: 283-305
  - hallucination grader: 326-353
  - answer grader: 374-401
  - question rewriter: 422-441
  - web search: 459-463
  - state: 485-502
  - nodes and edge functions: 520-722
  - graph: 740-782
  - example inputs: 824-839, 892-903
- Same topology with Ollama JSON-mode prompts: `langgraph/examples/rag/langgraph_adaptive_rag_local.ipynb` (router 205-217, graders 246-259 / 329-344 / 369-384, rewriter 409-419, edges 728-747). The Self-RAG notebooks (`langgraph_self_rag*.ipynb`) are this graph minus the router and web search.

## 2. Node graph

```
START --route_question (LLM router)--> "web_search": web_search -> generate
                                       "vectorstore": retrieve -> grade_documents (1 LLM call per doc)
grade_documents --decide_to_generate--> "transform_query" (no doc kept): transform_query (LLM) -> retrieve   [cycle]
                                        "generate": generate
generate --grade_generation_v_documents_and_question (hallucination LLM, then answer LLM)-->
        "not supported": generate                                   [cycle]
        "not useful":    transform_query -> retrieve -> ...         [cycle]
        "useful":        END
```

## 3. Verbatim code and prompts

_Verbatim from `langgraph/examples/rag/langgraph_adaptive_rag.ipynb` decoded notebook source, raw JSON lines 113-148:_

```python
### Build Index

from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import WebBaseLoader
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings

### from langchain_cohere import CohereEmbeddings

# Set embeddings
embd = OpenAIEmbeddings()

# Docs to index
urls = [
    "https://lilianweng.github.io/posts/2023-06-23-agent/",
    "https://lilianweng.github.io/posts/2023-03-15-prompt-engineering/",
    "https://lilianweng.github.io/posts/2023-10-25-adv-attack-llm/",
]

# Load
docs = [WebBaseLoader(url).load() for url in urls]
docs_list = [item for sublist in docs for item in sublist]

# Split
text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
    chunk_size=500, chunk_overlap=0
)
doc_splits = text_splitter.split_documents(docs_list)

# Add to vectorstore
vectorstore = Chroma.from_documents(
    documents=doc_splits,
    collection_name="rag-chroma",
    embedding=embd,
)
retriever = vectorstore.as_retriever()
```

Router (structured output `RouteQuery`):

_Verbatim from `langgraph/examples/rag/langgraph_adaptive_rag.ipynb` decoded notebook source, raw JSON lines 175-215:_

```python
### Router

from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field
from langchain_openai import ChatOpenAI


# Data model
class RouteQuery(BaseModel):
    """Route a user query to the most relevant datasource."""

    datasource: Literal["vectorstore", "web_search"] = Field(
        ...,
        description="Given a user question choose to route it to web search or a vectorstore.",
    )


# LLM with function call
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
structured_llm_router = llm.with_structured_output(RouteQuery)

# Prompt
system = """You are an expert at routing a user question to a vectorstore or web search.
The vectorstore contains documents related to agents, prompt engineering, and adversarial attacks.
Use the vectorstore for questions on these topics. Otherwise, use web-search."""
route_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system),
        ("human", "{question}"),
    ]
)

question_router = route_prompt | structured_llm_router
print(
    question_router.invoke(
        {"question": "Who will the Bears draft first in the NFL draft?"}
    )
)
print(question_router.invoke({"question": "What are the types of agent memory?"}))
```

Retrieval grader (structured output `GradeDocuments`):

_Verbatim from `langgraph/examples/rag/langgraph_adaptive_rag.ipynb` decoded notebook source, raw JSON lines 233-265:_

```python
### Retrieval Grader


# Data model
class GradeDocuments(BaseModel):
    """Binary score for relevance check on retrieved documents."""

    binary_score: str = Field(
        description="Documents are relevant to the question, 'yes' or 'no'"
    )


# LLM with function call
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
structured_llm_grader = llm.with_structured_output(GradeDocuments)

# Prompt
system = """You are a grader assessing relevance of a retrieved document to a user question. \n 
    If the document contains keyword(s) or semantic meaning related to the user question, grade it as relevant. \n
    It does not need to be a stringent test. The goal is to filter out erroneous retrievals. \n
    Give a binary score 'yes' or 'no' score to indicate whether the document is relevant to the question."""
grade_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system),
        ("human", "Retrieved document: \n\n {document} \n\n User question: {question}"),
    ]
)

retrieval_grader = grade_prompt | structured_llm_grader
question = "agent memory"
docs = retriever.get_relevant_documents(question)
doc_txt = docs[1].page_content
print(retrieval_grader.invoke({"question": question, "document": doc_txt}))
```

Generator. The prompt is pulled at runtime from LangChain Hub (`hub.pull("rlm/rag-prompt")`) and is **not contained in this file**:

_Verbatim from `langgraph/examples/rag/langgraph_adaptive_rag.ipynb` decoded notebook source, raw JSON lines 283-305:_

```python
### Generate

from langchain import hub
from langchain_core.output_parsers import StrOutputParser

# Prompt
prompt = hub.pull("rlm/rag-prompt")

# LLM
llm = ChatOpenAI(model_name="gpt-3.5-turbo", temperature=0)


# Post-processing
def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)


# Chain
rag_chain = prompt | llm | StrOutputParser()

# Run
generation = rag_chain.invoke({"context": docs, "question": question})
print(generation)
```

The text of `rlm/rag-prompt` as captured in the printed output of a sibling notebook (`langgraph/examples/rag/langgraph_agentic_rag.ipynb`, raw lines 211-217, output of `hub.pull("rlm/rag-prompt").pretty_print()`). It is one Human message; below, ANSI colour codes are removed and `{question}`/`{context}` are the template variables:

```
You are an assistant for question-answering tasks. Use the following pieces of retrieved context to answer the question. If you don't know the answer, just say that you don't know. Use three sentences maximum and keep the answer concise.
Question: {question} 
Context: {context} 
Answer:
```

The Hub version used when the notebook ran may differ. This captured output is the only local evidence.

Hallucination grader (structured output `GradeHallucinations`):

_Verbatim from `langgraph/examples/rag/langgraph_adaptive_rag.ipynb` decoded notebook source, raw JSON lines 326-353:_

```python
### Hallucination Grader


# Data model
class GradeHallucinations(BaseModel):
    """Binary score for hallucination present in generation answer."""

    binary_score: str = Field(
        description="Answer is grounded in the facts, 'yes' or 'no'"
    )


# LLM with function call
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
structured_llm_grader = llm.with_structured_output(GradeHallucinations)

# Prompt
system = """You are a grader assessing whether an LLM generation is grounded in / supported by a set of retrieved facts. \n 
     Give a binary score 'yes' or 'no'. 'Yes' means that the answer is grounded in / supported by the set of facts."""
hallucination_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system),
        ("human", "Set of facts: \n\n {documents} \n\n LLM generation: {generation}"),
    ]
)

hallucination_grader = hallucination_prompt | structured_llm_grader
hallucination_grader.invoke({"documents": docs, "generation": generation})
```

Answer grader (structured output `GradeAnswer`):

_Verbatim from `langgraph/examples/rag/langgraph_adaptive_rag.ipynb` decoded notebook source, raw JSON lines 374-401:_

```python
### Answer Grader


# Data model
class GradeAnswer(BaseModel):
    """Binary score to assess answer addresses question."""

    binary_score: str = Field(
        description="Answer addresses the question, 'yes' or 'no'"
    )


# LLM with function call
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
structured_llm_grader = llm.with_structured_output(GradeAnswer)

# Prompt
system = """You are a grader assessing whether an answer addresses / resolves a question \n 
     Give a binary score 'yes' or 'no'. Yes' means that the answer resolves the question."""
answer_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system),
        ("human", "User question: \n\n {question} \n\n LLM generation: {generation}"),
    ]
)

answer_grader = answer_prompt | structured_llm_grader
answer_grader.invoke({"question": question, "generation": generation})
```

Question rewriter:

_Verbatim from `langgraph/examples/rag/langgraph_adaptive_rag.ipynb` decoded notebook source, raw JSON lines 422-441:_

```python
### Question Re-writer

# LLM
llm = ChatOpenAI(model="gpt-3.5-turbo-0125", temperature=0)

# Prompt
system = """You a question re-writer that converts an input question to a better version that is optimized \n 
     for vectorstore retrieval. Look at the input and try to reason about the underlying semantic intent / meaning."""
re_write_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system),
        (
            "human",
            "Here is the initial question: \n\n {question} \n Formulate an improved question.",
        ),
    ]
)

question_rewriter = re_write_prompt | llm | StrOutputParser()
question_rewriter.invoke({"question": question})
```

_Verbatim from `langgraph/examples/rag/langgraph_adaptive_rag.ipynb` decoded notebook source, raw JSON lines 459-463:_

```python
### Search

from langchain_community.tools.tavily_search import TavilySearchResults

web_search_tool = TavilySearchResults(k=3)
```

_Verbatim from `langgraph/examples/rag/langgraph_adaptive_rag.ipynb` decoded notebook source, raw JSON lines 485-502:_

```python
from typing import List

from typing_extensions import TypedDict


class GraphState(TypedDict):
    """
    Represents the state of our graph.

    Attributes:
        question: question
        generation: LLM generation
        documents: list of documents
    """

    question: str
    generation: str
    documents: List[str]
```

Nodes and edge functions:

_Verbatim from `langgraph/examples/rag/langgraph_adaptive_rag.ipynb` decoded notebook source, raw JSON lines 520-722:_

```python
from langchain.schema import Document


def retrieve(state):
    """
    Retrieve documents

    Args:
        state (dict): The current graph state

    Returns:
        state (dict): New key added to state, documents, that contains retrieved documents
    """
    print("---RETRIEVE---")
    question = state["question"]

    # Retrieval
    documents = retriever.invoke(question)
    return {"documents": documents, "question": question}


def generate(state):
    """
    Generate answer

    Args:
        state (dict): The current graph state

    Returns:
        state (dict): New key added to state, generation, that contains LLM generation
    """
    print("---GENERATE---")
    question = state["question"]
    documents = state["documents"]

    # RAG generation
    generation = rag_chain.invoke({"context": documents, "question": question})
    return {"documents": documents, "question": question, "generation": generation}


def grade_documents(state):
    """
    Determines whether the retrieved documents are relevant to the question.

    Args:
        state (dict): The current graph state

    Returns:
        state (dict): Updates documents key with only filtered relevant documents
    """

    print("---CHECK DOCUMENT RELEVANCE TO QUESTION---")
    question = state["question"]
    documents = state["documents"]

    # Score each doc
    filtered_docs = []
    for d in documents:
        score = retrieval_grader.invoke(
            {"question": question, "document": d.page_content}
        )
        grade = score.binary_score
        if grade == "yes":
            print("---GRADE: DOCUMENT RELEVANT---")
            filtered_docs.append(d)
        else:
            print("---GRADE: DOCUMENT NOT RELEVANT---")
            continue
    return {"documents": filtered_docs, "question": question}


def transform_query(state):
    """
    Transform the query to produce a better question.

    Args:
        state (dict): The current graph state

    Returns:
        state (dict): Updates question key with a re-phrased question
    """

    print("---TRANSFORM QUERY---")
    question = state["question"]
    documents = state["documents"]

    # Re-write question
    better_question = question_rewriter.invoke({"question": question})
    return {"documents": documents, "question": better_question}


def web_search(state):
    """
    Web search based on the re-phrased question.

    Args:
        state (dict): The current graph state

    Returns:
        state (dict): Updates documents key with appended web results
    """

    print("---WEB SEARCH---")
    question = state["question"]

    # Web search
    docs = web_search_tool.invoke({"query": question})
    web_results = "\n".join([d["content"] for d in docs])
    web_results = Document(page_content=web_results)

    return {"documents": web_results, "question": question}


### Edges ###


def route_question(state):
    """
    Route question to web search or RAG.

    Args:
        state (dict): The current graph state

    Returns:
        str: Next node to call
    """

    print("---ROUTE QUESTION---")
    question = state["question"]
    source = question_router.invoke({"question": question})
    if source.datasource == "web_search":
        print("---ROUTE QUESTION TO WEB SEARCH---")
        return "web_search"
    elif source.datasource == "vectorstore":
        print("---ROUTE QUESTION TO RAG---")
        return "vectorstore"


def decide_to_generate(state):
    """
    Determines whether to generate an answer, or re-generate a question.

    Args:
        state (dict): The current graph state

    Returns:
        str: Binary decision for next node to call
    """

    print("---ASSESS GRADED DOCUMENTS---")
    state["question"]
    filtered_documents = state["documents"]

    if not filtered_documents:
        # All documents have been filtered check_relevance
        # We will re-generate a new query
        print(
            "---DECISION: ALL DOCUMENTS ARE NOT RELEVANT TO QUESTION, TRANSFORM QUERY---"
        )
        return "transform_query"
    else:
        # We have relevant documents, so generate answer
        print("---DECISION: GENERATE---")
        return "generate"


def grade_generation_v_documents_and_question(state):
    """
    Determines whether the generation is grounded in the document and answers question.

    Args:
        state (dict): The current graph state

    Returns:
        str: Decision for next node to call
    """

    print("---CHECK HALLUCINATIONS---")
    question = state["question"]
    documents = state["documents"]
    generation = state["generation"]

    score = hallucination_grader.invoke(
        {"documents": documents, "generation": generation}
    )
    grade = score.binary_score

    # Check hallucination
    if grade == "yes":
        print("---DECISION: GENERATION IS GROUNDED IN DOCUMENTS---")
        # Check question-answering
        print("---GRADE GENERATION vs QUESTION---")
        score = answer_grader.invoke({"question": question, "generation": generation})
        grade = score.binary_score
        if grade == "yes":
            print("---DECISION: GENERATION ADDRESSES QUESTION---")
            return "useful"
        else:
            print("---DECISION: GENERATION DOES NOT ADDRESS QUESTION---")
            return "not useful"
    else:
        pprint("---DECISION: GENERATION IS NOT GROUNDED IN DOCUMENTS, RE-TRY---")
        return "not supported"
```

_Verbatim from `langgraph/examples/rag/langgraph_adaptive_rag.ipynb` decoded notebook source, raw JSON lines 740-782:_

```python
from langgraph.graph import END, StateGraph, START

workflow = StateGraph(GraphState)

# Define the nodes
workflow.add_node("web_search", web_search)  # web search
workflow.add_node("retrieve", retrieve)  # retrieve
workflow.add_node("grade_documents", grade_documents)  # grade documents
workflow.add_node("generate", generate)  # generate
workflow.add_node("transform_query", transform_query)  # transform_query

# Build graph
workflow.add_conditional_edges(
    START,
    route_question,
    {
        "web_search": "web_search",
        "vectorstore": "retrieve",
    },
)
workflow.add_edge("web_search", "generate")
workflow.add_edge("retrieve", "grade_documents")
workflow.add_conditional_edges(
    "grade_documents",
    decide_to_generate,
    {
        "transform_query": "transform_query",
        "generate": "generate",
    },
)
workflow.add_edge("transform_query", "retrieve")
workflow.add_conditional_edges(
    "generate",
    grade_generation_v_documents_and_question,
    {
        "not supported": "generate",
        "useful": END,
        "not useful": "transform_query",
    },
)

# Compile
app = workflow.compile()
```

Example inputs from the notebook: `"What player at the Bears expected to draft first in the 2024 NFL draft?"` (web route) and `"What are the types of agent memory?"` (vectorstore route).

## 4. Routing conditions (exact)

| Decision | Source (raw lines) | Condition |
|---|---|---|
| route_question | 636-655 | `source.datasource == "web_search"` -> web_search; `== "vectorstore"` -> retrieve. Any other value returns `None` (unhandled). |
| decide_to_generate | 658-683 | `not filtered_documents` (every doc graded not `"yes"`) -> transform_query; else generate |
| grade_generation... | 686-722 | hallucination `binary_score == "yes"` -> then answer `binary_score == "yes"` -> `"useful"` (END), else `"not useful"` (transform_query); hallucination not `"yes"` -> `"not supported"` (regenerate) |

Note line 721 calls `pprint(...)`, but `pprint` is imported only in the later run cell (line 824). Because that cell runs before the graph is invoked, notebook order works; a standalone copy of the edge functions would need the import. This is a quirk only, not ported (prints are dropped).

## 5. Loop bounds

- **Original: three unbounded cycles** (retrieve <-> transform_query; generate self-loop; generate -> transform_query -> retrieve). The only cap is `recursion_limit`: 10007 super-steps by default in langgraph 1.2.16 (`libs/langgraph/langgraph/_internal/_config.py:32`); the docs claim 1000 (`docs/src/oss/langgraph/graph-api.mdx:1502`).
- **Proposed bounds:**
  - at most 2 query rewrites, so at most 3 retrieve/grade rounds;
  - at most 2 regenerations per retrieval context ('not supported');
  - on bound exhaustion, return the last generation (or a fixed "I don't know") and record a `bound_hit` flag.
- Justification: keeps the worst case finite and small. Worst case: 1 router + 3 x (4 graders + 1 rewrite) + 3 x 3 generate/grade pairs, about 40 calls. Self-reflection is expected to settle within 1-2 corrections, but this must be measured: report how often each bound binds, since bound hits are themselves observable.
- Fan-out: one grader call per retrieved doc. The count is fixed by `as_retriever()`'s default k=4, not content-dependent, but the per-doc verdicts drive `decide_to_generate`.

## 6. Structured outputs (all via `llm.with_structured_output`, i.e. OpenAI tool/function calling)

- `RouteQuery.datasource: Literal["vectorstore", "web_search"]`. Docstring: "Route a user query to the most relevant datasource." Field description: "Given a user question choose to route it to web search or a vectorstore."
- `GradeDocuments.binary_score: str`: "Documents are relevant to the question, 'yes' or 'no'".
- `GradeHallucinations.binary_score: str`: "Answer is grounded in the facts, 'yes' or 'no'".
- `GradeAnswer.binary_score: str`: "Answer addresses the question, 'yes' or 'no'".

Emulation: keep each system/human message verbatim and append one line built from the schema description, e.g. `Respond with exactly one word: vectorstore or web_search.` or `Respond with exactly one word: yes or no.`. Then:
- router: `contains(out,"web_search")` -> web, else vectorstore;
- graders: `equals(trim(out),"yes")`, or `contains(out,"yes")` if the DSL has no trim.

`max_tokens`: 3 for router and graders, 200 for the generator, 60 for the rewriter.

## 7. Secret attribute and expected leak

- **Router**: the web route skips retrieve and grade (4 fewer LLM calls), which reveals whether the question is about the indexed (private) domain.
- **Relevance**: an all-irrelevant retrieval adds a rewrite call plus another grading round, revealing that the corpus lacks the answer.
- **Grounding/usefulness**: regenerations and rewrites reveal hallucination or unanswerability.
- Secrets: (i) question topic in- vs. out-of-corpus; (ii) answerability. SQuAD v2 provides both.

## 8. Port sketch

```
r = LLM([system: ROUTER_SYS + ONE_WORD_SUFFIX, user: question], 3)
docs = contains(r,"web_search") ? web_stub(question) : null
rewrites = 0
loop up to 3 (retrieval rounds) while docs == null:
    cand = retrieve(question, 4); keep = []
    for d in cand: if contains(LLM([system: GRADE_SYS + YN, user: GRADE_HUMAN(d,question)],3),"yes"): keep += d
    if keep != [] : docs = keep
    elif rewrites < 2: question = LLM([system: REWRITE_SYS, user: REWRITE_HUMAN(question)],60); rewrites += 1
    else: return "I don't know"                         # bound hit
regen = 0
loop up to 3:
    gen = LLM([user: RAG_PROMPT(question, docs)], 200)
    if not contains(LLM([system: HALLU_SYS + YN, user: HALLU_HUMAN(docs, gen)],3),"yes"):
        if regen < 2: regen += 1; continue  else: break
    if contains(LLM([system: ANS_SYS + YN, user: ANS_HUMAN(question, gen)],3),"yes"): return gen
    # 'not useful' -> rewrite + re-retrieve, subject to the same rewrite budget (re-enter retrieval loop)
return gen
```

The `not useful -> transform_query -> retrieve` back-edge crosses the two loops. In a DSL with only structured bounded loops, implement the whole thing as one outer loop of at most 3 retrieval contexts, each containing a regeneration loop of at most 3. Document that the nesting changes the original's scheduling order only in that budgets are now explicit.

## 9. Deviations

1. Corpus: three Lilian Weng posts (fetched live, tiktoken chunks of 500) become a fixed SQuAD v2 paragraph corpus.
2. The router prompt's domain description (`"documents related to agents, prompt engineering, and adversarial attacks"`) **must be changed** to describe the indexed SQuAD titles. Without that the router has no way to know the domain. This is a content change to a verbatim prompt; keep the rest of the sentence structure.
3. OpenAI embeddings + Chroma become a deterministic lexical retriever; Tavily becomes a deterministic retriever over held-out paragraphs (the original web results are concatenated into a single `Document`, raw lines 626-630; mirror that).
4. In the original, `{context}`/`{documents}` are filled with a Python list of `Document` objects (raw lines 556, 702-704). `format_docs` (296-297) is defined but **never used**, so the model sees `Document(...)` reprs with metadata. The port renders joined `page_content`, or mimics the repr to preserve token counts.
5. Structured output (tool calling) becomes one-word text (see section 6).
6. Bounds are added (section 5). Unhandled router outputs fall back to vectorstore.
7. Hub prompt `rlm/rag-prompt`: the captured text above is used; it may differ from the runtime Hub version.
8. Models: router and graders `gpt-4o-mini`, generator `gpt-3.5-turbo`, rewriter `gpt-3.5-turbo-0125` (all temperature 0). The port should keep a two-model split if the side channel through model identity is part of the study; otherwise it uses the study's single model.

## 10. Dataset

- **`rajpurkar/squad_v2`.** Verified HTTP 200 at `https://huggingface.co/api/datasets/rajpurkar/squad_v2`.
  - License `cc-by-sa-4.0`. Config `squad_v2`: train 130,319 / validation 11,873.
  - Validation: 35 titles and 1,204 unique contexts. 5,945 questions are unanswerable (empty `answers.text`) and 5,928 answerable; counted via the datasets-server `/rows` API on 2026-10-23.
  - Fields: `title`, `context`, `question`, `answers`.
- Design:
  - Index the paragraphs of about half the validation titles (the router prompt lists those titles).
  - The held-out titles' paragraphs act as the "web".
  - Input: `question`.
  - Secret labels: `in_corpus` (title indexed) and `answerable` (`len(answers.text) > 0`).
- Smaller variant: `rajpurkar/squad` (v1.1, no unanswerables; HTTP 200, `cc-by-sa-4.0`).
