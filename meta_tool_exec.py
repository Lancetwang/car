import importlib.util
import sys
import traceback
from pathlib import Path
import uuid
import io


def execute_tool(file_path: str, func_name: str, args: dict):
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    module_name = f"dynamic_module_{uuid.uuid4().hex}"

    # 捕获标准输出
    old_stdout = sys.stdout
    sys.stdout = captured_output = io.StringIO()

    try:
        spec = importlib.util.spec_from_file_location(module_name, str(file_path))
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        if not hasattr(module, func_name):
            raise AttributeError(f"模块中未找到函数: {func_name}")
        func = getattr(module, func_name)

        result = func(**args)

        # 恢复标准输出
        sys.stdout = old_stdout
        printed_content = captured_output.getvalue().strip()

        # 判断函数返回值是否为错误
        is_error_result = False
        if isinstance(result, dict) and "error" in result:
            is_error_result = True
        elif isinstance(result, str) and (
            "error" in result.lower()
            or "exception" in result.lower()
            or "failed" in result.lower()
        ):
            is_error_result = True

        # 如果有 print 内容，优先使用 print 内容
        if printed_content:
            # 如果函数返回值是错误，只返回 print 内容
            if is_error_result:
                return printed_content
            # 如果函数返回值有效，综合两者
            elif result is not None:
                return f"{printed_content}\n{result}"
            else:
                return printed_content
        else:
            return result

    except Exception as e:
        # 恢复标准输出
        sys.stdout = old_stdout
        printed_content = captured_output.getvalue().strip()

        # 如果有 print 内容，即使报错也返回 print 的内容
        if printed_content:
            return printed_content

        # 返回完整的错误堆栈信息
        traceback_str = traceback.format_exc()
        return traceback_str

    finally:
        sys.modules.pop(module_name, None)
