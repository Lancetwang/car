from typing import List, Literal, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class TimelineEvent(BaseModel):

    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(), description="事件发生时间"
    )
    event_type: Literal[
        "query",
        "classification",
        "plan",
        "task_start",
        "task_success",
        "task_failed",
        "replan",
        "replan_success",
        "final_answer",
        "direct_answer",
        "fallback",
        "error",
    ] = Field(description="事件类型")
    description: str = Field(description="事件的人类可读描述")
    details: Optional[Dict[str, Any]] = Field(
        default=None, description="事件的详细信息(可选)"
    )


class QueryType(BaseModel):

    needs_tools: bool = Field(
        description="判断用户的查询是否需要使用外部工具来回答。如果需要工具则设置为 `true`，否则为 `false`。"
    )
    reason: str = Field(
        description="关于 `needs_tools` 决策的原因说明。例如，'用户正在询问今天的天气，需要使用天气API工具。'"
    )


class Plan(BaseModel):
    """
    拆解用户的目标为一个逐步执行的计划。
    """

    goal: str = Field(description="用户的原始问题")
    to_do_list: List[str] = Field(
        description="为了解决用户的问题而拆分出的一个按顺序排列的、逐步执行的任务清单。列表中的每个字符串应表示一个单独的、可操作的步骤。"
    )


class TaskRecord(BaseModel):
    """
    任务执行记录 - 用于详细记录任务的执行过程和结果
    """

    task: str = Field(description="任务描述")
    solution: str = Field(description="执行结果或失败原因")
    tool_used: Optional[str] = Field(default=None, description="使用的工具名称")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(), description="执行时间戳"
    )


class State(BaseModel):
    """
    状态机 - 追踪整个任务执行流程
    职责分离:
    - to_be_done/done: 轻量级任务队列管理
    - success_history: 成功任务的详细记录,供依赖查询和最终回答使用
    - failure_history: 失败任务的详细记录,供重新规划时分析错误原因
    """

    goal: str = Field(description="用户提出的主要问题、诉求")

    # 任务队列 (轻量级字符串列表)
    to_be_done: List[str] = Field(default=[], description="待完成的任务队列")
    done: List[str] = Field(default=[], description="已完成的任务列表")

    # 执行历史 (详细记录,按成功/失败分离)
    success_history: List[TaskRecord] = Field(
        default=[], description="成功任务的详细执行记录,供后续任务依赖和最终回答使用"
    )
    failure_history: List[TaskRecord] = Field(
        default=[], description="失败任务的详细执行记录,供重新规划时分析错误原因"
    )

    # 状态标记
    is_finished: bool = Field(default=False, description="判断用户的目标是否已经完成")
    replan_count: int = Field(default=0, description="重新规划次数计数器")

    # 时间线日志 (用于记录完整执行过程)
    timeline: List[TimelineEvent] = Field(
        default=[], description="按时间顺序记录的事件日志,用于生成执行日志文件"
    )
