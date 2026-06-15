# CAR: Empowering Agents with Dynamic Tool Synthesis and Global Trajectory Rectification

This repository contains the code and data for **CAR (Create And Replan)**, accepted to **Findings of ACL 2026**.

CAR is an agent framework designed for open-ended tool-use environments where the initial toolset may be incomplete or unreliable. Instead of assuming a fixed action space, CAR enables an agent to synthesize missing tools at runtime and revise its global plan when execution failures reveal a flawed trajectory.

> **Paper:** *CAR: Empowering Agents with Dynamic Tool Synthesis and Global Trajectory Rectification*  
> **Venue:** Findings of ACL 2026  
> **Code:** <https://github.com/Lancetwang/car>

## Overview

Existing tool-using agents such as ReAct and Plan-and-Solve often operate under a closed-world assumption: all tools must be available before inference starts. When required tools are missing, obsolete, or unstable, these agents may fall back to inefficient tool-call loops, blind retries, or direct-answer hallucination.

CAR addresses this with two mechanisms:

- **Dynamic Action Space Expansion:** when the current toolset is insufficient, CAR invokes a meta-tool to synthesize a new executable Python tool and adds it to the tool pool for subsequent steps.
- **Global Trajectory Rectification:** when local retries fail, CAR diagnoses the failure, preserves successful history, and replans the remaining trajectory instead of repeatedly retrying the same failing step.

The repository also includes **ToolHop-Pro**, a diagnostic benchmark derived from ToolHop to evaluate agents under tool scarcity and execution instability.

## Repository Structure

```text
.
├── car_agent.py              # CAR agent implementation
├── meta_tool_create.py       # Meta-tool for dynamic tool synthesis
├── meta_tool_exec.py         # Runtime execution of generated tools
├── func2schema.py            # Python function -> tool schema conversion
├── schema.py                 # Pydantic schemas for planning and state tracking
├── config.py                 # YAML configuration loader
├── config.yaml               # Model/tool/runtime configuration
├── test_arc_mode.py          # ToolHop-Pro evaluation script
├── ToolHopPro.json           # ToolHop-Pro benchmark data
├── tool_set/                 # Runtime tool pool
├── utils/                    # Dataset/statistics utilities
├── stats/                    # Dataset analysis figures
└── results/                  # Experiment outputs and comparison logs
```

## Installation

This project uses `uv` and requires Python 3.13 or later.

```bash
git clone https://github.com/Lancetwang/car.git
cd car
uv sync
```

The agent uses OpenAI-compatible chat model clients through `langchain-openai`. Configure your model provider credentials in an `.env` file, for example:

```bash
OPENAI_API_KEY=your_api_key
OPENAI_BASE_URL=your_openai_compatible_endpoint
```

Then edit `config.yaml` to set the main and support models:

```yaml
llm:
  main: "qwen-plus-2025-07-28"
  support: "qwen-flash-2025-07-28"
  temperature: 0.0
```

## Reproduction Notes

The implementation imports prompt templates from `prompts.py`. If you are running from a clean public checkout where prompt files are omitted, recreate the prompt template file according to the prompt templates in the paper appendix before running the agent.

Generated tools are written into `tool_set/` at runtime. API keys and local environment files should remain untracked.

## Running CAR Interactively

```bash
uv run car_agent.py
```

This starts an interactive loop where CAR classifies the query, plans a trajectory, executes available tools, creates missing tools when needed, and replans after unrecoverable failures.

## Running ToolHop-Pro Experiments

Evaluate CAR on ToolHop-Pro with the complete tool setting:

```bash
uv run test_arc_mode.py --type complete
```

Evaluate under the missing-tool setting:

```bash
uv run test_arc_mode.py --type missing
```

Run a specific question:

```bash
uv run test_arc_mode.py --type missing --id 0
```

Run multiple selected questions:

```bash
uv run test_arc_mode.py --type missing --id 0 1 2 3
```

Suppress verbose agent logs:

```bash
uv run test_arc_mode.py --type missing --id 0 --no-verbose
```

## ToolHop-Pro

ToolHop-Pro is constructed to stress-test robustness beyond standard static tool-use evaluation. It includes three settings:

- **Complete:** all tools are available.
- **Missing:** logical tools are pruned, requiring the agent to synthesize missing capabilities.
- **Error:** tools are available but subject to execution instability.

The benchmark is provided in `ToolHopPro.json`. Utility scripts for analyzing tool distributions and parameter complexity are available under `utils/`.

## Main Results

In the paper, CAR improves Qwen3-Plus on the original ToolHop benchmark from **47.94%** to **54.57%** pass rate.

On ToolHop-Pro, CAR achieves:

| Backbone | Complete | Missing | Error |
| --- | ---: | ---: | ---: |
| Qwen3-Plus + CAR | 54.57 | 53.87 | 52.86 |

These results support the central claim that dynamic tool synthesis and global replanning improve robustness under missing tools and unstable execution environments.

## Acknowledgements

This repository accompanies the ACL 2026 Findings paper. Please refer to the paper for full experimental details, limitations, and safety discussion.
