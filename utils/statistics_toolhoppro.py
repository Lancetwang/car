import json

# Read ToolHopPro.json file
with open("ToolHopPro.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# Statistics variables
num_questions = len(data)
all_tools = set()
tool_param_counts = []
tools_per_question = []

# Iterate through all data items
for item in data:
    if "tools" in item:
        # Count tools per question
        num_tools_in_question = len(item["tools"])
        tools_per_question.append(num_tools_in_question)

        for tool_name, tool_info in item["tools"].items():
            # Collect unique tool names
            all_tools.add(tool_name)

            # Count parameters for each tool
            if "parameters" in tool_info and "properties" in tool_info["parameters"]:
                param_count = len(tool_info["parameters"]["properties"])
                tool_param_counts.append(param_count)

# Calculate statistics
total_unique_tools = len(all_tools)
min_params = min(tool_param_counts) if tool_param_counts else 0
max_params = max(tool_param_counts) if tool_param_counts else 0
avg_tools_per_question = (
    sum(tools_per_question) / len(tools_per_question) if tools_per_question else 0
)

# Print results
print("=" * 60)
print("ToolHopPro Dataset Statistics")
print("=" * 60)
print(f"\nNumber of questions: {num_questions}")
print(f"Total unique tools: {total_unique_tools}")
print(f"Tool parameter count range: {min_params} - {max_params}")
print(f"Average tools per question: {avg_tools_per_question:.2f}")
print(f"\nTotal tool instances (with repetitions): {len(tool_param_counts)}")
print(
    f"Min tools in a question: {min(tools_per_question) if tools_per_question else 0}"
)
print(
    f"Max tools in a question: {max(tools_per_question) if tools_per_question else 0}"
)
print("=" * 60)
