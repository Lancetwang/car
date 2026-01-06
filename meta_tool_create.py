from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from config import cfg
from prompts import tool_creator_prompt

load_dotenv()

tool_creator = ChatOpenAI(model_name=cfg.llm.support, temperature=cfg.llm.temperature)


def create_tool(require: str, name: str) -> dict:
    """根据用户需求创建一个新的脚本工具来解决问题
    Args:
        require: 用户需要完成的需求
        name: 创建出的工具的名称
    """
    func_code = tool_creator.invoke(
        [
            {"role": "system", "content": tool_creator_prompt},
            {
                "role": "user",
                "content": f"用户需求: {require}\n工具名称: {name}",
            },
        ]
    ).content
    file_name = f"{name}.py"
    try:
        with open(f"{cfg.tool.dir}/{file_name}", "w", encoding="utf-8") as f:
            f.write(func_code)
        print(f"工具脚本 {file_name} 创建成功！")
        return {"success": True, "code": func_code}
    except Exception as e:
        print(f"创建工具脚本 {file_name} 失败: {str(e)}")
        return {"success": False, "error": str(e)}
