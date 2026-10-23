# Port spec: `lg-crag-local` (pattern: corrective RAG, per-document grading + web-search fallback)

## 1. Source

- Repo/commit: `langchain-ai/langgraph` @ `eb066bd31a2bf01fc0cd58256df4800a3695c233`
- File: `langgraph/examples/rag/langgraph_crag_local.ipynb`. Line numbers are raw `.ipynb` JSON lines; code below is the decoded cell source.
  - `local_llm = "llama3"`: cell at lines 123-125
  - index/retriever: lines 153-192
  - retrieval grader: lines 219-257
  - generator: lines 275-303
  - web search tool: lines 313-317
  - graph: lines 348-516
  - example run: lines 541-554
- Sibling `langgraph/examples/rag/langgraph_crag.ipynb` (OpenAI, structured output, with a query-rewrite step) has a different topology and is not ported.

## 2. Node graph

```
START -> retrieve (k=4) -> grade_documents (1 LLM call per retrieved doc; sets search="Yes" if ANY doc graded "no")
      --decide_to_generate--> "search": web_search (Tavily, appended to the relevant docs) -> generate -> END
                              "generate": generate -> END
```

## 3. Verbatim code and prompts

_Verbatim from `langgraph/examples/rag/langgraph_crag_local.ipynb` decoded notebook source, raw JSON lines 123-125:_

```python
local_llm = "llama3"
model_tested = "llama3-8b"
metadata = f"CRAG, {model_tested}"
```

_Verbatim from `langgraph/examples/rag/langgraph_crag_local.ipynb` decoded notebook source, raw JSON lines 153-192:_

```python
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import WebBaseLoader
from langchain_community.vectorstores import SKLearnVectorStore
from langchain_nomic.embeddings import NomicEmbeddings  # local
from langchain_openai import OpenAIEmbeddings  # api

# List of URLs to load documents from
urls = [
    "https://lilianweng.github.io/posts/2023-06-23-agent/",
    "https://lilianweng.github.io/posts/2023-03-15-prompt-engineering/",
    "https://lilianweng.github.io/posts/2023-10-25-adv-attack-llm/",
]

# Load documents from the URLs
docs = [WebBaseLoader(url).load() for url in urls]
docs_list = [item for sublist in docs for item in sublist]

# Initialize a text splitter with specified chunk size and overlap
text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
    chunk_size=250, chunk_overlap=0
)

# Split the documents into chunks
doc_splits = text_splitter.split_documents(docs_list)

# Embedding
"""
embedding=NomicEmbeddings(
    model="nomic-embed-text-v1.5",
    inference_mode="local",
)
"""
embedding = OpenAIEmbeddings()

# Add the document chunks to the "vector store"
vectorstore = SKLearnVectorStore.from_documents(
    documents=doc_splits,
    embedding=embedding,
)
retriever = vectorstore.as_retriever(k=4)
```

Retrieval grader. This is a single-string `PromptTemplate` sent as one user message. Ollama runs in JSON mode (`format="json"`):

_Verbatim from `langgraph/examples/rag/langgraph_crag_local.ipynb` decoded notebook source, raw JSON lines 219-257:_

```python
### Retrieval Grader

from langchain.prompts import PromptTemplate
from langchain_community.chat_models import ChatOllama
from langchain_core.output_parsers import JsonOutputParser
from langchain_mistralai.chat_models import ChatMistralAI

# LLM
llm = ChatOllama(model=local_llm, format="json", temperature=0)

# Prompt
prompt = PromptTemplate(
    template="""You are a teacher grading a quiz. You will be given: 
    1/ a QUESTION
    2/ A FACT provided by the student
    
    You are grading RELEVANCE RECALL:
    A score of 1 means that ANY of the statements in the FACT are relevant to the QUESTION. 
    A score of 0 means that NONE of the statements in the FACT are relevant to the QUESTION. 
    1 is the highest (best) score. 0 is the lowest score you can give. 
    
    Explain your reasoning in a step-by-step manner. Ensure your reasoning and conclusion are correct. 
    
    Avoid simply stating the correct answer at the outset.
    
    Question: {question} \n
    Fact: \n\n {documents} \n\n
    
    Give a binary score 'yes' or 'no' score to indicate whether the document is relevant to the question. \n
    Provide the binary score as a JSON with a single key 'score' and no premable or explanation.
    """,
    input_variables=["question", "documents"],
)

retrieval_grader = prompt | llm | JsonOutputParser()
question = "agent memory"
docs = retriever.invoke(question)
doc_txt = docs[1].page_content
print(retrieval_grader.invoke({"question": question, "documents": doc_txt}))
```

Generator:

_Verbatim from `langgraph/examples/rag/langgraph_crag_local.ipynb` decoded notebook source, raw JSON lines 275-303:_

```python
### Generate

from langchain_core.output_parsers import StrOutputParser

# Prompt
prompt = PromptTemplate(
    template="""You are an assistant for question-answering tasks. 
    
    Use the following documents to answer the question. 
    
    If you don't know the answer, just say that you don't know. 
    
    Use three sentences maximum and keep the answer concise:
    Question: {question} 
    Documents: {documents} 
    Answer: 
    """,
    input_variables=["question", "documents"],
)

# LLM
llm = ChatOllama(model=local_llm, temperature=0)

# Chain
rag_chain = prompt | llm | StrOutputParser()

# Run
generation = rag_chain.invoke({"documents": docs, "question": question})
print(generation)
```

_Verbatim from `langgraph/examples/rag/langgraph_crag_local.ipynb` decoded notebook source, raw JSON lines 313-317:_

```python
### Search

from langchain_community.tools.tavily_search import TavilySearchResults

web_search_tool = TavilySearchResults(k=3)
```

Graph:

_Verbatim from `langgraph/examples/rag/langgraph_crag_local.ipynb` decoded notebook source, raw JSON lines 348-516:_

```python
from typing import List
from typing_extensions import TypedDict
from IPython.display import Image, display
from langchain.schema import Document
from langgraph.graph import START, END, StateGraph


class GraphState(TypedDict):
    """
    Represents the state of our graph.

    Attributes:
        question: question
        generation: LLM generation
        search: whether to add search
        documents: list of documents
    """

    question: str
    generation: str
    search: str
    documents: List[str]
    steps: List[str]


def retrieve(state):
    """
    Retrieve documents

    Args:
        state (dict): The current graph state

    Returns:
        state (dict): New key added to state, documents, that contains retrieved documents
    """
    question = state["question"]
    documents = retriever.invoke(question)
    steps = state["steps"]
    steps.append("retrieve_documents")
    return {"documents": documents, "question": question, "steps": steps}


def generate(state):
    """
    Generate answer

    Args:
        state (dict): The current graph state

    Returns:
        state (dict): New key added to state, generation, that contains LLM generation
    """

    question = state["question"]
    documents = state["documents"]
    generation = rag_chain.invoke({"documents": documents, "question": question})
    steps = state["steps"]
    steps.append("generate_answer")
    return {
        "documents": documents,
        "question": question,
        "generation": generation,
        "steps": steps,
    }


def grade_documents(state):
    """
    Determines whether the retrieved documents are relevant to the question.

    Args:
        state (dict): The current graph state

    Returns:
        state (dict): Updates documents key with only filtered relevant documents
    """

    question = state["question"]
    documents = state["documents"]
    steps = state["steps"]
    steps.append("grade_document_retrieval")
    filtered_docs = []
    search = "No"
    for d in documents:
        score = retrieval_grader.invoke(
            {"question": question, "documents": d.page_content}
        )
        grade = score["score"]
        if grade == "yes":
            filtered_docs.append(d)
        else:
            search = "Yes"
            continue
    return {
        "documents": filtered_docs,
        "question": question,
        "search": search,
        "steps": steps,
    }


def web_search(state):
    """
    Web search based on the re-phrased question.

    Args:
        state (dict): The current graph state

    Returns:
        state (dict): Updates documents key with appended web results
    """

    question = state["question"]
    documents = state.get("documents", [])
    steps = state["steps"]
    steps.append("web_search")
    web_results = web_search_tool.invoke({"query": question})
    documents.extend(
        [
            Document(page_content=d["content"], metadata={"url": d["url"]})
            for d in web_results
        ]
    )
    return {"documents": documents, "question": question, "steps": steps}


def decide_to_generate(state):
    """
    Determines whether to generate an answer, or re-generate a question.

    Args:
        state (dict): The current graph state

    Returns:
        str: Binary decision for next node to call
    """
    search = state["search"]
    if search == "Yes":
        return "search"
    else:
        return "generate"


# Graph
workflow = StateGraph(GraphState)

# Define the nodes
workflow.add_node("retrieve", retrieve)  # retrieve
workflow.add_node("grade_documents", grade_documents)  # grade documents
workflow.add_node("generate", generate)  # generate
workflow.add_node("web_search", web_search)  # web search

# Build graph
workflow.add_edge(START, "retrieve")
workflow.add_edge("retrieve", "grade_documents")
workflow.add_conditional_edges(
    "grade_documents",
    decide_to_generate,
    {
        "search": "web_search",
        "generate": "generate",
    },
)
workflow.add_edge("web_search", "generate")
workflow.add_edge("generate", END)

custom_graph = workflow.compile()

display(Image(custom_graph.get_graph(xray=True).draw_mermaid_png()))
```

_Verbatim from `langgraph/examples/rag/langgraph_crag_local.ipynb` decoded notebook source, raw JSON lines 541-554:_

```python
import uuid


def predict_custom_agent_local_answer(example: dict):
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    state_dict = custom_graph.invoke(
        {"question": example["input"], "steps": []}, config
    )
    return {"response": state_dict["generation"], "steps": state_dict["steps"]}


example = {"input": "What are the types of agent memory?"}
response = predict_custom_agent_local_answer(example)
response
```

The `\n` sequences inside the triple-quoted templates are literal Python escape sequences in the source, i.e. newlines in the rendered prompt.

## 4. Routing condition

- `grade_documents` (raw lines 414-446): for every retrieved doc, `score = retrieval_grader.invoke(...)`. If `score["score"] == "yes"`, the doc is kept; otherwise `search = "Yes"`.
- `decide_to_generate` (raw lines 474-488): `"search"` if `search == "Yes"`, else `"generate"`.
- So **a single irrelevant doc triggers web search**. Web results are appended to the relevant docs (raw lines 461-470), not substituted for them.

## 5. Loops / fan-out

- No loops.
- Fan-out: one grader call per retrieved document. The count is fixed by the retriever, `as_retriever(k=4)`. The notebook passes `k` as a top-level kwarg; 4 is also the retriever's default `search_kwargs` k.
- In the DSL: four unrolled grader calls, or "for up to 4 items of the retriever's list". The DSL's fan-out is defined over LLM-produced lists, and this list is tool-produced, so that is a deviation.

## 6. Structured output

None at the API level. The grader asks for `JSON with a single key 'score'` and is run with `ChatOllama(format="json")`; the code reads `score["score"]` after `JsonOutputParser`.

Emulation: keep the grader prompt verbatim; set `max_tokens=16`; test `contains(out, "yes")`. With no JSON mode, the model may ignore "no premable or explanation". Note that the prompt also says "Explain your reasoning in a step-by-step manner", which contradicts the JSON instruction. A robust variant appends `Answer with JSON {"score": "yes"} or {"score": "no"} only.` and tests `contains(out, "\"yes\"")`. Record which variant was used.

## 7. Secret attribute and expected leak

- Secret: whether the user's question is covered by the private corpus (in-domain vs. out-of-domain), and how many retrieved passages are relevant.
- Leak:
  - The LLM call count is constant (4 graders + 1 generator) whichever branch runs, because web search is a tool, not an LLM call.
  - The generator's input tokens differ: relevant docs only, vs. relevant docs plus 3 web snippets.
  - There is an extra network round trip (latency) when search fires.
  - Each grader's output is tiny but may differ ("yes"/"no").
- This makes it a good case for *token-count-only* leakage with constant call counts.

## 8. Port sketch

```
docs = retrieve(question, k=4)                       # deterministic local retriever (BM25/TF-IDF) over fixed corpus
keep = []; search = false
for d in docs (up to 4):
    g = LLM([user: GRADER_TMPL(question, d)], max_tokens=16)
    if contains(g, "yes"): keep += d  else: search = true
if search: keep += web_search_stub(question, k=3)    # deterministic second retriever over a held-out "web" corpus
ans = LLM([user: GEN_TMPL(question, keep)], max_tokens=200)
```

## 9. Deviations

1. Corpus: Lilian Weng blog posts (fetched live) become a fixed SQuAD paragraph corpus. Chunking (tiktoken, 250 tokens) becomes whole SQuAD paragraphs (~157-4,063 chars, mean ~779).
2. Embedding retriever (`SKLearnVectorStore` + `OpenAIEmbeddings`) becomes a deterministic lexical retriever. Rankings differ.
3. Tavily web search becomes a deterministic retriever over held-out paragraphs, returning 3 results to match `k=3`.
4. In the original, `{documents}` in the generator is filled with a Python list of `Document` objects (`rag_chain.invoke({"documents": documents, ...})`, raw line 403), so the model sees `Document(...)` reprs with metadata. The port renders `page_content` joined by blank lines, which changes input tokens. To mimic the original, render a repr-like string instead.
5. JSON mode becomes a substring test (see section 6).
6. The model `llama3` (Ollama) is replaced by the study's model; `max_tokens` is added.
7. The `steps` bookkeeping list is dropped.

## 10. Dataset

- **`rajpurkar/squad` (v1.1).** Verified HTTP 200 at `https://huggingface.co/api/datasets/rajpurkar/squad`.
  - License `cc-by-sa-4.0`. Config `plain_text`: train 87,599 / validation 10,570. Validation covers 48 article titles (datasets-server `/statistics`).
  - Fields: `title`, `context`, `question`, `answers`.
- Design:
  - Split the 48 validation titles into an indexed half (corpus = their unique `context` paragraphs) and a held-out half (the "web" corpus).
  - Sample questions 50/50 from both halves.
  - Input: `question`. Secret label: `in_corpus = title in indexed half`. Per-doc relevance ground truth: retrieved paragraph == the question's gold `context`.
- Alternative with built-in distractors: **`hotpotqa/hotpot_qa`**, config `distractor` (HTTP 200; `cc-by-sa-4.0`; train 90,447 / validation 7,405). Each question has 10 paragraphs (`context`), of which the `supporting_facts` titles are gold, which gives per-paragraph relevance labels directly.
