"""
ToolHopPro 数据集测试脚本

该脚本用于系统性测试 Agent 在 ToolHopPro 数据集上的表现。
主要功能：
1. 从 ToolHopPro.json 加载问题和工具信息
2. 为每个问题准备困难工具（生成 .py 文件和 tool_info.json）
3. 运行 Agent 并评估答案正确性
4. 记录详细的测试日志

运行方法：
  测试所有问题（工具缺失场景）：
    uv run test_arc_mode.py --type missing

  测试所有问题（完整工具场景）：
    uv run test_arc_mode.py --type complete

  测试指定问题ID（工具缺失场景）：
    uv run test_arc_mode.py --type missing --id 0

  测试指定问题ID（完整工具场景）：
    uv run test_arc_mode.py --type complete --id 0

  测试多个指定问题ID：
    uv run test_arc_mode.py --type missing --id 0 1 2 3

  关闭Agent详细输出（仅显示测试过程）：
    uv run test_arc_mode.py --type missing --id 0 --no-verbose
"""

import os
import re
import json
import time
from datetime import datetime
from typing import Any, Dict, List, Tuple

from langchain_openai import ChatOpenAI
from car_agent import CARAgent
from config import cfg


def load_json(path: str) -> Any:
    """加载 JSON 文件"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data: Any):
    """保存数据到 JSON 文件"""
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clear_tool_files():
    """清空工具目录中的所有 .py 文件"""
    os.makedirs(cfg.tool.dir, exist_ok=True)
    deleted_files = []
    for filename in os.listdir(cfg.tool.dir):
        if filename.endswith(".py"):
            file_path = os.path.join(cfg.tool.dir, filename)
            os.remove(file_path)
            deleted_files.append(filename)
            print(f"  🗑️  已删除: {filename}")
    if deleted_files:
        print(f"  ✅ 共删除 {len(deleted_files)} 个工具文件")
    else:
        print(f"  ℹ️  工具目录为空，无需删除")


def clear_tool_info():
    """清空 tool_info.json 文件"""
    save_json("tool_set/tool_info.json", [])
    print("  🗑️  已清空: tool_info.json")


def fix_python_code(code: str) -> str:
    """
    修复 Python 代码中的常见语法问题
    主要修复引号冲突问题
    """
    import ast

    try:
        ast.parse(code)
        return code
    except SyntaxError:
        print("⚠️  检测到语法错误，尝试修复引号问题...")

        # 尝试修复单引号字符串中包含单引号的情况
        def fix_quotes(match):
            content = match.group(1)
            if "'" in content:
                return f'"{content}"'
            return match.group(0)

        # 匹配单引号字符串，考虑转义
        fixed_code = re.sub(r"'([^'\\]*(?:\\.[^'\\]*)*)'", fix_quotes, code)

        try:
            ast.parse(fixed_code)
            print("✅ 引号问题已修复")
            return fixed_code
        except SyntaxError as e:
            print(f"⚠️  无法自动修复语法错误: {str(e)}")
            return code

    """
    为函数生成 argparse 风格的命令行接口包装代码

    设计原则：
    1. Boolean 参数使用 action='store_true'，与调用方一致
    2. Array 参数用逗号分隔，支持空列表
    3. Object 参数使用 JSON 格式
    4. 所有参数类型都经过验证和类型转换
    5. 生成的代码健壮、可读性强

    Args:
        func_name: 函数名称
        parameters: 函数参数的 JSON Schema 定义

    Returns:
        CLI wrapper 代码字符串
    """
    properties = parameters.get("properties", {})
    required = parameters.get("required", [])

    wrapper = f"""
if __name__ == "__main__":
    import argparse
    import json
    import sys
    
    parser = argparse.ArgumentParser(
        description="运行 {func_name}",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
"""

    # 为每个参数添加命令行选项
    for param_name, param_info in properties.items():
        param_type = param_info.get("type", "string").lower()
        param_desc = param_info.get("description", "").replace('"', '\\"')  # 转义引号
        is_required = param_name in required

        if param_type in ("boolean", "bool"):
            # Boolean 参数：使用 action='store_true'
            # 调用方传 --key 时为 True，不传时为 False
            wrapper += f"    parser.add_argument(\n"
            wrapper += f'        "--{param_name}",\n'
            wrapper += f'        action="store_true",\n'
            wrapper += f'        help="{param_desc}"\n'
            wrapper += f"    )\n"

        elif param_type in ("integer", "int"):
            # 整数参数
            req_arg = ", required=True" if is_required else ""
            wrapper += f"    parser.add_argument(\n"
            wrapper += f'        "--{param_name}",\n'
            wrapper += f"        type=int{req_arg},\n"
            wrapper += f'        help="{param_desc}"\n'
            wrapper += f"    )\n"

        elif param_type in ("number", "float", "double"):
            # 浮点数参数
            req_arg = ", required=True" if is_required else ""
            wrapper += f"    parser.add_argument(\n"
            wrapper += f'        "--{param_name}",\n'
            wrapper += f"        type=float{req_arg},\n"
            wrapper += f'        help="{param_desc}"\n'
            wrapper += f"    )\n"

        elif param_type == "array":
            # 数组参数：使用逗号分隔
            # 调用方传 --key "val1,val2,val3"
            req_arg = ", required=True" if is_required else ""
            wrapper += f"    parser.add_argument(\n"
            wrapper += f'        "--{param_name}",\n'
            wrapper += f'        type=lambda x: x.split(",") if x else []{req_arg},\n'
            wrapper += f'        help="{param_desc} (逗号分隔)"\n'
            wrapper += f"    )\n"

        elif param_type == "object":
            # 对象参数：使用 JSON 格式
            # 调用方传 --key '{{"a": 1, "b": 2}}'
            req_arg = ", required=True" if is_required else ""
            wrapper += f"    parser.add_argument(\n"
            wrapper += f'        "--{param_name}",\n'
            wrapper += f"        type=json.loads{req_arg},\n"
            wrapper += f'        help="{param_desc} (JSON 格式)"\n'
            wrapper += f"    )\n"

        else:
            # 默认为字符串类型
            req_arg = ", required=True" if is_required else ""
            wrapper += f"    parser.add_argument(\n"
            wrapper += f'        "--{param_name}",\n'
            wrapper += f"        type=str{req_arg},\n"
            wrapper += f'        help="{param_desc}"\n'
            wrapper += f"    )\n"

    # 解析参数并调用函数
    wrapper += f"""
    try:
        args = parser.parse_args()
    except SystemExit as e:
        # argparse 解析失败时会调用 sys.exit()
        # 捕获后重新抛出，确保返回正确的退出码
        sys.exit(e.code)
    
    # 过滤掉 None 值的参数（未提供的可选参数）
    kwargs = {{k: v for k, v in vars(args).items() if v is not None}}
    
    try:
        # 调用函数并打印结果
        result = {func_name}(**kwargs)
        print(result)
    except Exception as e:
        # 捕获函数执行时的异常
        print(f"错误: {{type(e).__name__}}: {{str(e)}}", file=sys.stderr)
        sys.exit(1)
"""

    return wrapper


def setup_hard_tools_for_problem(problem: Dict[str, Any], load_all: bool = False):
    """
    为指定问题设置工具

    Args:
        problem: 包含问题信息和工具定义的字典
        load_all: 是否加载所有工具（True=加载所有，False=只加载困难工具）

    工作流程：
    1. 清空 tool_info.json
    2. 遍历问题中的所有工具
    3. 根据 load_all 参数决定加载哪些工具
    4. 为每个工具生成 .py 文件
    5. 将工具的 schema 添加到 tool_info.json
    """
    # 清空 tool_info.json
    clear_tool_info()

    tools = problem.get("tools", {})
    tool_schemas = []

    print(f"\n📦 【步骤2】准备工具")
    print(f"  ℹ️  问题ID: {problem.get('id')}")
    print(f"  ℹ️  工具总数: {len(tools)}")
    print(f"  ℹ️  加载模式: {'加载所有工具' if load_all else '只加载困难工具'}")
    print(f"  {'-'*76}")

    easy_count = sum(1 for t in tools.values() if t.get("easy", False))
    hard_count = len(tools) - easy_count
    print(f"  📊 简单工具: {easy_count} 个 | 困难工具: {hard_count} 个")

    for idx, (tool_name, tool_info) in enumerate(tools.items(), 1):
        # 根据 load_all 参数决定是否跳过简单工具
        is_easy = tool_info.get("easy", False)

        if not load_all and is_easy:
            print(f"  [{idx}/{len(tools)}] ⏭️  跳过简单工具: {tool_name}")
            continue

        tool_type = "简单" if is_easy else "困难"
        print(f"  [{idx}/{len(tools)}] 🔧 处理{tool_type}工具: {tool_name}")

        try:
            # 1. 提取工具信息
            implement_code = tool_info.get("implement", "")
            description = tool_info.get("description", "")
            parameters = tool_info.get(
                "parameters", {"type": "object", "properties": {}, "required": []}
            )

            if not implement_code:
                print(f"       ⚠️  缺少实现代码，跳过")
                continue

            # 获取参数信息
            param_count = len(parameters.get("properties", {}))
            print(f"       ℹ️  参数个数: {param_count}")
            print(
                f"       ℹ️  描述: {description[:60]}..."
                if len(description) > 60
                else f"       ℹ️  描述: {description}"
            )

            # 2. 修复代码语法问题
            fixed_code = fix_python_code(implement_code)

            # 4. 写入 .py 文件
            py_path = os.path.join(cfg.tool.dir, f"{tool_name}.py")
            full_code = fixed_code

            with open(py_path, "w", encoding="utf-8") as f:
                f.write(full_code)

            print(f"       ✅ 已生成工具文件: {tool_name}.py")

            # 5. 构建 JSON Schema（OpenAI Function Calling 格式）
            tool_schema = {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": description,
                    "parameters": parameters,
                },
            }

            tool_schemas.append(tool_schema)

        except Exception as e:
            print(f"       ❌ 处理失败: {str(e)}")
            continue

    # 6. 写入 tool_info.json
    if tool_schemas:
        save_json("tool_set/tool_info.json", tool_schemas)
        print(f"  ✅ 已将 {len(tool_schemas)} 个工具写入 tool_info.json")
    else:
        print("  ⚠️  没有找到可用的工具")


def evaluate_answer_with_llm(question: str, expected: str, predicted: str) -> bool:
    """
    使用 LLM 评估预测答案是否正确

    Args:
        question: 问题内容
        expected: 期望答案
        predicted: 预测答案

    Returns:
        是否正确
    """
    print(f"\n📊 【步骤4】评估答案")
    print(f"  ℹ️  使用模型: gpt-4o-mini")

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    prompt = f"""根据问题以及预期答案和系统输出答案，判断系统输出答案是否正确回答了问题。
问题: {question}
预期答案: {expected}
系统输出答案: {predicted}

评估标准：
1. 只需要判断预测答案和预期答案在内容上表达是否一致、是否正确地回答了问题即可
2. 不需要考虑任何格式、形式上的问题
3. 语言种类不考虑，小数点后的 0 不考虑

请只回答 "正确" 或 "错误"，不要有其他内容。"""

    try:
        print(f"  🔄 正在调用 LLM 进行评估...")
        response = llm.invoke(prompt)
        result = response.content.strip()
        is_correct = "正确" in result
        print(f"  ✅ LLM 评估结果: {result}")
        return is_correct
    except Exception as e:
        print(f"  ⚠️  LLM 评估失败: {str(e)}")
        print(f"  ℹ️  降级到字符串匹配...")
        # 降级到简单字符串匹配
        is_correct = str(expected).strip().lower() == str(predicted).strip().lower()
        print(f"  ✅ 字符串匹配结果: {'正确' if is_correct else '错误'}")
        return is_correct


def test_single_problem(
    problem: Dict[str, Any], load_all: bool = False, verbose: bool = True
) -> Tuple[str, bool]:
    """
    测试单个问题

    Args:
        problem: 问题字典，包含 id, question, answer, tools
        load_all: 是否加载所有工具
        verbose: 是否输出Agent执行的详细信息

    Returns:
        (预测答案, 是否正确)
    """
    qid = problem.get("id")
    question = problem.get("question", "")
    expected_answer = problem.get("answer", "")

    print(f"\n{'='*80}")
    print(f"🔍 测试问题 #{qid}")
    print(f"{'='*80}")
    print(f"❓ 问题内容: {question}")
    print(f"🎯 预期答案: {expected_answer}")
    print(f"{'='*80}")

    try:
        # 1. 清空旧的工具文件
        print(f"\n🧹 【步骤1】清理旧的工具文件")
        clear_tool_files()

        # 2. 为当前问题设置工具
        setup_hard_tools_for_problem(problem, load_all=load_all)

        # 3. 创建 Agent 实例
        print(f"\n🤖 【步骤3】初始化并运行 Agent")
        print(f"  ℹ️  主模型: {cfg.llm.main}")
        print(f"  ℹ️  辅助模型: {cfg.llm.support}")
        print(f"  ℹ️  最大迭代次数: {cfg.agent.max_iterations}")
        print(f"  ℹ️  详细输出: {'开启' if verbose else '关闭'}")

        agent = CARAgent(config=cfg, verbose=verbose)
        print(f"  ✅ Agent 初始化完成")

        # 4. 运行 Agent 回答问题
        print(f"  {'-'*76}")
        print(f"  💭 Agent 开始思考和推理...")
        print(f"  {'-'*76}")

        predicted_answer = agent.run(question)

        print(f"  {'-'*76}")
        print(f"  ✅ Agent 执行完成")
        print(f"  📝 预测答案: {predicted_answer}")

        # 5. 评估答案
        is_correct = evaluate_answer_with_llm(
            question, expected_answer, predicted_answer
        )

        # 6. 输出结果
        print(f"\n{'='*80}")
        print(f"📋 测试结果总结")
        print(f"{'='*80}")
        print(f"🎯 预期答案: {expected_answer}")
        print(f"📝 预测答案: {predicted_answer}")
        print(f"✨ 评估结果: {'✅ 正确' if is_correct else '❌ 错误'}")
        print(f"{'='*80}")

        return predicted_answer, is_correct

    except Exception as e:
        error_msg = f"错误: {str(e)}"
        print(f"\n{'='*80}")
        print(f"❌ 测试问题 #{qid} 时发生错误")
        print(f"{'='*80}")
        print(f"错误信息: {error_msg}")
        print(f"{'='*80}")
        import traceback

        print("\n详细错误堆栈:")
        traceback.print_exc()
        return error_msg, False


def write_log_header(log_file: str):
    """写入日志文件头部"""
    with open(log_file, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("ToolHopPro 数据集测试结果\n")
        f.write("=" * 80 + "\n")
        f.write(f"测试开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"配置信息:\n")
        f.write(f"  - 主模型: {cfg.llm.main}\n")
        f.write(f"  - 辅助模型: {cfg.llm.support}\n")
        f.write(f"  - 最大迭代次数: {cfg.agent.max_iterations}\n")
        f.write(f"  - 工具目录: {cfg.tool.dir}\n")
        f.write("=" * 80 + "\n\n")


def write_log_entry(
    log_file: str,
    qid: int,
    question: str,
    expected: str,
    predicted: str,
    is_correct: bool,
    accuracy: float,
):
    """写入单个测试记录"""
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"问题 ID: {qid}\n")
        f.write(f"{'='*80}\n")
        f.write(f"问题内容:\n{question}\n\n")
        f.write(f"预期答案: {expected}\n")
        f.write(f"预测答案: {predicted}\n")
        f.write(f"测试结果: {'✅ 正确' if is_correct else '❌ 错误'}\n")
        f.write(
            f"当前累计正确率: {accuracy:.2%} ({int(accuracy * (qid + 1))}/{qid + 1})\n"
        )
        f.write(f"{'-'*80}\n\n")


def write_log_footer(log_file: str, total: int, correct: int, accuracy: float):
    """写入日志文件尾部总结"""
    with open(log_file, "a", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("测试总结\n")
        f.write("=" * 80 + "\n")
        f.write(f"测试完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"总问题数: {total}\n")
        f.write(f"正确答案数: {correct}\n")
        f.write(f"错误答案数: {total - correct}\n")
        f.write(f"最终正确率: {accuracy:.2%}\n")
        f.write("=" * 80 + "\n")


def main():
    """主测试函数"""
    import argparse

    # 解析命令行参数
    parser = argparse.ArgumentParser(
        description="ToolHopPro 数据集测试",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  测试所有问题（工具缺失场景）:
    uv run test_arc_mode.py --type missing
  
  测试所有问题（完整工具场景）:
    uv run test_arc_mode.py --type complete
  
  测试指定问题ID:
    uv run test_arc_mode.py --type missing --id 0
  
  测试多个问题ID:
    uv run test_arc_mode.py --type missing --id 0 1 2 3
        """,
    )
    parser.add_argument(
        "--type",
        type=str,
        default="missing",
        choices=["missing", "complete"],
        help="测试类型：missing=只加载困难工具（工具缺失场景），complete=加载所有工具",
    )
    parser.add_argument(
        "--id",
        type=int,
        nargs="+",
        default=None,
        help="指定要测试的问题ID（可以指定多个，如: --id 0 1 2）。不指定则测试所有问题",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=True,
        help="输出Agent执行的详细信息（默认开启）",
    )
    parser.add_argument(
        "--no-verbose",
        dest="verbose",
        action="store_false",
        help="关闭Agent执行的详细信息输出",
    )
    args = parser.parse_args()

    load_all = args.type == "complete"

    print("\n" + "=" * 80)
    print("🚀 ToolHopPro 数据集系统性测试")
    print("=" * 80)
    print(f"📌 测试模式: {args.type.upper()}")
    print(
        f"   {'✅ 加载所有工具（完整场景）' if load_all else '⚠️  只加载困难工具（工具缺失场景）'}"
    )
    if args.id:
        print(f"🎯 测试范围: 指定问题ID = {args.id}")
    else:
        print(f"🎯 测试范围: 所有问题")
    print(f"📊 详细输出: {'开启' if args.verbose else '关闭'}")
    print("=" * 80 + "\n")

    # 加载数据
    print("📁 正在加载 ToolHopPro.json...")
    try:
        toolhop_data = load_json("ToolHopPro.json")
        print(f"✅ 成功加载 {len(toolhop_data)} 个问题\n")
    except FileNotFoundError:
        print("❌ 错误: 未找到 ToolHopPro.json 文件")
        return
    except json.JSONDecodeError as e:
        print(f"❌ 错误: JSON 解析失败 - {str(e)}")
        return

    # 筛选要测试的问题
    if args.id:
        # 将数据转换为字典以便按ID查找
        data_dict = {item["id"]: item for item in toolhop_data}

        # 验证所有指定的ID是否存在
        invalid_ids = [qid for qid in args.id if qid not in data_dict]
        if invalid_ids:
            print(f"❌ 错误: 以下问题ID不存在: {invalid_ids}")
            print(f"   有效的ID范围: 0 - {len(toolhop_data) - 1}")
            return

        # 按指定ID筛选问题
        problems_to_test = [data_dict[qid] for qid in args.id]
        print(f"📋 已筛选出 {len(problems_to_test)} 个问题进行测试")
        for qid in args.id:
            print(f"   - 问题 #{qid}: {data_dict[qid]['question'][:60]}...")
        print()
    else:
        problems_to_test = toolhop_data

    # 初始化日志（根据模式使用不同的日志文件）
    if args.id:
        log_file = (
            f"toolhop_pro_test_results_{args.type}_id_{'_'.join(map(str, args.id))}.txt"
        )
    else:
        log_file = f"toolhop_pro_test_results_{args.type}.txt"

    write_log_header(log_file)
    print(f"📝 日志文件: {log_file}\n")

    # 统计变量
    total_questions = 0
    correct_answers = 0

    # 测试每个问题
    for i, problem in enumerate(problems_to_test):
        qid = problem.get("id")
        question = problem.get("question", "")
        expected_answer = problem.get("answer", "")

        total_questions += 1

        # 显示当前进度
        print(f"\n{'#'*80}")
        print(f"进度: [{i + 1}/{len(problems_to_test)}]")
        print(f"{'#'*80}")

        # 测试单个问题
        predicted_answer, is_correct = test_single_problem(
            problem, load_all=load_all, verbose=args.verbose
        )

        if is_correct:
            correct_answers += 1

        # 计算当前正确率
        current_accuracy = correct_answers / total_questions

        # 记录到日志
        write_log_entry(
            log_file,
            qid,
            question,
            expected_answer,
            predicted_answer,
            is_correct,
            current_accuracy,
        )

        # 输出累计统计
        print(f"\n{'#'*80}")
        print(
            f"📊 累计统计: 已测试 {total_questions}/{len(problems_to_test)} "
            f"| 正确率: {current_accuracy:.2%} ({correct_answers}/{total_questions})"
        )
        print(f"{'#'*80}\n")

        # 短暂延迟，避免请求过快
        if i < len(problems_to_test) - 1:  # 不是最后一个问题
            print("⏸️  等待 1 秒后继续下一个问题...\n")
            time.sleep(1)

    # 计算最终结果
    final_accuracy = correct_answers / total_questions if total_questions > 0 else 0

    # 写入日志尾部
    write_log_footer(log_file, total_questions, correct_answers, final_accuracy)

    # 输出最终结果
    print("\n" + "=" * 80)
    print("🎯 测试完成！")
    print("=" * 80)
    print(f"总问题数: {total_questions}")
    print(f"正确答案数: {correct_answers}")
    print(f"错误答案数: {total_questions - correct_answers}")
    print(f"最终正确率: {final_accuracy:.2%}")
    print(f"\n📝 详细结果已保存至: {log_file}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
