# bpmn2mcrl2 - camunda模型转mcrl2工具

## 结构说明

**docs**：开发和使用文档、issues

**samples**：示例项目

每个sample下：
- **camunda**：源camunda项目
- **mcrl2**：转换出的mcrl2项目

**scripts**：工具本体

## 计划开发周期

2026/04/07 - 2026/04/20

## 当前能力

| **特性分类** | **BPMN 元素 (XML 标签)** | **mCRL2 映射逻辑** | **支持状态** |
| --- | --- | --- | --- |
| **基础流** | `bpmn:sequenceFlow` | 顺序操作符 `.` | 已完成 |
| **原子动作** | `bpmn:serviceTask` | `act` 声明 + 动作名 | 已完成 |
| **排他网关** | `bpmn:exclusiveGateway` | 选择操作符 `+` (配合 `tau`) | 开发中 |
| **并行网关** | `bpmn:parallelGateway` | 进程拆分 | 已完成 |
| **跨组织同步** | `bpmn:messageFlow` | `comm` 规则 + `allow` 过滤 | 已完成 |
| **终止符号** | `bpmn:endEvent` | `delta` (或进程结束) | 已完成 |

## 使用方法

修改脚本中的bpmn输入路径和mcrl2输出路径直接运行