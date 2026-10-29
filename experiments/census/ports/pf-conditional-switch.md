# Port spec: `pf-conditional-switch` (pattern: Prompt Flow conditional flow, `activate` switch)

## 1. Source

- Repo/commit: `microsoft/promptflow` @ `33a68c9d3cf349d7fdfad1f41969af27543c0406`
- Directory: `promptflow/examples/flows/standard/conditional-flow-for-switch/`
  - `flow.dag.yaml` (69 lines)
  - `classify_with_llm.jinja2` (11 lines)
  - `class_check.py`, `order_search.py`, `product_info.py`, `product_recommendation.py`, `generate_response.py`
  - `data.jsonl` (3 demo queries)
- Activation semantics: `promptflow/docs/how-to-guides/develop-a-dag-flow/add-conditional-control-to-a-flow.md:58-73` and `promptflow/src/promptflow-core/promptflow/executor/_dag_manager.py:106-144`. A node is bypassed if its `activate` condition fails, or if *all* its node-reference dependencies are bypassed. Bypassed outputs are `None`, or the parameter default when one is declared.

## 2. Node graph

```
inputs.query -> classify_with_llm (LLM, max_tokens 128) -> class_check (python: first intent substring found)
   activate when class_check.output == "order_search"           -> order_search (python stub)
   activate when class_check.output == "product_info"           -> product_info (python stub)
   activate when class_check.output == "product_recommendation" -> product_recommendation (python stub)
-> generate_response (python: first non-empty branch output, else default apology) -> outputs.response
```

If `class_check` returns `"unknown"`, all three branches are bypassed. `generate_response` still runs, because its parameters have defaults (`""`), and returns the default string.

## 3. Verbatim files

_Verbatim from `promptflow/examples/flows/standard/conditional-flow-for-switch/flow.dag.yaml` lines 1-69:_

```yaml
$schema: https://azuremlschemas.azureedge.net/promptflow/latest/Flow.schema.json
inputs:
  query:
    type: string
    default: When will my order be shipped?
outputs:
  response:
    type: string
    reference: ${generate_response.output}
nodes:
- name: classify_with_llm
  type: llm
  source:
    type: code
    path: classify_with_llm.jinja2
  inputs:
    deployment_name: gpt-35-turbo
    max_tokens: 128
    query: ${inputs.query}
  connection: open_ai_connection
  api: chat
- name: class_check
  type: python
  source:
    type: code
    path: class_check.py
  inputs:
    llm_result: ${classify_with_llm.output}
- name: order_search
  type: python
  source:
    type: code
    path: order_search.py
  inputs:
    query: ${inputs.query}
  activate:
    when: ${class_check.output}
    is: order_search
- name: product_info
  type: python
  source:
    type: code
    path: product_info.py
  inputs:
    query: ${inputs.query}
  activate:
    when: ${class_check.output}
    is: product_info
- name: product_recommendation
  type: python
  source:
    type: code
    path: product_recommendation.py
  inputs:
    query: ${inputs.query}
  activate:
    when: ${class_check.output}
    is: product_recommendation
- name: generate_response
  type: python
  source:
    type: code
    path: generate_response.py
  inputs:
    order_search: ${order_search.output}
    product_info: ${product_info.output}
    product_recommendation: ${product_recommendation.output}
environment:
    python_requirements_txt: requirements.txt
```

The prompt. Prompt Flow's chat API parses `# system:` / `# user:` into role messages:

_Verbatim from `promptflow/examples/flows/standard/conditional-flow-for-switch/classify_with_llm.jinja2` lines 1-11:_

```jinja
# system:
There is a search bar in the mall APP and users can enter any query in the search bar.

The user may want to search for orders, view product information, or seek recommended products.

Therefore, please classify user intentions into the following three types according to the query: product_recommendation, order_search, product_info

Please note that only the above three situations can be returned, and try not to include other return values.

# user:
The user's query is {{query}}
```

_Verbatim from `promptflow/examples/flows/standard/conditional-flow-for-switch/class_check.py` lines 1-8:_

```python
from promptflow.core import tool


@tool
def class_check(llm_result: str) -> str:
    intentions_list = ["order_search", "product_info", "product_recommendation"]
    matches = [intention for intention in intentions_list if intention in llm_result.lower()]
    return matches[0] if matches else "unknown"
```

_Verbatim from `promptflow/examples/flows/standard/conditional-flow-for-switch/order_search.py` lines 1-7:_

```python
from promptflow.core import tool


@tool
def order_search(query: str) -> str:
    print(f"Your query is {query}.\nSearching for order...")
    return "Your order is being mailed, please wait patiently."
```

_Verbatim from `promptflow/examples/flows/standard/conditional-flow-for-switch/product_info.py` lines 1-7:_

```python
from promptflow.core import tool


@tool
def product_info(query: str) -> str:
    print(f"Your query is {query}.\nLooking for product information...")
    return "This product is produced by Microsoft."
```

_Verbatim from `promptflow/examples/flows/standard/conditional-flow-for-switch/product_recommendation.py` lines 1-7:_

```python
from promptflow.core import tool


@tool
def product_recommendation(query: str) -> str:
    print(f"Your query is {query}.\nRecommending products...")
    return "I recommend promptflow to you, which can solve your problem very well."
```

_Verbatim from `promptflow/examples/flows/standard/conditional-flow-for-switch/generate_response.py` lines 1-8:_

```python
from promptflow.core import tool


@tool
def generate_response(order_search="", product_info="", product_recommendation="") -> str:
    default_response = "Sorry, no results matching your search were found."
    responses = [order_search, product_info, product_recommendation]
    return next((response for response in responses if response), default_response)
```

_Verbatim from `promptflow/examples/flows/standard/conditional-flow-for-switch/data.jsonl` lines 1-3:_

```json
{"query": "When will my order be shipped?"}
{"query": "Can you help me find information about this T-shirt?"}
{"query": "Can you recommend me a useful prompt tool?"}
```

## 4. Routing condition

`class_check` lowercases the LLM output and returns the first element of `["order_search", "product_info", "product_recommendation"]` that occurs as a substring, else `"unknown"`. Precedence follows list order, not position in the text. `activate.when/is` then performs string equality on that label.

## 5. Loops / fan-out

None.

## 6. Structured output

None. Free text with substring matching, which maps directly onto DSL contains-tests.

## 7. Secret attribute and expected leak

- Secret: the user's shopping intent (order lookup vs. product information vs. recommendation).
- Leak: there is **always exactly one LLM call**. Branches are deterministic python with no LLM. Leakage therefore comes only from:
  - the classifier's output tokens. The label strings differ in token length (`order_search`, `product_info`, `product_recommendation`), and models often add words;
  - the application response size, a fixed string per branch (to a network observer of the app, not of the LLM).
- This is the corpus's clearest "constant call count, token-count-only" conditional flow.

## 8. Port sketch

```
c = LLM([system: CLASSIFY_SYS, user: "The user's query is {query}"], max_tokens=128)
if   contains(lower(c), "order_search"):           r = "Your order is being mailed, please wait patiently."
elif contains(lower(c), "product_info"):           r = "This product is produced by Microsoft."
elif contains(lower(c), "product_recommendation"): r = "I recommend promptflow to you, which can solve your problem very well."
else:                                              r = "Sorry, no results matching your search were found."
return r
```

## 9. Deviations

1. The python stubs' `print(...)` side effects are dropped.
2. If the DSL lacks `lower()`, lowercase the label constants and accept that capitalized outputs, e.g. "Order_search", are missed. Alternatively add both casings as extra contains-tests.
3. The model changes from Azure `gpt-35-turbo` (deployment `gpt-35-turbo`; no temperature set in the flow, so the promptflow tool default applies). `max_tokens: 128` is kept.
4. The `# system:`/`# user:` jinja role markers become explicit chat messages; whitespace in the rendered prompt may differ slightly.

## 10. Dataset

- **`bitext/Bitext-retail-ecommerce-llm-chatbot-training-dataset`.** Verified HTTP 200.
  - License `cdla-sharing-1.0`. 44,884 rows in one `train` split.
  - Fields: `instruction`, `intent` (46 values), `category` (13 values), `tags`, `response`.
  - Input: `instruction` -> `query`.
  - Ground-truth mapping (proposed):
    - **order_search** <- intents `track_order`, `order_history`, `change_order`, `cancel_order` (category `ORDER` 3,945 rows, plus `track_delivery`);
    - **product_info** <- `product_information` (987), `availability` (972), `availability_online` (993), `availability_in_store` (756);
    - **product_recommendation**: *no matching intent exists in this dataset*. Either drop the class, mark other intents as `unknown` (the flow's default path), or supplement with hand-written recommendation requests.
- Alternatives:
  - `clinc/clinc_oos` (HTTP 200; `cc-by-3.0`; `plus` config 15,250/3,100/5,500). It has intents `order`, `order_status`, `shopping_list` and out-of-scope (`oos`) queries for the `unknown` path.
  - `PolyAI/banking77` (HTTP 200; `cc-by-4.0`) does not fit this mall-app domain.
