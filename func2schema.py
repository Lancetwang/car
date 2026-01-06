#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
函数字符串转 JSON Schema 工具

将 Python 函数定义字符串转换为 OpenAI Function Calling 格式的 JSON Schema
"""

import ast
import re
import json
from typing import Dict, Any, Optional


def func2json_schema(content: str) -> Dict[str, Any]:
    """
    将函数字符串转换为 JSON Schema

    Args:
        content: 函数定义的字符串，包含函数签名、类型注解和文档字符串

    Returns:
        符合 OpenAI Function Calling 格式的 JSON Schema

    Example:
        >>> func_str = '''
        ... def weather(location: str, unit: str = "celsius") -> str:
        ...     \"\"\"获取指定位置的天气信息
        ...
        ...     Args:
        ...         location: 位置名称
        ...         unit: 温度单位，可选值：celsius, fahrenheit
        ...     \"\"\"
        ...     pass
        ... '''
        >>> schema = func2json_schema(func_str)
    """
    try:
        # 解析函数字符串为 AST
        tree = ast.parse(content)

        # 查找第一个函数定义
        func_def = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                func_def = node
                break

        if not func_def:
            raise ValueError("未找到函数定义")

        # 提取函数信息
        func_name = func_def.name
        docstring = ast.get_docstring(func_def) or ""

        # 提取主要描述（第一行或第一段）
        description = _extract_description(docstring)

        # 提取参数信息
        parameters = _extract_parameters(func_def, docstring)

        # 构建 JSON Schema
        schema = {
            "type": "function",
            "function": {
                "name": func_name,
                "description": description,
                "parameters": parameters,
            },
        }

        return schema

    except SyntaxError as e:
        raise ValueError(f"函数字符串语法错误: {str(e)}")
    except Exception as e:
        raise ValueError(f"解析函数失败: {str(e)}")


def _extract_description(docstring: str) -> str:
    """从 docstring 中提取主要描述"""
    if not docstring:
        return "No description provided"

    # 移除多余空白
    lines = [line.strip() for line in docstring.split("\n")]
    lines = [line for line in lines if line]

    if not lines:
        return "No description provided"

    # 返回第一行作为主要描述
    # 如果遇到 Args:, Parameters:, Returns: 等关键字，停止
    description_lines = []
    for line in lines:
        if line.startswith(("Args:", "Parameters:", "Returns:", "Raises:", "Example:")):
            break
        description_lines.append(line)

    return (
        " ".join(description_lines) if description_lines else "No description provided"
    )


def _extract_parameters(func_def: ast.FunctionDef, docstring: str) -> Dict[str, Any]:
    """提取函数参数信息并构建 parameters schema"""

    # 解析 docstring 中的参数描述
    param_docs = _parse_docstring_params(docstring)

    properties = {}
    required = []

    # 遍历函数参数
    args = func_def.args

    # 处理位置参数和关键字参数
    all_args = args.args
    defaults = args.defaults

    # 计算哪些参数有默认值
    num_defaults = len(defaults)
    num_args = len(all_args)
    num_required = num_args - num_defaults

    for i, arg in enumerate(all_args):
        param_name = arg.arg

        # 跳过 self 和 cls
        if param_name in ("self", "cls"):
            continue

        # 提取类型注解
        param_type = _get_python_type_to_json_type(arg.annotation)

        # 从 docstring 获取描述
        param_description = param_docs.get(param_name, f"Parameter {param_name}")

        # 构建属性
        properties[param_name] = {"type": param_type, "description": param_description}

        # 判断是否必需（没有默认值的参数是必需的）
        if i < num_required:
            required.append(param_name)

    # 处理 *args (如果有)
    if args.vararg:
        vararg_name = args.vararg.arg
        properties[vararg_name] = {
            "type": "array",
            "description": param_docs.get(
                vararg_name, f"Variable positional arguments"
            ),
            "items": {"type": "string"},
        }

    # 处理 **kwargs (如果有)
    if args.kwarg:
        kwarg_name = args.kwarg.arg
        properties[kwarg_name] = {
            "type": "object",
            "description": param_docs.get(kwarg_name, f"Variable keyword arguments"),
            "additionalProperties": True,
        }

    return {"type": "object", "properties": properties, "required": required}


def _get_python_type_to_json_type(annotation: Optional[ast.expr]) -> str:
    """将 Python 类型注解转换为 JSON Schema 类型"""
    if annotation is None:
        return "string"  # 默认类型

    # 获取类型名称
    type_name = ""
    if isinstance(annotation, ast.Name):
        type_name = annotation.id
    elif isinstance(annotation, ast.Constant):
        type_name = str(annotation.value)
    elif isinstance(annotation, ast.Subscript):
        # 处理 List[str], Dict[str, int] 等
        if isinstance(annotation.value, ast.Name):
            type_name = annotation.value.id

    # 映射 Python 类型到 JSON Schema 类型
    type_mapping = {
        "str": "string",
        "int": "integer",
        "float": "number",
        "bool": "boolean",
        "list": "array",
        "List": "array",
        "dict": "object",
        "Dict": "object",
        "tuple": "array",
        "Tuple": "array",
        "set": "array",
        "Set": "array",
        "Any": "string",
        "Optional": "string",
    }

    return type_mapping.get(type_name, "string")


def _parse_docstring_params(docstring: str) -> Dict[str, str]:
    """
    从 docstring 中解析参数描述

    支持多种风格：
    - Google style: Args: / Parameters:
    - NumPy style: Parameters ----------
    - Sphinx style: :param name: description
    - Dash style: - name (type): description
    """
    if not docstring:
        return {}

    param_descriptions = {}

    # 查找 Args: 或 Parameters: 部分
    args_match = re.search(
        r"(?:Args?|Parameters?):\s*\n(.*?)(?:\n\s*\n|\n(?:Returns?|Raises?|Example|Note):|$)",
        docstring,
        re.DOTALL | re.IGNORECASE,
    )

    if args_match:
        args_section = args_match.group(1)

        # 🔥 方式1: 匹配 "- param_name (type, optional): description" 格式
        # 示例: - name (str): The name of the historical figure.
        dash_pattern = r"^\s*-\s*(\w+)\s*\([^)]+\)\s*:\s*(.+?)(?=^\s*-\s*\w+\s*\(|$)"
        matches = list(
            re.finditer(dash_pattern, args_section, re.MULTILINE | re.DOTALL)
        )

        if matches:
            # 使用 dash 格式
            for match in matches:
                param_name = match.group(1).strip()
                param_desc = match.group(2).strip()
                # 清理描述（移除多余换行和空格）
                param_desc = " ".join(param_desc.split())
                param_descriptions[param_name] = param_desc
        else:
            # 🔥 方式2: 匹配标准格式 "param_name: description" 或 "param_name (type): description"
            # 示例: location: 位置名称 或 location (str): 位置名称
            param_pattern = r"^\s*(\w+)\s*(?:\([^)]+\))?\s*:\s*(.+?)(?=^\s*\w+\s*(?:\([^)]+\))?\s*:|$)"
            for match in re.finditer(
                param_pattern, args_section, re.MULTILINE | re.DOTALL
            ):
                param_name = match.group(1).strip()
                param_desc = match.group(2).strip()
                # 清理描述（移除多余换行和空格）
                param_desc = " ".join(param_desc.split())
                param_descriptions[param_name] = param_desc

    # Sphinx style: :param name: description
    sphinx_pattern = r":param\s+(\w+)\s*:\s*(.+?)(?=\s*:param|\s*:return|\s*:raises|$)"
    for match in re.finditer(sphinx_pattern, docstring, re.DOTALL):
        param_name = match.group(1).strip()
        param_desc = match.group(2).strip()
        param_desc = " ".join(param_desc.split())
        param_descriptions[param_name] = param_desc

    return param_descriptions


# ==================== 测试和示例 ====================


def test_func2json_schema():
    """测试函数"""

    # 测试用例 1: Dash 风格文档（您的格式）
    func1 = '''
def biographical_info_retriever(name: str, information_type: list, language: str = 'English', data_sources: list = None, time_period: str = None, relevance: str = 'medium'):
    """
    Retrieve comprehensive biographical information about a historical or sports figure.

    Parameters:
    - name (str): The full name of the individual.
    - information_type (list): Types of biographical information requested.
    - language (str): Language for the information. Defaults to English.
    - data_sources (list): Databases to query for information.
    - time_period (str): Time period for filtering historical data.
    - relevance (str): Relevance level of the information.

    Returns:
    - dict: A dictionary containing the requested biographical information.
    """
    # Error handling for required parameters
    if not name or not information_type:
        return {'error': 'Missing required parameters: name and information_type are required.'}

    # Validate information_type
    valid_info_types = ['date_of_birth', 'place_of_birth', 'full_biography', 'achievements', 'career_highlights', 'personal_life']
    if not all(info in valid_info_types for info in information_type):
        return {'error': 'Invalid information_type. Valid types are: ' + ', '.join(valid_info_types)}

    # Validate language
    valid_languages = ['English', 'Spanish', 'French', 'German', 'Chinese']
    if language not in valid_languages:
        return {'error': 'Invalid language. Valid options are: ' + ', '.join(valid_languages)}

    # Simulate data retrieval
    if name == 'Archduchess Margarethe Klementine Of Austria' and 'date_of_birth' in information_type:
        return {'date_of_birth': '6 July 1870'}

    # Simulate additional return values
    return {'message': 'Information retrieved successfully', 'data': {}}
'''

    # 测试用例 2: Google 风格文档
    func2 = '''
def calculate(expression: str, precision: int = 2) -> float:
    """计算数学表达式的结果
    
    Args:
        expression: 要计算的数学表达式字符串
        precision: 结果的小数精度，默认为2位
        
    Returns:
        float: 计算结果
    """
    return eval(expression)
'''

    # 测试用例 3: 标准 Parameters 风格
    func3 = '''
def search(query: str, limit: int = 10, filters: dict = None) -> list:
    """搜索功能
    
    Parameters:
        query: 搜索关键词
        limit: 返回结果数量限制
        filters: 过滤条件字典
    """
    pass
'''

    # 测试用例 4: Sphinx 风格文档
    func4 = '''
def historical_figure_identifier(event_name: str, time_period: str = '', location: str = '', name_variations: bool = True, output_format: str = 'text', figure_type: str = 'other', detail_level: str = 'summary', significance_filter: bool = False, information_source: str = '') -> str:
    """
    Identifies historical figures associated with specific events or constructions.
    """
    # Error handling for required parameter
    if not event_name:
        return 'Error: The event_name parameter is required.'
    
    # Simulated database of historical figures
    historical_figures_db = {
        'Stanley Park': 'Thomas Mawson'
    }
    
    # Logic to identify the historical figure
    figure = historical_figures_db.get(event_name, 'Unknown')
    
    # Constructing the output based on the output_format
    if output_format == 'json':
        return {'event_name': event_name, 'historical_figure': figure}
    else:
        return f'The historical figure associated with {event_name} is {figure}.'

    # Additional error handling for other parameters can be added as needed
    # For example, checking if output_format is valid, etc.
'''

    print("=" * 80)
    print("测试 func2json_schema 函数")
    print("=" * 80)

    for i, func_str in enumerate([func1, func2, func3, func4], 1):
        print(f"\n【测试用例 {i}】")
        print("-" * 40)
        schema = func2json_schema(func_str)
        print(json.dumps(schema, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    test_func2json_schema()
