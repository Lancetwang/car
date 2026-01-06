import json
import matplotlib.pyplot as plt
from collections import Counter

# Set font to Times New Roman for publication
plt.rcParams["font.family"] = "Times New Roman"
plt.rcParams["font.size"] = 16
plt.rcParams["legend.fontsize"] = 14

# Read ToolHopPro.json file
with open("ToolHopPro.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# Count easy and complex tools
easy_count = 0
complex_count = 0
param_counts = []

# Iterate through all data items
for item in data:
    if "tools" in item:
        for tool_name, tool_info in item["tools"].items():
            # Count easy/complex tools
            if tool_info.get("easy", False):
                easy_count += 1
            else:
                complex_count += 1

            # Count parameters
            if "parameters" in tool_info and "properties" in tool_info["parameters"]:
                param_count = len(tool_info["parameters"]["properties"])
                param_counts.append(param_count)

print(f"Logical Tools: {easy_count}")
print(f"External Tools: {complex_count}")
print(f"Total Tools: {easy_count + complex_count}")

# Figure 1: Tool Type Distribution (Pie Chart)
fig1, ax1 = plt.subplots(figsize=(10, 10))

categories = ["Logical Tools", "External Tools"]
counts = [easy_count, complex_count]
colors = ["#4CAF95", "#22FF2D"]

# Create pie chart
wedges, texts, autotexts = ax1.pie(
    counts,
    labels=categories,
    colors=colors,
    autopct="%1.1f%%",
    startangle=90,
    textprops={"fontsize": 20, "fontweight": "bold"},
    wedgeprops={"edgecolor": "black", "linewidth": 1.5},
)

# Set percentage text style
for autotext in autotexts:
    autotext.set_color("black")
    autotext.set_fontsize(22)
    autotext.set_fontweight("bold")

ax1.set_title("Tool Type Distribution", fontsize=24, fontweight="bold", pad=20)

# Add legend with counts
legend_labels = [f"{cat}: {count} tools" for cat, count in zip(categories, counts)]
ax1.legend(
    legend_labels,
    loc="upper right",
    framealpha=0.95,
    edgecolor="black",
    fancybox=True,
    fontsize=18,
)

plt.tight_layout()
plt.savefig("tool_type_distribution.pdf", format="pdf", bbox_inches="tight")
plt.savefig("tool_type_distribution.png", dpi=300, bbox_inches="tight")
print("\nFigure 1 saved as: tool_type_distribution.pdf and tool_type_distribution.png")
plt.close()

# Figure 2: Parameter Count Distribution (Bar Chart)
fig2, ax2 = plt.subplots(figsize=(10, 10))

param_distribution = Counter(param_counts)
param_nums = sorted(param_distribution.keys())
param_freqs = [param_distribution[num] for num in param_nums]

ax2.bar(
    param_nums,
    param_freqs,
    color="#2196F3",
    edgecolor="black",
    linewidth=1.5,
    alpha=0.8,
    width=0.4,
)
ax2.set_xlabel("Number of Parameters", fontsize=22, fontweight="bold")
ax2.set_ylabel("Number of Tools", fontsize=22, fontweight="bold")
ax2.set_title("Tool Parameter Count Distribution", fontsize=24, fontweight="bold")
ax2.grid(axis="y", alpha=0.3, linestyle="--")

# Set x-axis ticks with larger font
ax2.set_xticks(param_nums)
ax2.tick_params(axis="both", which="major", labelsize=18)

# Add statistics info
avg_params = sum(param_counts) / len(param_counts) if param_counts else 0
ax2.text(
    0.98,
    0.98,
    f"Average Parameters: {avg_params:.2f}",
    transform=ax2.transAxes,
    ha="right",
    va="top",
    bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.7, edgecolor="black"),
    fontsize=18,
)

plt.tight_layout()
plt.savefig("parameter_distribution.pdf", format="pdf", bbox_inches="tight")
plt.savefig("parameter_distribution.png", dpi=300, bbox_inches="tight")
print("Figure 2 saved as: parameter_distribution.pdf and parameter_distribution.png")
plt.close()

# Print detailed parameter distribution statistics
print("\nParameter Distribution Details:")
print("-" * 40)
for param_num in param_nums:
    print(f"{param_num} parameters: {param_distribution[param_num]} tools")
