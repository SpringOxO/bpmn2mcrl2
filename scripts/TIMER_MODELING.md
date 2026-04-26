# 定时器建模说明

## 概述

本文档说明了BPMN定时器事件如何被转换为mCRL2的时间模型。

## 改进内容

之前的实现将定时器事件建模为普通的动作，丢失了时间信息。现在的实现利用mCRL2的时间特性，能够准确地表达定时器的时间约束。

## 支持的定时器类型

### 1. 持续时间定时器 (Duration Timer)

**BPMN定义:**
```xml
<bpmn:timerEventDefinition>
  <bpmn:timeDuration>PT5M</bpmn:timeDuration>
</bpmn:timerEventDefinition>
```

**mCRL2建模:**
```mcrl2
(tau @ 300) . timer_action(oid)
```

说明：PT5M表示5分钟，转换为300秒。使用 `tau @ 300` 表示在时间点300时执行。

### 2. 周期性定时器 (Cycle Timer)

**BPMN定义:**
```xml
<bpmn:timerEventDefinition>
  <bpmn:timeCycle>0/5 0/1 * 1/1 * ?</bpmn:timeCycle>
</bpmn:timerEventDefinition>
```

**mCRL2建模:**
```mcrl2
proc
  process(oid: OrderId, t: Real) =
    (tau @ t) . timer_action(oid) .
    ... 其他动作 ... .
    process(oid, t + 300);

init
  process(order_id(1), 0);
```

说明：
- 进程增加时间参数 `t: Real`
- 使用 `(tau @ t)` 表示在时间t时触发
- 递归调用时更新时间：`t + 300`（每5分钟）
- 初始时间为0

### 3. 固定时间点定时器 (Date Timer)

**BPMN定义:**
```xml
<bpmn:timerEventDefinition>
  <bpmn:timeDate>2024-12-31T23:59:59</bpmn:timeDate>
</bpmn:timerEventDefinition>
```

**mCRL2建模:**
目前将固定时间点转换为相对时间，未来可以扩展支持绝对时间。

## 定时器事件位置

### 启动事件 (Start Event)

```mcrl2
proc
  process(oid: OrderId, t: Real) =
    (tau @ t) . start_timer(oid) . next_action(oid);
```

### 边界事件 (Boundary Event)

```mcrl2
proc
  activity_with_timer(oid: OrderId) =
    (normal_flow(oid) +
     (tau @ 300) . boundary_timer(oid) . exception_flow(oid));
```

### 中间捕获事件 (Intermediate Catch Event)

```mcrl2
proc
  process(oid: OrderId) =
    action1(oid) .
    (tau @ 300) . timer_event(oid) .
    action2(oid);
```

## 时间语义

mCRL2的时间模型基于以下概念：

1. **时间域**: 使用 `Real` 类型表示时间
2. **时间约束**: 使用 `@` 操作符指定动作发生的时间
3. **延迟**: `tau @ t` 表示在时间点t时执行内部动作
4. **时间推进**: 通过递归调用更新时间参数

## 示例

### 示例1: loan-granting.bpmn

**BPMN特性:**
- 周期性定时器启动事件（每5分钟）

**生成的mCRL2:**
```mcrl2
proc
  loan_process(oid: OrderId, t: Real) =
    (tau @ t) . start_timer(oid) .
    check_credit_score(oid) .
    (tau . grant_loan(oid) . endevent_1alwvtl(oid) +
     tau . reject_loan_request(oid) . endevent_0zj88y0(oid)) .
    endevent_0q9wl5o(oid) .
    loan_process(oid, t + 300);

init
  loan_process(order_id(1), 0);
```

**说明:**
- 进程每300秒（5分钟）执行一次
- 时间参数t从0开始，每次递归增加300
- `(tau @ t)` 确保在正确的时间点触发

### 示例2: order-handling.bpmn

**BPMN特性:**
- 周期性定时器启动事件
- 条件边界事件

**生成的mCRL2:**
```mcrl2
proc
  order_process(oid: OrderId, t: Real) =
    (tau @ t) . start_order_received(oid) .
    task_1nbdup3_lifecycle(oid, true, false) .
    order_process(oid, t + 300);
```

## Cron表达式解析

系统支持解析简单的cron表达式：

| Cron表达式 | 含义 | 转换结果（秒） |
|-----------|------|--------------|
| `0/5 * * * * ?` | 每5分钟 | 300 |
| `0 0/1 * * * ?` | 每1小时 | 3600 |
| `0 0 0/1 * * ?` | 每1天 | 86400 |

## ISO 8601持续时间解析

系统支持解析ISO 8601持续时间格式：

| ISO 8601 | 含义 | 转换结果（秒） |
|----------|------|--------------|
| `PT5M` | 5分钟 | 300 |
| `PT1H` | 1小时 | 3600 |
| `PT30S` | 30秒 | 30 |
| `P1D` | 1天 | 86400 |
| `PT1H30M` | 1小时30分钟 | 5400 |

## 验证和分析

使用mCRL2工具链可以验证和分析时间属性：

```bash
# 生成状态空间
mcrl22lps --timed model.mcrl2 model.lps

# 模拟执行
lpsxsim model.lps

# 验证时间属性
lps2pbes -f property.mcf model.lps model.pbes
pbes2bool model.pbes
```

## 参考资料

- [mCRL2时间规范](https://www.mcrl2.org/web/user_manual/language_reference/data.html#real-numbers)
- [BPMN 2.0定时器事件](https://www.omg.org/spec/BPMN/2.0/)
- [ISO 8601持续时间格式](https://en.wikipedia.org/wiki/ISO_8601#Durations)
