"""
【案例】自定义流 + 状态更新组合：节点内多次 writer(...) 推送进度，同时返回 dict 更新 State；演示 custom / updates / 组合。

对应教程章节：第 25 章 - LangGraph 高级特性 → 1、流式处理（Streaming）

知识点速览：
- `get_stream_writer()` 负责把“图运行过程中的自定义消息”主动往外推；它和节点返回的状态更新是两条并行通道。
- `stream_mode=["custom", "updates"]` 时，迭代得到 `(mode, chunk)`，非常适合前端一边看业务进度，一边看状态更新。
- 本例最值得观察的是：`writer(...)` 写出的 `custom` 数据不会自动进 State；节点真正写回图状态的，仍然是最后 return 的那份 dict。
"""

from typing import TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import StateGraph, START, END


class State(TypedDict):
    query: str
    answer: str
    progress: list


def node_with_custom_streaming(state: State) -> State:
    """带自定义流式传输的节点：边写自定义流边更新状态。"""
    writer = get_stream_writer()

    writer({"custom_key": "开始处理查询"})
    writer({"progress": "步骤1: 分析查询内容", "status": "running"})

    query = state["query"]

    writer({"progress": "步骤2: 生成结果", "status": "running"})
    writer({"progress": "步骤3: 完成处理", "status": "completed"})
    writer({"custom_key": "查询处理完成"})

    result = f"处理结果: {query.upper()}"
    return {
        "answer": result,
        "progress": state.get("progress", []) + ["处理完成"],
    }


def main():
    print("=== LangGraph 自定义数据流式传输演示 ===\n")

    graph = (
        StateGraph(State)
        .add_node("node_with_custom_streaming", node_with_custom_streaming)
        .add_edge(START, "node_with_custom_streaming")
        .add_edge("node_with_custom_streaming", END)
        .compile()
    )

    inputs = {"query": "hello world", "answer": "", "progress": []}

    print("--- 1. 单独使用 custom 流模式 ---")
    try:
        for chunk in graph.stream(inputs, stream_mode="custom"):
            print(f"自定义数据块: {chunk}")
    except Exception as e:
        print(f"错误: {e}")
        print(
            "说明: 在 Graph API 中，自定义流数据需在节点中通过 get_stream_writer 发送"
        )

    print("\n" + "=" * 50 + "\n")

    print("--- 2. 单独使用 updates 流模式 ---")
    for chunk in graph.stream(inputs, stream_mode="updates"):
        print(f"状态更新: {chunk}")

    print("\n" + "=" * 50 + "\n")

    print("--- 3. 同时使用 custom 和 updates 流模式 ---")
    try:
        for mode, chunk in graph.stream(inputs, stream_mode=["custom", "updates"]):
            print(f"[{mode}]: {chunk}")
    except Exception as e:
        print(f"错误: {e}")
        print("说明: 请确认 LangGraph 版本支持多模式流")


if __name__ == "__main__":
    main()

"""
【输出示例】
=== LangGraph 自定义数据流式传输演示 ===

--- 1. 单独使用 custom 流模式 ---
自定义数据块: {'custom_key': '开始处理查询'}
自定义数据块: {'progress': '步骤1: 分析查询内容', 'status': 'running'}
自定义数据块: {'progress': '步骤2: 生成结果', 'status': 'running'}
自定义数据块: {'progress': '步骤3: 完成处理', 'status': 'completed'}
自定义数据块: {'custom_key': '查询处理完成'}

==================================================

--- 2. 单独使用 updates 流模式 ---
状态更新: {'node_with_custom_streaming': {'answer': '处理结果: HELLO WORLD', 'progress': ['处理完成']}}

==================================================

--- 3. 同时使用 custom 和 updates 流模式 ---
[custom]: {'custom_key': '开始处理查询'}
[custom]: {'progress': '步骤1: 分析查询内容', 'status': 'running'}
[custom]: {'progress': '步骤2: 生成结果', 'status': 'running'}
[custom]: {'progress': '步骤3: 完成处理', 'status': 'completed'}
[custom]: {'custom_key': '查询处理完成'}
[updates]: {'node_with_custom_streaming': {'answer': '处理结果: HELLO WORLD', 'progress': ['处理完成']}}
"""
