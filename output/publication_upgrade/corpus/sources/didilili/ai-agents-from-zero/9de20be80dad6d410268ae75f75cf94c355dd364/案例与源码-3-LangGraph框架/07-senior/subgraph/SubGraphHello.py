"""
【案例】子图作为节点：将 compile 后的子图直接 add_node 进父图；父子共用同一 State 类型时，由 Reducer 合并 messages。

对应教程章节：第 25 章 - LangGraph 高级特性 → 4、子图（Subgraphs）

知识点速览：
- 这是子图最基础的入门案例：重点先理解“编译后的图也可以像节点一样被父图注册”。
- 父子状态结构相同、且 `messages` 使用 add（列表拼接）时，本例会出现重复前缀，正好用来观察“父图和子图各自合并一次”带来的效果。
- 这个案例不是在教“最佳消息合并策略”，而是在帮你建立对子图调用链和状态合并路径的第一直觉。
"""

from operator import add
from typing import Annotated, TypedDict

from langgraph.constants import END
from langgraph.graph import StateGraph, START


class DiliState(TypedDict):
    """
    状态：messages 使用 operator.add 合并策略——新返回的列表与原有列表拼接（非覆盖）。
    """

    messages: Annotated[list[str], add]


def sub_node(state: DiliState) -> DiliState:
    return {"messages": ["response from subgraph"]}


# --- 子图 ---
subgraph_builder = StateGraph(DiliState)
subgraph_builder.add_node("sub_node", sub_node)
subgraph_builder.add_edge(START, "sub_node")
subgraph_builder.add_edge("sub_node", END)
subgraph = subgraph_builder.compile()

# --- 父图：节点即子图 ---
builder = StateGraph(DiliState)
builder.add_node("subgraph_node", subgraph)
builder.add_edge(START, "subgraph_node")
builder.add_edge("subgraph_node", END)

graph = builder.compile()

"""
子图调用的状态传递逻辑当主图调用子图节点时，整个过程会触发两次状态合并：
第一步：主图把初始状态 {"messages": ["main-graph"]} 传递给子图

第二步：子图内部执行 sub_node，返回 {"messages": ["response from subgraph"]}，
        由于 add 策略，子图会把传入的 ["main-graph"] 和返回的 ["response from subgraph"] 拼接，
        得到 ["main-graph", "response from subgraph"]

第三步：子图执行完成后，主图会再次应用 add 策略，
    把主图原有的 ["main-graph"]
    和子图返回的 ["main-graph", "response from subgraph"] 拼接，
    最终得到 ["main-graph", "main-graph", "response from subgraph"]
"""
print(graph.invoke({"messages": ["main-graph"]}))
print()
# 预期形态示例：{'messages': ['main-graph', 'main-graph', 'response from subgraph']}

print(subgraph.get_graph().draw_mermaid())
print("=" * 50)
print()

"""
【输出示例】
{'messages': ['main-graph', 'main-graph', 'response from subgraph']}

---
config:
  flowchart:
    curve: linear
---
graph TD;
        __start__([<p>__start__</p>]):::first
        sub_node(sub_node)
        __end__([<p>__end__</p>]):::last
        __start__ --> sub_node;
        sub_node --> __end__;
        classDef default fill:#f2f0ff,line-height:1.2
        classDef first fill-opacity:0
        classDef last fill:#bfb6fc

==================================================
"""
