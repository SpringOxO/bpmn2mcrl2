# Sample 3: 报关单据审核与打回重交

## 场景概述

**参与方**: Customs Broker（报关行）vs Environment（海关系统）

**当前缺陷**: 报关行向海关申报后，直接等待成功消息，缺乏材料被打回的迭代过程。

**业务逻辑**: 报关行提交报关单据，Environment（海关系统）审核后返回 `Document_Status`（枚举值: Valid 或 Invalid）。有效则流程完成，无效则补充材料后重新提交（循环）。

**mCRL2 视角优势**: 展示 mCRL2 处理枚举数据类型（自定义 Sort）以及无穷循环（递归进程调用）的能力。对于验证系统是否存在活锁（Livelock，例如无限次提交都被驳回）具有极高的演示价值。

## BPMN 流程

```
开始 → 向海关申报 → 接收 Document_Status → 异或网关
  ├─ status == Valid   → 申报通过 → 结束
  └─ status == Invalid → 补充申报材料 → 循环回到"向海关申报"
```

### 关键 BPMN 元素

| 元素 | ID | 说明 |
|------|-----|------|
| 参与方 | `Participant_CB` | Customs Broker，流程 `Process_CB` |
| 参与方 | `Participant_044r31t` | Environment，空流程（仅 startEvent） |
| 消息流 | `Flow_declaration_send` | Declaration: CB → Env |
| 消息流 | `Flow_doc_status_return` | Document_Status: Env → CB |
| 消息流 | `Flow_supplement_send` | Supplement: CB → Env |
| 排他网关 | `Gateway_doc_check` | 条件 `${status == Valid}` / `${status == Invalid}` |
| 循环边 | `Flow_supplement_to_declare` | 补充材料 → 回到申报 |

## 目录结构

```
sample3/
  bpmn/
    scenario1-customs-declaration.bpmn    # BPMN 源文件 (Camunda Modeler 可打开)
  mcrl2/
    scenario1_baseline.mcrl2              # 转换器自动生成的基线版本
    scenario1-customs-declaration.mcrl2   # 手工增强版本 (含自定义 Sort + 递归)
    scenario1.lps / scenario1.lts         # 生成的 LPS/LTS (验证产物)
  README.md
```

## 生成基线 mCRL2

```bash
cd /path/to/bpmn2mcrl2
python scripts/bpmn2mcrl2.py sample3/bpmn/scenario1-customs-declaration.bpmn sample3/mcrl2/scenario1_baseline.mcrl2
```

## 验证增强版 mCRL2

```bash
# 语法检查
mcrl22lps sample3/mcrl2/scenario1-customs-declaration.mcrl2 sample3/mcrl2/scenario1.lps

# 生成 LTS
lps2lts sample3/mcrl2/scenario1.lps sample3/mcrl2/scenario1.lts

# 查看状态空间
ltsinfo sample3/mcrl2/scenario1.lts
```

## 基线 vs 增强版对比

| 维度 | 基线（转换器输出） | 增强版（手工编写） |
|------|-------------------|-------------------|
| `status` 类型 | `Int`（范围 0-10） | `DocStatus = struct Valid \| Invalid` |
| `Valid`/`Invalid` | 独立 Int 变量，各自 0-10 | 互斥枚举值 |
| 进程参数 | 所有进程带 3 个 Int 参数 | 仅 `oid: OrderId` |
| Environment 进程 | `delta` 但带无用 Int 参数 | 有实际行为：发送 DocStatus |
| 消息携带数据 | 无 | `r_document_status(oid, status)` 携带 DocStatus |
| 守卫条件 | `(status == Valid)` 但 status 是 Int | 类型安全的 `(status == Valid)` |
| 活锁检测 | 不支持（无递归） | 递归进程，Environment 可无限返回 Invalid |

### 基线 mCRL2 核心代码

```
process_cb(oid: OrderId, Invalid: Int, Valid: Int, status: Int) =
  proc_activity_declare(oid, Invalid, Valid, status);

proc_activity_declare(oid, Invalid, Valid, status) =
  s_declaration(oid) . r_document_status(oid) .
  ((status == Valid) -> tau + (status == Invalid) -> tau .
    s_supplement(oid) . proc_activity_declare(oid, Invalid, Valid, status))
  . declaration_accepted(oid) . process_completed(oid);

init
  (sum Invalid, Valid, status: Int .
    ((Invalid>=0&&Invalid<=10) && (Valid>=0&&Valid<=10) && (status>=0&&status<=10))
    -> process_cb(order_id(1), Invalid, Valid, status))
```

**问题**: `Valid`/`Invalid` 被推导为 Int 并作为参数污染所有进程。语义上 status 可以取 0-10 中任意值，而非严格二选一。

### 增强版 mCRL2 核心代码

```mcrl2
sort DocStatus = struct Valid | Invalid;

act
  s_document_status, r_document_status, c_document_status : OrderId # DocStatus;
  ...

proc
  process_cb(oid: OrderId) =
    declare_to_customs(oid) . s_declaration(oid) .
    (sum status: DocStatus . r_document_status(oid, status) .
    (
      (status == Valid) -> tau .
        declaration_accepted(oid) . process_completed(oid) . delta
      +
      (status == Invalid) -> tau .
        supplement_documents(oid) . s_supplement(oid) .
        process_cb(oid)
    ));

  env(oid: OrderId) =
    r_declaration(oid) .
    (s_document_status(oid, Valid) . delta + s_document_status(oid, Invalid) . delta)
    +
    r_supplement(oid) .
    (s_document_status(oid, Valid) . delta + s_document_status(oid, Invalid) . delta);
```

## 活锁（Livelock）验证

Environment 通过 `+` 非确定性选择返回 `Valid` 或 `Invalid`。当 Environment 持续选择 `Invalid` 时，Customs Broker 会无限循环在"申报 → 驳回 → 补充 → 申报 → ..."中。

mCRL2 mu-calculus 验证：

```
% 属性: 从任意状态出发，是否总能最终到达 declaration_accepted？
[true*]<true*.declaration_accepted>true

% 该属性为 false——存在 Environment 永远返回 Invalid 的无限路径（活锁）
```

## 验证结果

| 指标 | 值 |
|------|-----|
| 状态数 | 8 |
| 迁移数 | 7 |
| 动作标签 | 6（含 tau） |
| LTS 确定性 | 是 |

## 工具链

```
BPMN XML (Camunda Modeler 5.44.0)
  ├─→ bpmn2mcrl2.py ──→ 基线 .mcrl2
  └─→ 手工编写 ──────→ 增强版 .mcrl2
                            └─→ mcrl22lps ──→ .lps ──→ lps2lts ──→ .lts ──→ ltsinfo
```
