from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, ToolMessage, SystemMessage
from dotenv import load_dotenv
from meta_tool_create import create_tool
from meta_tool_exec import execute_tool
from datetime import datetime


from func2schema import func2json_schema
from pathlib import Path
from schema import QueryType, Plan, TaskRecord, State, TimelineEvent
import json
from prompts import (
    router_prompt,
    planner_prompt,
    replanner_prompt,
    worker_prompt,
    answerer_prompt,
    fallback_prompt,
    is_invalid_result,
)

load_dotenv()


class CARAgent:
    def __init__(self, config, verbose=True):
        self.config = config
        self.verbose = verbose  # 控制是否输出详细信息
        self.main_llm = ChatOpenAI(
            model_name=self.config.llm.main, temperature=self.config.llm.temperature
        )
        self.support_llm = ChatOpenAI(
            model_name=self.config.llm.support, temperature=self.config.llm.temperature
        )
        self._load_tools()
        self._setup()
        self.timeout = self.config.tool.timeout
        self.max_iterations = self.config.agent.max_iterations
        self.max_replans = self.config.agent.max_replans

        if self.verbose:
            print(f"\n{'='*80}")
            print(f"Agent 初始化完成")
            print(f"{'='*80}")
            print(f"主模型: {self.config.llm.main}")
            print(f"辅助模型: {self.config.llm.support}")
            print(f"温度: {self.config.llm.temperature}")
            print(f"最大迭代次数: {self.max_iterations}")
            print(f"最大重规划次数: {self.max_replans}")
            print(f"可用工具数: {len(self.available_tool)}")
            print(f"{'='*80}\n")

    def _load_tools(self):
        self.tool_dir = self.config.tool.dir
        with open("meta_tool_create.py", "r", encoding="utf-8") as f:
            self.json_schemas = [func2json_schema(f.read())]
        self.available_tool = set([s["function"]["name"] for s in self.json_schemas])
        for file in Path(self.tool_dir).glob("*.py"):
            code = file.read_text(encoding="utf-8")
            schema = func2json_schema(code)
            if schema["function"]["name"] not in self.available_tool:
                self.json_schemas.append(schema)
                self.available_tool.add(schema["function"]["name"])

    def _get_tool_details(self):
        dc = {
            s["function"]["name"]: s["function"]["description"]
            for s in self.json_schemas
        }
        return json.dumps(dc, ensure_ascii=False, indent=2)

    def _setup(self):
        self.router = self.support_llm.bind_tools([QueryType], tool_choice="QueryType")
        self.planer = self.main_llm.bind_tools([Plan], tool_choice="Plan")
        self.worker = self.main_llm.bind(tools=self.json_schemas)
        self.answerer = self.main_llm
        self.tool_details = self._get_tool_details()

    def update_worker_tools(self, func_code):
        new_tool_schema = func2json_schema(func_code)
        new_tool_name = new_tool_schema["function"]["name"]
        self.json_schemas = [
            s for s in self.json_schemas if s["function"]["name"] != new_tool_name
        ]
        self.available_tool.add(new_tool_name)
        self.json_schemas.append(new_tool_schema)
        self.worker = self.main_llm.bind(tools=self.json_schemas)
        self.tool_details = self._get_tool_details()

    def classify_query(self, query: str) -> QueryType:
        if self.verbose:
            print(f"\n{'='*80}")
            print(f"问题分类")
            print(f"{'='*80}")

        response = self.router.invoke(
            [
                SystemMessage(content=router_prompt),
                HumanMessage(
                    content=f"用户的问题：{query}\n目前可用的工具: {self.tool_details}"
                ),
            ]
        )
        if response.tool_calls:
            classification = response.tool_calls[-1]["args"]
            result = QueryType(**classification)
            if self.verbose:
                print(f"是否需要工具: {'是' if result.needs_tools else '否'}")
                print(f"原因: {result.reason}")
            return result
        else:
            result = QueryType(
                needs_tools=False, reason="无法明确分类，默认不需要调用工具。"
            )
            if self.verbose:
                print(f"是否需要工具: 否（无法明确分类）")
            return result

    def direct_answer(self, query: str) -> str:
        response = self.answerer.invoke([HumanMessage(content=query)])
        return response.content

    def generate_plan(self, query: str):
        if self.verbose:
            print(f"\n{'='*80}")
            print(f"生成执行计划")
            print(f"{'='*80}")

        prompt = planner_prompt.format(tool_details=self.tool_details)
        response = self.planer.invoke(
            [
                SystemMessage(content=prompt),
                HumanMessage(content=f"用户的需求: {query}"),
            ]
        )
        if response.tool_calls:
            plan_data = response.tool_calls[-1]["args"]
            plan = Plan(**plan_data)
            if self.verbose:
                print(f"目标: {plan.goal}")
                print(f"任务列表: ({len(plan.to_do_list)} 个步骤)")
                for i, task in enumerate(plan.to_do_list, 1):
                    print(f"  {i}. {task}")
            return plan
        else:
            if self.verbose:
                print(f"计划生成失败")
            return None

    def init_state(self, plan: Plan) -> State:
        return State(
            goal=plan.goal,
            to_be_done=plan.to_do_list,
            done=[],
            success_history=[],
            failure_history=[],
            is_finished=False,
            replan_count=0,
            timeline=[],
        )

    def solve_current_step(self, current_task: str, state: State):
        prompt = worker_prompt.format(
            current_task=current_task,
            done=state.done,
            success_history=self._format_history(state.success_history),
        )
        msg = [
            SystemMessage(content=prompt),
            HumanMessage(content=f"专注于解决当前步骤的任务: {current_task}"),
        ]
        tools_used = []

        for iteration in range(self.max_iterations):
            if self.verbose:
                print(f"  工具迭代 {iteration + 1}:")
            response = self.worker.invoke(msg)
            msg.append(response)

            if not response.tool_calls:
                content = response.content or ""
                # 检查模型是否认为任务失败了
                if (
                    "TASK_FAILED" in content
                    or "任务失败" in content
                    or "无法完成" in content
                ):
                    if self.verbose:
                        print(f"    任务失败")
                        print(
                            f"    原因: {content[:200]}..."
                            if len(content) > 200
                            else f"    原因: {content}"
                        )
                    return {
                        "success": False,
                        "result": content,
                        "tools_used": tools_used,
                    }
                if self.verbose:
                    print(f"    任务完成")
                    print(
                        f"    结果: {content[:200]}..."
                        if len(content) > 200
                        else f"    结果: {content}"
                    )
                return {
                    "success": True,
                    "result": content,
                    "tools_used": tools_used,
                }

            for i, tool_call in enumerate(response.tool_calls):
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_id = tool_call["id"]

                if self.verbose:
                    print(f"    调用工具: {tool_name}")
                    print(f"    参数:")
                    for key, value in tool_args.items():
                        value_str = str(value)
                        if len(value_str) > 100:
                            value_str = value_str[:100] + "..."
                        print(f"      {key}: {value_str}")

                if tool_name == "create_tool":
                    res = create_tool(**tool_args)
                    if res["success"]:
                        self.update_worker_tools(res["code"])
                        tools_used.append("create_tool")
                        if self.verbose:
                            print(f"    工具创建成功")
                        msg.append(
                            ToolMessage(
                                tool_call_id=tool_id,
                                content=f"工具创建成功",
                            )
                        )
                    else:
                        if self.verbose:
                            print(f"    工具创建失败: {res['error']}")
                        msg.append(
                            ToolMessage(
                                tool_call_id=tool_id,
                                content=f"工具创建失败: {res['error']}",
                            )
                        )
                else:
                    if tool_name in self.available_tool:
                        try:
                            result = execute_tool(
                                f"{self.config.tool.dir}/{tool_name}.py",
                                tool_name,
                                tool_args,
                            )
                            if self.verbose:
                                result_str = str(result)
                                if len(result_str) > 200:
                                    result_str = result_str[:200] + "..."
                                print(f"    返回结果: {result_str}")

                            if is_invalid_result(result):
                                if self.verbose:
                                    print(f"    结果无效")
                                msg.append(
                                    ToolMessage(
                                        tool_call_id=tool_id,
                                        content=f"{tool_name}执行返回了无效结果: {json.dumps(result, ensure_ascii=False)}",
                                    )
                                )
                            else:
                                tools_used.append(tool_name)
                                msg.append(
                                    ToolMessage(
                                        tool_call_id=tool_id,
                                        content=json.dumps(result, ensure_ascii=False),
                                    )
                                )
                        except Exception as e:
                            import traceback

                            error_traceback = traceback.format_exc()
                            if self.verbose:
                                print(f"    执行失败: {str(e)}")
                            msg.append(
                                ToolMessage(
                                    tool_call_id=tool_id, content=error_traceback
                                )
                            )
                    else:
                        error_msg = f"工具{tool_name}不在工具集中"
                        if self.verbose:
                            print(f"    {error_msg}")
                        msg.append(ToolMessage(tool_call_id=tool_id, content=error_msg))

        return {
            "success": False,
            "result": "TASK_FAILED: 达到最大迭代次数仍未完成任务",
            "tools_used": tools_used,
        }

    def replan_remaining_tasks(
        self, state: State, failed_task: str, failure_reason: str
    ):
        prompt = replanner_prompt.format(
            goal=state.goal,
            done=state.done,
            success_history=self._format_history(state.success_history),
            failure_history=self._format_history(state.failure_history),
            failed_task=failed_task,
            failure_reason=failure_reason,
            to_be_done=state.to_be_done,
            tool_details=self.tool_details,
        )
        response = self.planer.invoke(
            [
                SystemMessage(content=prompt),
                HumanMessage(content="请根据以上信息重新制定计划。"),
            ]
        )
        if response.tool_calls:
            plan_data = response.tool_calls[-1]["args"]
            return Plan(**plan_data)
        return None

    def step_next(self, state: State):
        if not state.to_be_done:
            # 所有任务完成,生成最终答案
            if self.verbose:
                print(f"\n{'='*80}")
                print(f"生成最终答案")
                print(f"{'='*80}")

            prompt = answerer_prompt.format(
                goal=state.goal,
                done=state.done,
                success_history=self._format_history(state.success_history),
            )
            final_response = self.answerer.invoke(
                [
                    SystemMessage(content=prompt),
                    HumanMessage(content="基于上述要求给出最终的回答。"),
                ]
            )

            # 记录最终答案事件
            self._log_event(
                state.timeline,
                "final_answer",
                "任务完成，生成最终回答",
                {"answer": final_response.content},
            )

            if self.verbose:
                answer_preview = (
                    final_response.content[:150] + "..."
                    if len(final_response.content) > 150
                    else final_response.content
                )
                print(f"最终答案: {answer_preview}")

            state.is_finished = True
            return state, final_response.content

        current_task = state.to_be_done[0]

        if self.verbose:
            print(f"\n{'='*80}")
            print(f"步骤 {len(state.done) + 1}: {current_task}")
            print(f"{'='*80}")

        # 记录任务开始事件
        self._log_event(
            state.timeline,
            "task_start",
            f"开始执行步骤: {current_task}",
            {
                "task": current_task,
                "step_index": len(state.done) + len(state.failure_history) + 1,
            },
        )

        exec_result = self.solve_current_step(current_task, state)

        if not exec_result["success"]:
            failure_reason = exec_result["result"]

            if self.verbose:
                print(f"\n步骤失败")
                print(
                    f"失败原因: {failure_reason[:150]}..."
                    if len(failure_reason) > 150
                    else f"失败原因: {failure_reason}"
                )
                print(f"\n{'='*80}")
                print(f"重新规划 (第 {state.replan_count + 1} 次)")
                print(f"{'='*80}")

            # 记录任务失败事件
            self._log_event(
                state.timeline,
                "task_failed",
                f"步骤失败: {current_task}",
                {
                    "task": current_task,
                    "reason": failure_reason,
                    "tools_used": exec_result["tools_used"],
                },
            )

            state.failure_history.append(
                TaskRecord(
                    task=current_task,
                    solution=failure_reason,
                    tool_used=(
                        ",".join(exec_result["tools_used"])
                        if exec_result["tools_used"]
                        else None
                    ),
                )
            )

            # 记录重新规划事件
            self._log_event(
                state.timeline,
                "replan",
                f"重新规划任务（第 {state.replan_count + 1} 次）",
                {
                    "failed_task": current_task,
                    "remaining_tasks": state.to_be_done,
                },
            )

            print(f"从当前位置重新规划...")
            state.replan_count += 1
            new_plan = self.replan_remaining_tasks(state, current_task, failure_reason)

            if new_plan:
                state.to_be_done = new_plan.to_do_list
                if self.verbose:
                    print(f"新任务列表: ({len(new_plan.to_do_list)} 个步骤)")
                    for i, task in enumerate(new_plan.to_do_list, 1):
                        print(f"  {i}. {task}")
                else:
                    print(f"新的任务列表: {state.to_be_done}")

                # 记录重新规划成功事件
                self._log_event(
                    state.timeline,
                    "replan_success",
                    f"重新规划完成，新增 {len(new_plan.to_do_list)} 个步骤",
                    {"new_todo_list": new_plan.to_do_list},
                )
            else:
                if self.verbose:
                    print(f"重新规划失败，无法生成新计划")
                else:
                    print("重新规划失败，无法生成新计划")
                state.is_finished = True

            return state, None
        else:
            # 任务成功
            result = exec_result["result"]

            # 记录任务成功事件
            self._log_event(
                state.timeline,
                "task_success",
                f"步骤完成: {current_task}",
                {
                    "task": current_task,
                    "solution": result,
                    "tools_used": exec_result["tools_used"],
                },
            )

            # 记录到成功历史
            state.success_history.append(
                TaskRecord(
                    task=current_task,
                    solution=result,
                    tool_used=(
                        ",".join(exec_result["tools_used"])
                        if exec_result["tools_used"]
                        else None
                    ),
                )
            )

            # 移动任务队列
            state.done.append(current_task)
            state.to_be_done = state.to_be_done[1:]

            if self.verbose:
                print(f"\n步骤完成，剩余任务: {len(state.to_be_done)} 个")
            else:
                print(f"【任务结束】, 剩余任务: {len(state.to_be_done)}")

            return state, None

    def workflow(self, query: str):
        """
        主工作流程
        """
        # 记录用户问题事件
        timeline = []
        self._log_event(timeline, "query", f"用户问题: {query}", {"question": query})

        classification = self.classify_query(query)

        # 记录分类事件
        self._log_event(
            timeline,
            "classification",
            f"问题分类: {'需要工具' if classification.needs_tools else '直接回答'}",
            {
                "needs_tools": classification.needs_tools,
                "reason": classification.reason,
            },
        )

        if not classification.needs_tools:
            if self.verbose:
                print(f"\n{'='*80}")
                print(f"直接回答（无需工具）")
                print(f"{'='*80}")
            else:
                print("不需要调用工具，直接回答。")
            answer = self.direct_answer(query)

            # 记录直接回答事件
            self._log_event(
                timeline,
                "direct_answer",
                "直接回答问题（无需工具）",
                {"answer": answer},
            )

            # 写日志
            self._write_timeline_log(query, timeline)

            return {"final_answer": answer}

        plan = self.generate_plan(query)
        if not plan:
            if self.verbose:
                print(f"\n{'='*80}")
                print(f"无法生成计划，停止执行")
                print(f"{'='*80}")
            else:
                print("无法生成计划，停止执行。")

            # 记录计划失败事件
            self._log_event(timeline, "error", "无法生成有效的执行计划", None)

            # 写日志
            self._write_timeline_log(query, timeline)

            return {"final_answer": "无法为该问题生成有效的执行计划"}

        # 记录计划生成事件
        self._log_event(
            timeline,
            "plan",
            f"生成计划: {len(plan.to_do_list)} 个步骤",
            {"goal": plan.goal, "todo_list": plan.to_do_list},
        )

        print(f"生成的计划: {plan.to_do_list}")
        state = self.init_state(plan)
        state.timeline = timeline  # 将时间线绑定到 state

        try:
            while not state.is_finished:
                # 检查是否超过最大重新规划次数
                if state.replan_count > self.max_replans:
                    if self.verbose:
                        print(f"\n{'='*80}")
                        print(
                            f"达到最大重新规划次数 ({self.max_replans})，使用回退方案"
                        )
                        print(f"{'='*80}")
                    else:
                        print(
                            "达到最大重新规划次数，停止执行，尝试用LLM自身能力直接回答。"
                        )

                    # 记录回退事件
                    self._log_event(
                        state.timeline,
                        "fallback",
                        f"达到最大重新规划次数({self.max_replans})，使用回退方案",
                        {
                            "replan_count": state.replan_count,
                            "max_replans": self.max_replans,
                        },
                    )

                    # 向 Fallback 提供成功和失败历史
                    prompt = fallback_prompt.format(
                        goal=state.goal,
                        done=state.done,
                        success_history=self._format_history(state.success_history),
                        failure_history=self._format_history(state.failure_history),
                    )
                    fallback_answer = self.answerer.invoke(
                        [SystemMessage(content=prompt)]
                    ).content

                    # 记录回退答案事件
                    self._log_event(
                        state.timeline,
                        "final_answer",
                        "任务未完全完成，生成回退答案",
                        {"answer": fallback_answer},
                    )

                    # 写日志
                    self._write_timeline_log(query, state.timeline)

                    return {"final_answer": fallback_answer}

                state, final_answer = self.step_next(state)

                # 如果返回了最终答案,则完成
                if final_answer is not None:
                    # 写日志
                    self._write_timeline_log(query, state.timeline)

                    return {"final_answer": final_answer}

            # 写日志
            self._write_timeline_log(query, state.timeline)

            return {"final_answer": "任务执行完成，但未获取到最终答案"}

        except Exception as e:
            # 记录异常事件
            self._log_event(
                state.timeline,
                "error",
                f"执行过程中发生异常: {type(e).__name__}",
                {"error_type": type(e).__name__, "error_message": str(e)},
            )

            # 写日志
            self._write_timeline_log(query, state.timeline)

            # 重新抛出异常
            raise

    def _format_history(self, history_list):
        if not history_list:
            return "暂无历史记录"

        formatted = []
        for i, record in enumerate(history_list, 1):
            tool_info = f" (使用工具: {record.tool_used})" if record.tool_used else ""
            formatted.append(
                f"{i}. 任务: {record.task}\n"
                f"   结果: {record.solution}{tool_info}\n"
                f"   时间: {record.timestamp}"
            )
        return "\n".join(formatted)

    def _log_event(
        self, timeline: list, event_type: str, description: str, details: dict = None
    ):
        """
        记录事件到时间线

        Args:
            timeline: 时间线列表 (可以是 state.timeline 或独立的 list)
            event_type: 事件类型
            description: 事件描述
            details: 事件详细信息 (可选)
        """
        timeline.append(
            TimelineEvent(
                event_type=event_type, description=description, details=details
            )
        )

    def _write_timeline_log(self, query: str, timeline: list):
        """
        将时间线日志写入文件

        Args:
            query: 用户原始问题
            timeline: TimelineEvent 列表
        """
        if not self.config.output.enable_log:
            return
        try:
            # 使用第一个事件的时间作为文件名
            if timeline:
                start_time_str = timeline[0].timestamp
                start_time = datetime.fromisoformat(start_time_str)
            else:
                start_time = datetime.now()

            filename = start_time.strftime("%Y%m%d_%H%M%S_%f")[:-3] + ".json"

            # 确保输出目录存在
            output_dir = Path(self.config.output.dir)
            output_dir.mkdir(parents=True, exist_ok=True)

            filepath = output_dir / filename

            # 构建日志内容
            log_data = {
                "query": query,
                "start_time": timeline[0].timestamp if timeline else None,
                "end_time": timeline[-1].timestamp if timeline else None,
                "total_events": len(timeline),
                "timeline": [
                    {
                        "timestamp": event.timestamp,
                        "event_type": event.event_type,
                        "description": event.description,
                        "details": event.details,
                    }
                    for event in timeline
                ],
            }

            # 写入 JSON 文件
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(log_data, f, ensure_ascii=False, indent=2)

            print(f"\n[日志已保存]: {filepath}")

        except Exception as e:
            print(f"\n[警告] 写入日志失败: {e}")
            # 不抛出异常,不影响主流程

    def run(self, query: str):
        result = self.workflow(query)
        return result.get("final_answer", str(result))


if __name__ == "__main__":
    from config import cfg

    agent = CARAgent(cfg)
    while True:
        print("=" * 60)
        query = input("请输入问题 (或输入 'exit' 退出): ")
        print("=" * 60)
        if query.lower() == "exit":
            break
        answer = agent.run(query)
        print("=" * 60)
        print(f"回答:\n{answer}")
