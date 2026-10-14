"""
Input: 用户请求(stock_code, market_type, research_depth, selected_analysts, conversation_id)
Output: 完整的StockAnalysisState(含所有分析结果和最终决策) + EventBus事件流 + SqliteSaver checkpoint
Pos: app/agents/coordinator.py - Agent系统的核心编排器，基于LangGraph动态编排（并行fan-out/fan-in + 条件路由）+ EventBus事件发布 + 官方Checkpointer持久化

一旦我被修改，请更新我的头部注释，以及所属文件夹的md。

[2026-04-17] 接入LangGraph官方SqliteSaver checkpointer:
  - 位置: data/langgraph_checkpoint.db (与conversation JSON并存, 独立schema)
  - thread_id = conversation_id, 使agent执行状态与对话线程绑定
  - 支持 get_state/get_state_history/replay/fork (LangGraph 1.1 官方能力)
  - 一个进程一个全局saver实例, 线程安全 (sqlite3 connection per-thread)
"""
import logging
import os
import sqlite3
import threading
import time
from typing import Dict, Any, List, Optional
from langgraph.graph import StateGraph, END
from app.agents.state import StockAnalysisState

logger = logging.getLogger(__name__)


# [FIX-6 2026-05-18 +08:00] Agent 进度跟踪器
# 解决 task.progress 卡 5% 问题：每个 LangGraph 节点完成时按 (completed/total) 推进
class _ProgressTracker:
    """线程安全的进度跟踪器。

    一个 Agent 编排周期内的多线程共享一个 tracker。节点完成时调用 advance(),
    通过 EventBus 把当前进度回写到 task。"""

    def __init__(self, task_id: str, total_nodes: int, start: int = 5, end: int = 95):
        self.task_id = task_id
        self.total_nodes = max(1, total_nodes)
        self.start = start
        self.end = end
        self.completed = 0
        self._lock = threading.Lock()

    def advance(self, agent_name: str, current_step: str = '') -> int:
        with self._lock:
            self.completed += 1
            span = self.end - self.start
            progress = int(self.start + (self.completed / self.total_nodes) * span)
            progress = min(self.end, max(self.start, progress))
        # 通过 EventBus 发布 progress 更新
        try:
            from app.core.event_bus import get_event_bus
            get_event_bus().publish('task.progress_advance', {
                'task_id': self.task_id,
                'progress': progress,
                'completed': self.completed,
                'total': self.total_nodes,
                'agent_name': agent_name,
                'current_step': current_step or f'{agent_name} 完成',
            })
        except Exception as e:
            logger.debug(f'progress publish failed: {e}')
        return progress


# 线程局部跟踪器（一个 agent_run 调用一个 tracker）
_tracker_local = threading.local()


def set_progress_tracker(tracker: Optional[_ProgressTracker]) -> None:
    """在 Agent 编排开始前设置当前线程的进度跟踪器。"""
    _tracker_local.tracker = tracker


def get_progress_tracker() -> Optional[_ProgressTracker]:
    return getattr(_tracker_local, 'tracker', None)


def _to_native(obj):
    """[FIX-2 2026-05-18] 递归归一化 numpy/pandas 类型为 Python 原生类型。

    LangGraph checkpoint 使用 ormsgpack 序列化 state，遇到 numpy.float64 /
    numpy.integer / numpy.ndarray 会抛 "Type is not msgpack serializable" 错误。
    在 agent 节点返回前过一遍此函数，确保 state 可被持久化。

    支持类型：
      - numpy.floating  -> float
      - numpy.integer   -> int
      - numpy.bool_     -> bool
      - numpy.ndarray   -> list (递归)
      - pandas Series   -> list (递归)
      - pandas Timestamp -> ISO 字符串
      - dict / list / tuple / set -> 递归处理元素
      - 其他原生类型保持不变
    """
    # numpy 类型 (注意: np.float64 是 float 子类, np.int64 是 int 子类,
    # 必须在 isinstance(obj,(int,float,bool)) 快速路径之前先识别)
    try:
        import numpy as np
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return [_to_native(x) for x in obj.tolist()]
    except ImportError:
        pass
    # 快速路径: Python 原生类型直接返回
    if obj is None or isinstance(obj, (str, bool, int, float)):
        return obj
    # pandas 类型
    try:
        import pandas as pd
        if isinstance(obj, pd.Timestamp):
            return obj.isoformat()
        if isinstance(obj, pd.Series):
            return [_to_native(x) for x in obj.tolist()]
    except ImportError:
        pass
    # 容器递归
    if isinstance(obj, dict):
        return {k: _to_native(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_native(x) for x in obj]
    if isinstance(obj, set):
        return [_to_native(x) for x in obj]
    # 兜底: hasattr __float__ 当作数字处理
    if hasattr(obj, '__float__') and not isinstance(obj, (str, bytes)):
        try:
            return float(obj)
        except (TypeError, ValueError):
            pass
    return obj

# 进程级单例 checkpointer — 同 DB 文件被所有 thread 共享，check_same_thread=False
_checkpointer_instance = None
_checkpointer_lock = threading.Lock()

# S3-D1: commit 写操作锁，序列化并发 invoke 时的 sqlite commit
_sqlite_write_lock = threading.Lock()

_SQLITE_RETRY_DELAYS = (0.1, 0.3, 1.0)  # 3 次指数退避：100ms / 300ms / 1s


def _invoke_with_commit_retry(graph, initial_state: dict, invoke_config: dict) -> dict:
    """包装 graph.invoke，对 sqlite3.OperationalError（database is locked / disk I/O error）
    自动重试 3 次（指数退避）。失败后 log 并重新抛出，让上层 try/except 处理。

    S3-D1 Hunt2-M6 2026-05-20 +08:00
    """
    last_exc: Exception = RuntimeError("unreachable")
    for attempt, delay in enumerate([0.0] + list(_SQLITE_RETRY_DELAYS), start=1):
        if delay:
            logger.warning(
                f"[S3-D1] graph.invoke sqlite commit 失败（第 {attempt-1} 次），"
                f"{delay}s 后重试…"
            )
            time.sleep(delay)
        try:
            with _sqlite_write_lock:
                return graph.invoke(initial_state, invoke_config)
        except sqlite3.OperationalError as exc:
            err_msg = str(exc).lower()
            if 'locked' in err_msg or 'disk i/o' in err_msg or 'unable to open' in err_msg:
                last_exc = exc
                logger.warning(f"[S3-D1] sqlite OperationalError (attempt {attempt}): {exc}")
                continue
            raise  # 非 lock/io 类错误直接抛出
        except Exception:
            raise
    logger.error(f"[S3-D1] graph.invoke 重试 {len(_SQLITE_RETRY_DELAYS)} 次后仍失败: {last_exc}")
    raise last_exc


def get_checkpointer():
    """获取进程级 SqliteSaver 单例。

    失败时(sqlite模块不可用/磁盘只读)返回None，build_analysis_graph会降级为无checkpoint模式。
    返回的对象包装了底层sqlite连接，check_same_thread=False 允许跨线程使用。
    """
    global _checkpointer_instance
    if _checkpointer_instance is not None:
        return _checkpointer_instance
    with _checkpointer_lock:
        if _checkpointer_instance is not None:
            return _checkpointer_instance
        try:
            import sqlite3
            from langgraph.checkpoint.sqlite import SqliteSaver
            db_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'data')
            os.makedirs(db_dir, exist_ok=True)
            db_path = os.path.join(db_dir, 'langgraph_checkpoint.db')
            conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30.0)
            # S1-C6: WAL 模式，并发 agent state 读写不阻塞（多 reader + 1 writer）
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')
            conn.execute('PRAGMA busy_timeout=5000')
            # S3-F3: 辅助索引 — checkpoints 表按 thread_id 的 ORDER BY / GROUP BY 加速
            # 主键已覆盖 (thread_id, checkpoint_ns, checkpoint_id)；
            # 单独 thread_id 索引加速"查某 thread 全部 checkpoint"的 WHERE thread_id=? 扫描
            conn.execute(
                'CREATE INDEX IF NOT EXISTS ix_checkpoints_thread_id '
                'ON checkpoints (thread_id)'
            )
            conn.execute(
                'CREATE INDEX IF NOT EXISTS ix_writes_thread_id '
                'ON writes (thread_id)'
            )
            conn.commit()
            _checkpointer_instance = SqliteSaver(conn)
            logger.info(f"LangGraph Checkpointer 已初始化(WAL+索引): {db_path}")
        except Exception as e:
            logger.warning(f"LangGraph Checkpointer 初始化失败, 降级为无持久化模式: {type(e).__name__}: {e}")
            _checkpointer_instance = None
        return _checkpointer_instance


def _wrap_with_events(agent_fn, agent_name):
    """包装Agent节点函数，注入EventBus事件发布"""
    def wrapped(state):
        try:
            from app.core.event_bus import get_event_bus, EVENT_AGENT_STARTED, EVENT_AGENT_COMPLETED
            event_bus = get_event_bus()
            event_bus.publish(EVENT_AGENT_STARTED, {
                'event_type': 'agent_progress',
                'agent_name': agent_name,
                'agent': agent_name,
                'role': agent_name,
                'data': {
                    'agent_name': agent_name,
                    'status': 'started',
                    'stock_code': state.get('stock_code', ''),
                    'progress': state.get('progress', 0)
                }
            })  # G3 dual → agent.role_started
            # [UI-Q3 2026-04-15] 推一条 reasoning 事件让终端看起来更生动
            event_bus.publish('reasoning', {
                'event_type': 'reasoning',
                'data': {
                    'agent': agent_name,
                    'content': f'{agent_name}开始分析 {state.get("stock_code", "")}'
                }
            })
        except Exception:
            pass

        result = agent_fn(state)

        # [FIX-2 2026-05-18] 归一化 numpy/pandas 类型，防止 ormsgpack 序列化失败
        if isinstance(result, dict):
            result = _to_native(result)

        try:
            from app.core.event_bus import get_event_bus, EVENT_AGENT_COMPLETED
            event_bus = get_event_bus()
            # [FIX-6] 节点完成时按完成度推进 task.progress
            tracker = get_progress_tracker()
            if tracker is not None:
                node_progress = tracker.advance(agent_name)
                # 同步把推进后的 progress 写回 state, 让前端 SSE 能立刻看到
                if isinstance(result, dict):
                    result['progress'] = node_progress
                progress = node_progress
            else:
                progress = result.get('progress', state.get('progress', 0))
            event_bus.publish(EVENT_AGENT_COMPLETED, {
                'event_type': 'agent_progress',
                'agent_name': agent_name,
                'agent': agent_name,
                'role': agent_name,
                'data': {
                    'agent_name': agent_name,
                    'status': 'completed',
                    'progress': progress,
                    'stock_code': state.get('stock_code', '')
                }
            })  # G3 dual → agent.role_finished
        except Exception:
            pass

        return result
    return wrapped


def _summarize_debate(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    [R2 Q4 P5 2026-04-15] 辩论综合节点 (内联, 不新建agent文件):
    基于 bull_case + bear_case 合成 debate_summary, 为决策者提供平衡视角。

    输出 debate_summary (str, 符合 state schema) - 包含:
      - 多方主论点摘要
      - 空方主论点摘要
      - 综合倾向判断 (看多/看空/分歧)

    P0-3：同时发布 agent.debate_turn（bull/bear/summary 三轮），供前端证据面扫读。
    """
    bull_case = state.get('bull_case') or ''
    bear_case = state.get('bear_case') or ''
    stock_code = state.get('stock_code') or ''

    def _extract_confidence(text: str) -> str:
        """从 bull/bear 文本中抽取置信度关键词 (高/中/低)"""
        if not text:
            return '未知'
        for kw in ['高', '中', '低']:
            if f'置信度' in text and kw in text[max(0, text.find('置信度')):text.find('置信度')+50]:
                return kw
        return '未标注'

    def _publish_debate_turn(side: str, thesis: str, confidence: str, points: list = None):
        try:
            from app.core.event_bus import get_event_bus, EVENT_AGENT_DEBATE_TURN
            get_event_bus().publish(EVENT_AGENT_DEBATE_TURN, {
                'event_type': 'agent.debate_turn',
                'data': {
                    'side': side,  # bull | bear | summary
                    'stock_code': stock_code,
                    'thesis': (thesis or '')[:400],
                    'confidence': confidence,
                    'divergence_points': points or [],
                    'agent': '辩论综合' if side == 'summary' else (
                        '看多研究员' if side == 'bull' else '看空研究员'
                    ),
                },
            })
        except Exception:
            pass

    if not bull_case and not bear_case:
        _publish_debate_turn('summary', '辩论双方均未产出有效分析', '未知', [])
        return {
            'debate_summary': '辩论双方均未产出有效分析',
            'execution_log': [{'agent': '辩论综合', 'status': 'skipped', 'reason': 'empty_cases'}]
        }

    bull_conf = _extract_confidence(bull_case)
    bear_conf = _extract_confidence(bear_case)

    # 截取 bull/bear 前300字作为主论点摘要（证据面短扫）
    bull_thesis = (bull_case[:300] + '...') if len(bull_case) > 300 else bull_case
    bear_thesis = (bear_case[:300] + '...') if len(bear_case) > 300 else bear_case

    # P0-3：先发双方 turn，再发 summary
    _publish_debate_turn('bull', bull_thesis, bull_conf)
    _publish_debate_turn('bear', bear_thesis, bear_conf)

    # 综合倾向
    if bull_conf == '高' and bear_conf != '高':
        tendency = '多方论据更充分, 综合倾向看多'
    elif bear_conf == '高' and bull_conf != '高':
        tendency = '空方论据更充分, 综合倾向看空'
    elif bull_conf == bear_conf:
        tendency = f'双方置信度相当({bull_conf}), 观点分歧, 建议谨慎'
    else:
        tendency = f'多方置信度{bull_conf}, 空方置信度{bear_conf}, 综合需权衡'

    # 固定 3 条可扫读分歧点（不读长文也能抓住冲突）
    divergence_points = [
        '估值合理性（多方乐观 vs 空方审慎）',
        '增长可持续性与盈利质量',
        '风险定价与边际变化',
    ]

    summary = (
        f"【多方主论点】{bull_thesis}\n\n"
        f"【空方主论点】{bear_thesis}\n\n"
        f"【多方置信度】{bull_conf}\n"
        f"【空方置信度】{bear_conf}\n"
        f"【综合研判】{tendency}\n"
        f"【分歧点】" + "；".join(divergence_points)
    )

    _publish_debate_turn('summary', tendency, f'{bull_conf}/{bear_conf}', divergence_points)

    return {
        'debate_summary': summary,
        'execution_log': [{'agent': '辩论综合', 'status': 'success'}]
    }

def _route_after_technical(state: Dict[str, Any]) -> str:
    """
    技术分析之后的条件路由函数。
    根据技术分析结果决定后续路径：
    - technical_report 有 error → 快速失败，直接到 decision
    - 否则 → 正常继续后续分析节点
    """
    technical_report = state.get('technical_report')
    depth = state.get('research_depth', 1)

    # 快速失败：技术分析出错时直接跳到决策
    if technical_report and isinstance(technical_report, dict) and technical_report.get('error'):
        logger.warning(f"技术分析出错，快速失败路由到决策节点: {technical_report.get('error')}")
        return "fast_fail"

    # 正常路径：根据深度决定下一步
    if depth >= 2:
        return "parallel_depth2"
    else:
        return "direct_decision"


def build_analysis_graph(
    research_depth: int = 3,
    selected_analysts: Optional[List[str]] = None
):
    """
    构建动态编排分析图，根据研究深度动态决定节点。
    支持并行 fan-out/fan-in 和条件路由。

    深度级别:
      1 - 技术分析 + 决策
      2 - + 基本面 + 资金流（并行）
      3 - + 情绪分析
      4 - + 多空辩论（并行）
      5 - + 风险评估

    编排特性:
      - fundamental 和 capital_flow 并行执行（depth>=2）
      - bull 和 bear 并行执行（depth>=4）
      - technical 之后条件路由（error → 快速失败）
    """
    from app.agents.technical_analyst import TechnicalAnalystAgent
    from app.agents.fundamental_analyst import FundamentalAnalystAgent
    from app.agents.capital_flow_analyst import CapitalFlowAnalystAgent
    from app.agents.sentiment_analyst import SentimentAnalystAgent
    from app.agents.bull_researcher import BullResearcherAgent
    from app.agents.bear_researcher import BearResearcherAgent
    from app.agents.risk_manager import RiskManagerAgent
    from app.agents.decision_maker import DecisionMakerAgent

    graph = StateGraph(StockAnalysisState)

    # === 路由记录节点：写入 router_decision 供调试追溯 ===
    def record_router_fast_fail(state):
        """记录快速失败路由决策"""
        return {'router_decision': 'fast_fail'}

    def record_router_normal(state):
        """记录正常路由决策"""
        return {'router_decision': 'normal'}

    # === 技术分析始终包含，作为入口点 ===
    graph.add_node("technical", _wrap_with_events(TechnicalAnalystAgent.analyze, "技术分析师"))
    graph.set_entry_point("technical")

    # === 决策节点始终存在 ===
    graph.add_node("decision", _wrap_with_events(DecisionMakerAgent.analyze, "决策分析师"))

    if research_depth >= 2:
        # --- depth >= 2: fundamental 和 capital_flow 并行 (fan-out / fan-in) ---
        graph.add_node("fundamental", _wrap_with_events(FundamentalAnalystAgent.analyze, "基本面分析师"))
        graph.add_node("capital_flow", _wrap_with_events(CapitalFlowAnalystAgent.analyze, "资金流分析师"))

        # 确定 fan-in 汇合点
        if research_depth >= 3:
            # fan-in 到 sentiment
            graph.add_node("sentiment", _wrap_with_events(SentimentAnalystAgent.analyze, "情绪分析师"))
            fan_in_target = "sentiment"
        elif research_depth >= 2:
            # 没有 sentiment，直接汇合到 decision
            fan_in_target = "decision"

        # 条件路由：technical 之后判断是否快速失败
        graph.add_node("_route_record_normal", record_router_normal)
        graph.add_node("_route_record_fast_fail", record_router_fast_fail)

        graph.add_conditional_edges(
            "technical",
            _route_after_technical,
            {
                "fast_fail": "_route_record_fast_fail",     # 技术分析出错 → 快速失败
                "parallel_depth2": "_route_record_normal",  # 正常 → 进入并行
                "direct_decision": "_route_record_normal",  # depth=1 不会走到这里（此分支仅 depth>=2）
            }
        )

        # 快速失败路径 → 直接到 decision
        graph.add_edge("_route_record_fast_fail", "decision")

        # 正常路径 → fan-out: 同时启动 fundamental 和 capital_flow
        graph.add_edge("_route_record_normal", "fundamental")
        graph.add_edge("_route_record_normal", "capital_flow")

        # fan-in: fundamental 和 capital_flow 都完成后汇合
        graph.add_edge("fundamental", fan_in_target)
        graph.add_edge("capital_flow", fan_in_target)

        # 继续构建后续节点链
        last_node = fan_in_target

        if research_depth >= 4:
            # [R2 Q4 P1+P5 2026-04-15] 串行辩论: bull → bear → debate_summary
            # 原并行版本 bear 读不到 bull_case 导致退化为独立看空, 现改为串行使 bear 可真实反驳 bull_case
            graph.add_node("bull", _wrap_with_events(BullResearcherAgent.analyze, "多头研究员"))
            graph.add_node("bear", _wrap_with_events(BearResearcherAgent.analyze, "空头研究员"))
            graph.add_node("debate_summary", _wrap_with_events(_summarize_debate, "辩论综合"))

            # 串行链: sentiment → bull → bear → debate_summary
            graph.add_edge(last_node, "bull")
            graph.add_edge("bull", "bear")
            graph.add_edge("bear", "debate_summary")

            if research_depth >= 5:
                # fan-in 到 risk
                graph.add_node("risk", _wrap_with_events(RiskManagerAgent.analyze, "风险管理师"))
                graph.add_edge("debate_summary", "risk")
                last_node = "risk"

                # 投资者人格分析（可选，在风险评估后）
                try:
                    from app.agents.investors.investor_coordinator import InvestorCoordinator
                    graph.add_node("investors", _wrap_with_events(InvestorCoordinator.analyze, "投资者人格分析师"))
                    graph.add_edge("risk", "investors")
                    last_node = "investors"
                except ImportError:
                    pass  # 投资者模块未安装
            else:
                # depth=4: debate_summary 直接到 decision
                graph.add_edge("debate_summary", "decision")
                last_node = None  # decision 已连接

        # 连接最后一个节点到 decision（如果还没连接）
        if last_node is not None and last_node != "decision":
            graph.add_edge(last_node, "decision")

    else:
        # --- depth = 1: 仅技术分析 → 直接决策 ---
        # 条件路由（虽然 depth=1 也要支持快速失败）
        graph.add_node("_route_record_normal", record_router_normal)
        graph.add_node("_route_record_fast_fail", record_router_fast_fail)

        graph.add_conditional_edges(
            "technical",
            _route_after_technical,
            {
                "fast_fail": "_route_record_fast_fail",
                "direct_decision": "_route_record_normal",
                "parallel_depth2": "_route_record_normal",  # 不会到达，但需要映射
            }
        )
        graph.add_edge("_route_record_fast_fail", "decision")
        graph.add_edge("_route_record_normal", "decision")

    # === 反思节点（决策后执行，从历史中学习优化） ===
    try:
        from app.agents.reflection import ReflectionAgent
        graph.add_node("reflection", _wrap_with_events(ReflectionAgent.reflect, "反思分析师"))
        graph.add_edge("decision", "reflection")
        graph.add_edge("reflection", END)
    except ImportError:
        graph.add_edge("decision", END)

    # 编译图 — 注入checkpointer以支持replay/fork/HITL；失败时降级为无持久化
    ckpt = get_checkpointer()
    if ckpt is not None:
        return graph.compile(checkpointer=ckpt)
    return graph.compile()


def run_agent_analysis(
    stock_code: str,
    market_type: str = 'A',
    research_depth: int = 3,
    selected_analysts: Optional[List[str]] = None,
    progress_callback=None,
    conversation_id: Optional[str] = None,
    task_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    执行Agent分析的主入口。

    Args:
        stock_code: 股票代码
        market_type: 市场类型 (A/HK/US)
        research_depth: 研究深度 1-5
        selected_analysts: 可选的指定分析师列表
        progress_callback: 进度回调函数

    Returns:
        完整的分析状态字典
    """
    logger.info(f"启动Agent分析: {stock_code}, 深度={research_depth}")

    # 构建图
    graph = build_analysis_graph(research_depth, selected_analysts)

    # 初始状态
    initial_state = {
        'stock_code': stock_code,
        'market_type': market_type,
        'research_depth': research_depth,
        'messages': [],
        'technical_report': None,
        'fundamental_report': None,
        'capital_flow_report': None,
        'sentiment_report': None,
        'bull_case': None,
        'bear_case': None,
        'debate_summary': None,
        'investor_opinions': None,
        'investor_consensus': None,
        'router_decision': None,
        'risk_assessment': None,
        'final_decision': None,
        'execution_log': [],
        'progress': 0.0,
        'errors': [],
        'degradations': [],
        'confidence_cap': None,
        'scorecard': None,
        'decision_memo': None,
        'reflection_summary': None,
        'memory_context': None,
    }

    # G8 Memory 预取：同标的历史摘要注入（空历史不造假）
    try:
        from app.core.agent_memory import get_agent_memory
        from app.agents.scorecard import build_memory_prefetch_summary
        _mem = get_agent_memory()
        _hist = _mem.get_history(stock_code, limit=5) if stock_code else []
        _sem = ''
        try:
            _sem = _mem.get_semantic_summary(stock_code) or ''
        except Exception:
            _sem = ''
        _mc = build_memory_prefetch_summary(_hist, _sem, limit=5)
        if _mc:
            initial_state['memory_context'] = _mc
            summary_bits = []
            if _mc.get('history_count'):
                summary_bits.append(f"历史分析 {_mc['history_count']} 次")
            if _mc.get('semantic_context'):
                summary_bits.append(str(_mc['semantic_context'])[:400])
            if summary_bits:
                initial_state.setdefault('messages', [])
                if not isinstance(initial_state['messages'], list):
                    initial_state['messages'] = []
                initial_state['messages'].append({
                    'role': 'system',
                    'content': (
                        f"[Memory prefetch for {stock_code}] "
                        + " | ".join(summary_bits)
                    ),
                })
    except Exception as _mem_err:
        logger.debug('memory prefetch skipped: %s', _mem_err)

    # 注入自适应策略
    try:
        from app.agents.strategy_evolver import get_strategy_evolver
        strategy_prompt = get_strategy_evolver().get_strategy_prompt(stock_code)
        if strategy_prompt:
            initial_state['messages'] = [{"role": "system", "content": strategy_prompt}]
    except Exception:
        pass

    # 发布分析开始事件
    try:
        from app.core.event_bus import get_event_bus, EVENT_ANALYSIS_STARTED
        get_event_bus().publish(EVENT_ANALYSIS_STARTED, {'stock_code': stock_code})
    except Exception:
        pass

    # LangGraph checkpointer 要求 thread_id 唯一，用 conversation_id 关联对话线程；
    # 未提供时用 stock_code+时间戳兜底，仍能持久化但无法 replay 同一对话
    import time as _time
    thread_id = conversation_id or f"analysis_{stock_code}_{int(_time.time())}"
    invoke_config = {"configurable": {"thread_id": thread_id}}

    # [FIX-6 2026-05-18] 注入进度跟踪器，让每个 LangGraph 节点完成时刷新 task.progress
    tracker = None
    if task_id:
        try:
            # 估算 wrap 过的 agent 节点数(只计入业务 agent，不计路由记录节点)
            all_nodes = list(getattr(getattr(graph, 'nodes', None), 'keys', lambda: [])() or [])
            biz_nodes = [n for n in all_nodes if not str(n).startswith('_route_')]
            total = len(biz_nodes) or 1
            tracker = _ProgressTracker(task_id=task_id, total_nodes=total)
            set_progress_tracker(tracker)
            logger.info(f"[FIX-6] Agent progress tracker 已注册 task_id={task_id} total_nodes={total}")
        except Exception as e:
            logger.warning(f"[FIX-6] tracker 注入失败: {e}")

    _agent_graph_timeout = float(os.getenv('AGENT_GRAPH_TIMEOUT', '1800'))
    try:
        from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FutTimeout
        with ThreadPoolExecutor(max_workers=1) as _pool:
            _fut = _pool.submit(_invoke_with_commit_retry, graph, initial_state, invoke_config)
            try:
                result = _fut.result(timeout=_agent_graph_timeout)
            except _FutTimeout:
                try:
                    from app.core.event_bus import publish_agent_degraded
                    publish_agent_degraded(
                        cause='tool_timeout',
                        message=f'Agent graph 超时（{_agent_graph_timeout}s），未生成假行情',
                        level='critical',
                        source='coordinator',
                        task_id=task_id or '',
                        stock_code=stock_code,
                        correlation_id=task_id or conversation_id or '',
                    )
                except Exception:
                    pass
                raise TimeoutError(f"Agent graph 超时（限制 {_agent_graph_timeout}s，stock={stock_code}）")
        logger.info(f"Agent分析完成: {stock_code} (thread_id={thread_id})")

        # P0 降级可视化 + confidence 上界帽（铁律 #1：无假数；仅收紧置信）
        try:
            from app.core.event_bus import (
                apply_confidence_cap,
                infer_degradation_cause_from_text,
                merge_confidence_cap,
                publish_agent_degraded,
            )
            degs = list(result.get('degradations') or [])
            cap = result.get('confidence_cap')
            # 将 errors 中尚未结构化的失败提升为 degradation 事件
            for err_txt in (result.get('errors') or []):
                if not err_txt:
                    continue
                cause = infer_degradation_cause_from_text(str(err_txt))
                payload = publish_agent_degraded(
                    cause=cause,
                    message=str(err_txt)[:500],
                    level='warn',
                    source='agent.errors',
                    task_id=task_id or '',
                    stock_code=stock_code,
                    correlation_id=task_id or conversation_id or '',
                )
                degs.append(payload)
                cap = merge_confidence_cap(cap, payload.get('confidence_cap'))
            result['degradations'] = degs
            result['confidence_cap'] = cap
            fd = result.get('final_decision')
            if isinstance(fd, dict) and cap is not None and 'confidence' in fd:
                raw_conf = fd.get('confidence')
                capped = apply_confidence_cap(raw_conf, cap)
                if raw_conf is not None and float(capped) != float(raw_conf):
                    publish_agent_degraded(
                        cause='source_degraded',
                        message=(
                            f'置信度由 {raw_conf} 收紧至 {capped}'
                            f'（cap={cap}，未补假行情）'
                        ),
                        level='info',
                        source='confidence_cap',
                        task_id=task_id or '',
                        stock_code=stock_code,
                        confidence_cap=cap,
                    )
                result['final_decision'] = {**fd, 'confidence': capped, 'confidence_cap': cap}
        except Exception as _deg_exc:
            logger.debug('degradation post-process skipped: %s', _deg_exc)

        # G1: 汇总工具/报告路径 provenance[] 到 result 与 final_decision（仅摘要，无假行情）
        try:
            from app.core.artifact_wrapper import (
                build_provenance_entry,
                merge_provenance,
                provenance_from_sources,
            )
            prov_lists = []
            # 角色报告来源
            for _role_key, _role_val in (result or {}).items():
                if isinstance(_role_val, dict):
                    if _role_val.get('provenance'):
                        prov_lists.append(_role_val.get('provenance'))
                    elif _role_val.get('sources'):
                        prov_lists.append(
                            provenance_from_sources(
                                _role_val.get('sources'),
                                tool=str(_role_key),
                            )
                        )
            # degradations → 标注降级数据源
            for d in (result.get('degradations') or []):
                if isinstance(d, dict):
                    prov_lists.append([
                        build_provenance_entry(
                            source=str(d.get('source') or d.get('adapter') or 'degraded'),
                            tool=str(d.get('tool') or d.get('stage') or 'degradation'),
                        )
                    ])
                elif isinstance(d, str):
                    prov_lists.append([
                        build_provenance_entry(source=d, tool='degradation')
                    ])
            merged_prov = merge_provenance(*prov_lists)
            if not merged_prov:
                # 至少标记一次分析图运行
                merged_prov = [
                    build_provenance_entry(
                        source='langgraph_analysis',
                        tool='run_stock_analysis',
                        args={'stock_code': (result or {}).get('stock_code')},
                    )
                ]
            result['provenance'] = merged_prov
            fd0 = result.get('final_decision')
            if isinstance(fd0, dict):
                fd0 = {**fd0, 'provenance': merge_provenance(fd0.get('provenance'), merged_prov)}
                result['final_decision'] = fd0
        except Exception as _prov_exc:
            logger.debug('provenance aggregate skipped: %s', _prov_exc)

        # P0-5 HITL 确认面：高风险决策阻塞等待人工确认（禁止静默通过）
        # 放在 final_decision 写出之后、对外发布 completed 之前
        final_decision = result.get('final_decision')
        risk_assessment = result.get('risk_assessment') or {}
        hitl_meta = {'required': False, 'approved': None, 'approval_type': None}
        try:
            from app.agents.hitl import (
                approval_manager,
                should_request_hitl,
                build_approval_reason,
            )
            if should_request_hitl(final_decision, risk_assessment):
                hitl_meta['required'] = True
                gate_task_id = task_id or conversation_id or f"hitl-{stock_code}-{int(time.time())}"
                risk_level = (
                    (final_decision or {}).get('risk_level')
                    or risk_assessment.get('overall_risk')
                    or risk_assessment.get('risk_level')
                    or '高'
                )
                reason = build_approval_reason(final_decision, risk_assessment)
                logger.info(
                    f"HITL 闸门触发: task={gate_task_id} stock={stock_code} risk={risk_level}"
                )
                approved_decision = approval_manager.request_approval(
                    task_id=gate_task_id,
                    decision=final_decision or {},
                    risk_level=str(risk_level),
                    reason=reason,
                    risk_assessment=risk_assessment,
                )
                final_decision = approved_decision
                result['final_decision'] = approved_decision
                hitl_meta['approved'] = bool(approved_decision.get('approved'))
                hitl_meta['approval_type'] = approved_decision.get('approval_type')
                hitl_meta['reason'] = reason
                hitl_meta['task_id'] = gate_task_id
                if not approved_decision.get('approved'):
                    result['hitl_rejected'] = True
                    result['errors'] = list(result.get('errors') or []) + [
                        f"HITL拒绝: {approved_decision.get('human_feedback') or reason}"
                    ]
        except Exception as hitl_err:
            logger.warning(f"HITL 闸门异常: {hitl_err}")
            try:
                from app.agents.hitl import should_request_hitl as _should_hitl
                if _should_hitl(final_decision, risk_assessment):
                    hitl_meta = {
                        'required': True,
                        'approved': False,
                        'approval_type': 'error_reject',
                        'error': str(hitl_err)[:200],
                    }
                    result['hitl_rejected'] = True
                    if isinstance(final_decision, dict):
                        result['final_decision'] = {
                            **final_decision,
                            'approved': False,
                            'approval_type': 'error_reject',
                        }
            except Exception:
                pass
        result['hitl'] = hitl_meta

        # G5/G6/G7：终局 scorecard + 决策备忘 + 反思只读摘要（不写生产权重）
        try:
            from app.agents.scorecard import (
                compute_run_scorecard,
                build_decision_memo,
                summarize_reflection_readonly,
            )
            from app.core.event_bus import publish_run_scorecard
            from app.core.agent_memory import get_agent_memory as _gam_g7

            if not result.get('memory_context') and initial_state.get('memory_context'):
                result['memory_context'] = initial_state.get('memory_context')

            _sc = compute_run_scorecard(
                result,
                task_id=task_id or '',
                stock_code=stock_code,
            )
            _memo = build_decision_memo(result, scorecard=_sc)
            result['scorecard'] = _sc
            result['decision_memo'] = _memo
            _fd = result.get('final_decision')
            if not isinstance(_fd, dict):
                _fd = {}
            else:
                _fd = dict(_fd)
            _fd['scorecard'] = {
                'data_coverage': _sc.get('data_coverage'),
                'tool_success_rate': _sc.get('tool_success_rate'),
                'role_agreement': _sc.get('role_agreement'),
                'confidence_cap': _sc.get('confidence_cap'),
            }
            _fd['decision_memo'] = _memo
            if result.get('memory_context') is not None:
                _fd['memory_context'] = result.get('memory_context')
            try:
                _past = _gam_g7().get_past_reflections(stock_code, limit=3)
                _rs = summarize_reflection_readonly(_past, limit=3)
                if _rs:
                    result['reflection_summary'] = _rs
                    _fd['reflection_summary'] = _rs
            except Exception as _g7e:
                logger.debug('reflection summary skipped: %s', _g7e)
            result['final_decision'] = _fd
            _pub_payload = dict(_sc)
            _pub_payload['decision_memo'] = _memo
            if result.get('reflection_summary') is not None:
                _pub_payload['reflection_summary'] = result['reflection_summary']
            if result.get('memory_context') is not None:
                _pub_payload['memory_context'] = result['memory_context']
            publish_run_scorecard(
                _pub_payload,
                task_id=task_id or '',
                stock_code=stock_code,
            )
        except Exception as _sc_err:
            logger.warning('scorecard/memo compute failed: %s', _sc_err)

        # 保存到Agent记忆 + 发布完成事件
        try:
            from app.core.agent_memory import get_agent_memory
            from app.core.event_bus import get_event_bus, EVENT_ANALYSIS_COMPLETED
            get_agent_memory().save_analysis(stock_code, result)
            get_event_bus().publish(EVENT_ANALYSIS_COMPLETED, {
                'stock_code': stock_code,
                'decision': result.get('final_decision'),
                'hitl': hitl_meta,
            })
        except Exception:
            pass

        # 触发策略演化（基于历史反思）
        try:
            from app.agents.strategy_evolver import get_strategy_evolver
            from app.agents.reflection import ReflectionAgent
            evolver = get_strategy_evolver()
            past_reflections = ReflectionAgent.get_past_reflections(stock_code, limit=5)
            if len(past_reflections) >= 3:
                evolver.evolve_strategy(stock_code, past_reflections)
        except Exception:
            pass

        # [FIX-6] 成功路径清除 tracker
        try:
            set_progress_tracker(None)
        except Exception:
            pass
        return result
    except Exception as e:
        logger.error(f"Agent分析失败: {e}")
        # [FIX-6] 失败路径清除 tracker
        try:
            set_progress_tracker(None)
        except Exception:
            pass
        return {
            **initial_state,
            'errors': initial_state['errors'] + [str(e)],
            'final_decision': {
                'action': 'HOLD',
                'confidence': 0.0,
                'reasoning': f'分析过程出错: {str(e)}'
            }
        }


class CoordinatorAgent:
    """
    协调器Agent类封装，供外部模块导入使用。
    提供与其他Agent一致的类接口。
    """

    name = "协调器"

    @staticmethod
    def run(
        stock_code: str,
        market_type: str = 'A',
        research_depth: int = 3,
        selected_analysts: Optional[List[str]] = None,
        progress_callback=None
    ) -> Dict[str, Any]:
        """执行完整的Agent分析流程"""
        return run_agent_analysis(
            stock_code=stock_code,
            market_type=market_type,
            research_depth=research_depth,
            selected_analysts=selected_analysts,
            progress_callback=progress_callback
        )
