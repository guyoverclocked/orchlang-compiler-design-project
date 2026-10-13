"""
【案例】默认 Reducer（覆盖更新）：未为状态字段指定 Reducer 时，节点返回的值会直接覆盖该字段，后执行节点的结果覆盖先执行节点的结果。

对应教程章节：第 23 章 - LangGraph API：图与状态 → 3、State 的更新机制：Reducer（规约函数）

知识点速览：
- Reducer 决定「节点返回的更新如何合并到当前状态」；不指定时采用默认行为：覆盖。
- 多节点依次更新同一字段时，最终状态中该字段只保留最后一个节点返回的值。
- 适合「单写」场景；若需追加、累加等，需使用 add_messages、operator.add 等 Reducer。
"""

from typing import List
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END


# 未为 foo、bar 指定 Reducer，默认覆盖更新
class DefaultReducerState(TypedDict):
    foo: int
    bar: List[str]


def node_default_1(state: DefaultReducerState) -> dict:
    """节点1 只更新 foo，bar 保持原样（本示例中会被节点2 覆盖 bar）。"""
    print(state["foo"])
    print(state["bar"])
    return {"foo": 22}


def node_default_2(state: DefaultReducerState) -> dict:
    """节点2 只更新 bar；foo 保持为节点1 写入的 22。"""
    print(state["foo"])
    print(state["bar"])
    return {"bar": ["bye1", "bye2", "bye3"]}


def main():
    print("1. 默认 Reducer（覆盖更新）演示:\n")
    builder = StateGraph(DefaultReducerState)
    builder.add_node("node1", node_default_1)
    builder.add_node("node2", node_default_2)
    builder.add_edge(START, "node1")
    builder.add_edge("node1", "node2")
    builder.add_edge("node2", END)
    graph = builder.compile()

    result = graph.invoke(input={"foo": 1, "bar": ["hi"]})
    print(f"执行结果: {result}\n")


if __name__ == "__main__":
    main()

"""
【输出示例】
1. 默认 Reducer（覆盖更新）演示:

1
['hi']
22
['hi']
执行结果: {'foo': 22, 'bar': ['bye1', 'bye2', 'bye3']}
"""
