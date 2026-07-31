# DisplayAgent

Linux 显示配置 Agent，基于《AI Agent 实战营》架构原则设计。

## 核心架构

基于 `Agent = LLM + 上下文 + 工具` 公式：

```
┌─────────────────────────────────────────────────────────────┐
│                      DisplayAgent                           │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │   上下文层   │  │   工具层     │  │     Harness 层      │ │
│  │             │  │             │  │                      │ │
│  │ System      │  │ xrandr      │  │ Constraint (约束)    │ │
│  │ Prompt      │  │ wpctl       │  │ Verify (验证)        │ │
│  │ 状态栏       │  │ DRM/KMS     │  │ Correct (纠正)       │ │
│  │ 用户记忆     │  │             │  │                      │ │
│  └─────────────┘  └─────────────┘  └──────────────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                      ReAct 循环                            │
│              Thought → Action → Observation                 │
└─────────────────────────────────────────────────────────────┘
```

## 功能特性

- **跨发行版支持**: 自动检测 X11 (xrandr) / Wayland (wpctl)
- **全部显示参数**: 分辨率、刷新率、多屏布局、主屏、缩放、旋转、亮度、色彩
- **Harness 安全机制**: 约束检查、结果验证、错误纠正
- **自然语言对话**: 用户用日常语言描述需求，Agent 自动解析执行

## 目录结构

```
display-agent/
├── display_agent/
│   ├── __init__.py
│   ├── agent.py        # ReAct 循环
│   ├── context.py      # 系统提示词、记忆、状态栏
│   ├── harness.py      # 约束、验证、纠正
│   ├── tools.py        # 显示工具封装
│   └── mock/
│       ├── __init__.py
│       ├── display_server.py  # Mock 显示服务器
│       └── monitor.py         # Mock 显示器
├── eval/
│   ├── __init__.py
│   ├── cases.py        # 14 个评测用例
│   ├── judge.py        # LLM-as-Judge
│   └── eval.py         # 评测运行器
├── tests/
└── README.md
```

## 快速开始

### 安装依赖

```bash
pip install anthropic  # 可选，用于 LLM-as-Judge
```

### 运行评测

```bash
# 使用 Mock Judge（无需 API key）
python -m eval.eval

# 使用 Anthropic Judge
python -m eval.eval --use-judge --judge-model anthropic --api-key YOUR_KEY

# 输出 JSON 结果
python -m eval.eval --output results.json
```

## 评测用例

| ID | 名称 | 类别 | 难度 |
|----|------|------|------|
| single_001 | 设置主屏 | 单屏 | 1 |
| single_002 | 更改分辨率 | 单屏 | 1 |
| single_003 | 调整亮度 | 单屏 | 1 |
| single_004 | 设置缩放 | 单屏 | 1 |
| single_005 | 旋转屏幕 | 单屏 | 1 |
| multi_001 | 切换主屏 | 多屏 | 1 |
| multi_002 | 排列显示器 | 多屏 | 2 |
| multi_003 | 禁用显示器 | 多屏 | 1 |
| multi_004 | 启用显示器 | 多屏 | 1 |
| wayland_001 | Wayland 主屏 | Wayland | 1 |
| safety_001 | 拒绝超范围亮度 | 安全 | 2 |
| safety_002 | 拒绝超范围缩放 | 安全 | 2 |
| edge_001 | 查询显示器列表 | 边界 | 1 |
| edge_002 | 复杂多步任务 | 边界 | 3 |

## 设计原则

参考《AI Agent 实战营》:

1. **保持简单**: 直接 API 调用优于复杂框架
2. **保持透明**: 明确显示执行轨迹和决策
3. **ACI 设计**: 从 Agent 视角设计工具接口

## 扩展测试用例

在 `eval/cases.py` 中添加新的 `TestCase`:

```python
suite.add_case(TestCase(
    id="custom_001",
    name="Custom test case",
    category=CaseCategory.SINGLE_MONITOR,
    description="Description",
    user_message="User's request",
    initial_state_fn=create_single_monitor_setup,
    expected_checks=[check_primary_is_hdmi1],
    difficulty=2,
))
```
