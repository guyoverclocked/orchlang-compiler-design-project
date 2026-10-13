"""
【案例】内存检查点 InMemorySaver：编译图时传入 checkpointer，用 thread_id 区分会话，演示 get_state / get_state_history / 二次 invoke。

对应教程章节：第 25 章 - LangGraph 高级特性 → 2、状态持久化（Persistence）

知识点速览：
- compile(checkpointer=...) 后，每次 invoke 会在检查点中留下快照；config["configurable"]["thread_id"] 标识一条「对话线程」。
- get_state(config) 取当前线程最新状态；get_state_history(config) 取历史快照序列（用于调试或时间回溯）。
- `InMemorySaver` 数据仅在进程内存中，进程结束即丢失；它最适合先帮助你理解“checkpoint 到底是什么”。
- 本例最值得观察的是：Persistence 不只是“把结果存起来”，而是把图每一步的状态历史都保留下来，为后面的 Time-Travel 打基础。
"""

from typing import Annotated

import operator
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import StateGraph, START, END
from typing_extensions import TypedDict


class PersistenceDemoState(TypedDict):
    # operator.add：列表/数值等按「相加」语义合并（列表相当于拼接）
    messages: Annotated[list, operator.add]
    step_count: Annotated[int, operator.add]


def step_one(state: PersistenceDemoState) -> dict:
    print("执行步骤 1")
    return {
        "messages": ["执行了步骤 1"],
        "step_count": 1,
    }


def step_two(state: PersistenceDemoState) -> dict:
    print("执行步骤 2")
    return {
        "messages": ["执行了步骤 2"],
        "step_count": 1,
    }


def step_three(state: PersistenceDemoState) -> dict:
    print("执行步骤 3")
    return {
        "messages": ["执行了步骤 3"],
        "step_count": 1,
    }


def create_graph():
    builder = StateGraph(PersistenceDemoState)

    builder.add_node("step_one", step_one)
    builder.add_node("step_two", step_two)
    builder.add_node("step_three", step_three)

    builder.add_edge(START, "step_one")
    builder.add_edge("step_one", "step_two")
    builder.add_edge("step_two", "step_three")
    builder.add_edge("step_three", END)

    return builder


def main():
    print("=== LangGraph 1.0 内存持久化存储演示 ===\n")

    graph = create_graph()
    app = graph.compile(checkpointer=InMemorySaver())

    config = {"configurable": {"thread_id": "user_13811112222"}}

    print("1. 首次执行工作流:")
    result = app.invoke(
        {
            "messages": ["开始执行"],
            "step_count": 0,
        },
        config,
    )

    print(f"执行结果 result: {result}\n")

    print("2. 检查存储的状态:")
    saved_state = app.get_state(config)
    print(f"保存的状态: {saved_state.values}")
    print(f"下一个节点: {saved_state.next}\n")

    # 正序遍历：从最早到最晚的检查点快照
    history = app.get_state_history(config)
    for checkpoint in history:
        print("=" * 50)
        print(f"当前状态: {checkpoint.values}")

    print("=" * 80)
    print("3. 恢复执行工作流:")
    # 工作流若已结束，再次 invoke(None, config) 通常直接返回已落盘的结果
    result2 = app.invoke(None, config)
    print(f"恢复执行结果: {result2}\n")

    print("=== 演示结束 ===")


if __name__ == "__main__":
    main()

"""
【输出示例】
=== LangGraph 1.0 内存持久化存储演示 ===

1. 首次执行工作流:
执行步骤 1
执行步骤 2
执行步骤 3
执行结果 result: {'messages': ['开始执行', '执行了步骤 1', '执行了步骤 2', '执行了步骤 3'], 'step_count': 3}

2. 检查存储的状态:
保存的状态: {'messages': ['开始执行', '执行了步骤 1', '执行了步骤 2', '执行了步骤 3'], 'step_count': 3}
下一个节点: ()

==================================================
当前状态: {'messages': ['开始执行', '执行了步骤 1', '执行了步骤 2', '执行了步骤 3'], 'step_count': 3}
==================================================
当前状态: {'messages': ['开始执行', '执行了步骤 1', '执行了步骤 2'], 'step_count': 2}
==================================================
当前状态: {'messages': ['开始执行', '执行了步骤 1'], 'step_count': 1}
==================================================
当前状态: {'messages': ['开始执行'], 'step_count': 0}
==================================================
当前状态: {'messages': [], 'step_count': 0}
================================================================================
3. 恢复执行工作流:
恢复执行结果: {'messages': ['开始执行', '执行了步骤 1', '执行了步骤 2', '执行了步骤 3'], 'step_count': 3}

=== 演示结束 ===
"""
