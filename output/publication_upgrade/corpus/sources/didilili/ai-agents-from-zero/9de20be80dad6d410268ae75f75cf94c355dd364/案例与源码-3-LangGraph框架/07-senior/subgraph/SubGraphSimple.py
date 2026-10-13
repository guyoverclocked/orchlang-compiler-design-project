"""
【案例】父子图共享字段：父图 State 与子图 State 均含 parent_messages；子图内可改共享列表；子图私有字段不会出现在父图最终 state（父 schema 未声明）。

对应教程章节：第 25 章 - LangGraph 高级特性 → 4、子图（Subgraphs）

知识点速览：
- 子图 compile 后作为父图的一个 node；父图 invoke 的初始状态会传入子图（字段对齐时）。
- 子图 TypedDict 多出的键（如 sub_message）仅在子图内部可见，父图输出按 ParentState 过滤。
- 本例重点是理解“父子图可以共享部分字段，但不是所有字段都会一路透到父图最终输出”。
- 直接修改 `state["parent_messages"].append(...)` 时需注意：若追求更稳的不可变更新风格，真实项目里通常更推荐返回新列表；本例保留原地修改只是为了更容易观察共享字段变化。
"""

from typing import TypedDict

from langgraph.graph import StateGraph, START, END


class ParentState(TypedDict):
    parent_messages: list


class SubgraphState(TypedDict):
    parent_messages: list
    sub_message: str


def subgraph_node(state: SubgraphState) -> SubgraphState:
    """子图节点：更新共享列表 + 写入子图私有字段。"""
    state["parent_messages"].append("message from subgraph updateO(∩_∩)O")
    state["sub_message"] = "subgraph private message"
    return state


def parent_node(state: ParentState) -> ParentState:
    """父图首节点：保证 parent_messages 为列表并追加父侧消息。"""
    if not state.get("parent_messages"):
        state["parent_messages"] = []
    state["parent_messages"].append("message from 父亲 node")
    return state


def build_subgraph():
    """构建并返回编译后的子图。"""
    sub_builder = StateGraph(SubgraphState)
    sub_builder.add_node("sub_node", subgraph_node)
    sub_builder.add_edge(START, "sub_node")
    sub_builder.add_edge("sub_node", END)
    return sub_builder.compile()


def build_parent_graph(compiled_subgraph):
    """构建并返回编译后的父图。"""
    builder = StateGraph(ParentState)
    builder.add_node("parent_node", parent_node)
    builder.add_node("subgraph_node", compiled_subgraph)
    builder.add_edge(START, "parent_node")
    builder.add_edge("parent_node", "subgraph_node")
    builder.add_edge("subgraph_node", END)
    return builder.compile()


def main():
    # 构建子图
    compiled_subgraph = build_subgraph()
    # 构建父图
    parent_graph = build_parent_graph(compiled_subgraph)
    initial_state = {"parent_messages": ["我是父消息"]}
    print("初始状态：", initial_state)

    # 父图执行时会进入子图；sub_message 不会出现在父图最终 dict（ParentState 无此键）
    final_state = parent_graph.invoke(initial_state)
    print("\n执行后最终状态：", final_state)


if __name__ == "__main__":
    main()
"""
初始状态： {'parent_messages': ['我是父消息']}

执行后最终状态： {'parent_messages': ['我是父消息', 'message from 父亲 node', 'message from subgraph updateO(∩_∩)O']}
"""
