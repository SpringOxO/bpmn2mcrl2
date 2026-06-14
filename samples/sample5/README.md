# Sample5: 数据驱动的 BPMN 场景与 μ-calculus 安全不变式验证

本目录包含 5 个从真实货运物流 BPMN 中抽取的数据驱动决策场景，演示如何通过 mCRL2 的 μ-calculus (mCF) 验证**数据绑定的安全不变式 (Data-bound Safety Invariants)**。

## 设计动机

传统 BPMN 验证往往只关注控制流（死锁、活锁、可达性），忽略了数据对流程分支的驱动作用。mCRL2 的数据参数化进程和 μ-calculus 的全称量化能力，使得我们可以证明：

> **无论经过何种交叉执行路径，特定带参动作只在合法数据条件下发生。**

## 关键技术：mcrl2:payload 注解

在 BPMN 消息流的 `<bpmn:documentation>` 中添加：

```xml
<bpmn:documentation>mcrl2:payload VarName1, VarName2</bpmn:documentation>
```

转换器会将数据变量作为动作参数输出：

```mcrl2
c_payment_settled_notice : OrderId # Int # Int;   % carries Amount_Due, Amount_Paid
```

这使得 μ-calculus 公式可以直接对动作携带的数据做全称量化。

## 验证方法

使用 `pbes2bool -s2` 策略（关键！`forall` 在无限 `Int` 域上需要 `-s2` 才能高效求解）：

```bash
mcrl22lps model.mcrl2 model.lps
lps2pbes -f safety.mcf model.lps safety.pbes
pbes2bool -s2 safety.pbes
```

## 5 个场景总览

| # | 场景 | 数据变量 | 核心特征 | 安全不变式 |
|---|---|---|---|---|
| 1 | Customs Inspection | `CargoType: Int` | Boolean 枚举守卫 | 放行 → 类型合规；扣留 → 类型不符 |
| 2 | Depot Inventory | `Container_Count: Int` | 算术更新 + 循环补货 | 发箱 → 计数非负 |
| 3 | Declaration Review | `status: Int` | 二元状态 + 循环重提交 | 状态消息 → 值在 {0,1} 内 |
| 4 | Weight Check | `weight: Int` | 阈值比较 + 双分支 | 拒绝通知 → weight > 5 |
| 5 | Payment Reconciliation | `Amount_Due, Amount_Paid, Current_Payment` | 多变量算术 + 累加循环 | 结清 → paid >= due；催缴 → paid < due |

### 场景 1：海关货物查验

```
BPMN: scenario1/bpmn/customs.bpmn
MCF:  scenario1/mcf/customs_safety_invariants.mcf
```

Environment 提交货物类型 `CargoType`，Customs 查验后走异或网关：
- 合规（`CargoType ∈ {1,2,3}`）→ 放行通知
- 不合规 → 扣留通知

**安全不变式**：
```mcrl2
[true*] forall ct: Int .
  [c_pass_notice(order_id(1), ct)] val(ct == 1 || ct == 2 || ct == 3)
```

### 场景 2：堆场库存检查

```
BPMN: scenario2/bpmn/depot_inventory_check.bpmn
MCF:  scenario2/mcf/inventory_safety_invariants.mcf
```

Depot 收到询问后检查 `Container_Count`：
- `count > 0` → 发送空箱 (count - 1)
- `count == 0` → 通知缺货 → 定时等待补货 (count + 1) → 回到检查

**安全不变式**：
```mcrl2
[true*] forall cnt: Int .
  [c_send_empty_ctn_...(order_id(1), cnt)] val(cnt >= 0)
```

### 场景 3：报关单据审核

```
BPMN: scenario3/bpmn/scenario3-customs-declaration.bpmn
MCF:  scenario3/mcf/declaration_safety_invariants.mcf
```

Customs Broker 提交申报，Environment 返回 `status`：
- `status == 1` → 申报接受，流程结束
- `status == 0` → 补充材料 → 重新申报（循环）

**安全不变式**：
```mcrl2
[true*] forall st: Int .
  [c_document_status(order_id(1), st)] val(st == 0 || st == 1)
```

### 场景 4：集装箱码头重量检查

```
BPMN: scenario4/bpmn/container-terminal-weight-check.bpmn
MCF:  scenario4/mcf/weight_safety_invariants.mcf
```

Container Terminal 接收重量数据 `weight`：
- `weight <= 5` → 装载
- `weight > 5` → 发送拒绝装载警告

**安全不变式**：
```mcrl2
[true*] forall w: Int .
  [c_reject_loading_warning_to_environment(order_id(1), w)] val(w > 5)
```

### 场景 5：货主支付费用资金核对

```
BPMN: scenario5/bpmn/owner_payment_reconciliation.bpmn
MCF:  scenario5/mcf/payment_safety_invariants.mcf
```

Owner 收到 `Amount_Due=3, Amount_Paid=0, Current_Payment=1`，支付后走异或网关：
- `Amount_Paid >= Amount_Due` → 发送结清通知 → 结束
- `Amount_Paid < Amount_Due` → 发送催缴余额 → 等待补充付款 → 重新支付（累加循环）

**安全不变式**：
```mcrl2
[true*] forall due: Int . forall paid: Int .
  [c_payment_settled_notice(order_id(1), due, paid)] val(paid >= due)
&&
[true*] forall due: Int . forall paid: Int .
  [c_balance_reminder(order_id(1), due, paid)] val(paid < due)
```

## 验证脚本

有完整验证脚本的场景：

| 场景 | 脚本 |
|---|---|
| 2 | `scenario2/verify.ps1` |
| 5 | `scenario5/verify.ps1` |

其他场景可直接用命令行验证（见各场景目录下的 mcf 文件）。

## 目录结构

```
sample5/
├── README.md
├── scenario1/  (Customs Inspection)
│   ├── bpmn/customs.bpmn
│   ├── mcf/customs_safety_invariants.mcf
│   └── mcrl2/
├── scenario2/  (Depot Inventory)
│   ├── bpmn/depot_inventory_check.bpmn
│   ├── mcf/inventory_safety_invariants.mcf
│   ├── mcf/inventory_branches_reachable.mcf
│   └── verify.ps1
├── scenario3/  (Declaration Review)
│   ├── bpmn/scenario3-customs-declaration.bpmn
│   ├── mcf/declaration_safety_invariants.mcf
│   └── mcrl2/
├── scenario4/  (Weight Check)
│   ├── bpmn/container-terminal-weight-check.bpmn
│   ├── mcf/weight_safety_invariants.mcf
│   ├── mcf/project4_load_reachable.mcf
│   ├── mcf/project4_reject_reachable.mcf
│   └── mcrl2/
└── scenario5/  (Payment Reconciliation)
    ├── bpmn/owner_payment_reconciliation.bpmn
    ├── mcf/payment_safety_invariants.mcf
    ├── mcf/payment_reconciliation_reachable.mcf
    ├── verify.ps1
    └── mcrl2/
```

## 技术要点

1. **`pbes2bool -s2` 是必须的**：`forall x: Int` 在无限整数域上量化，默认策略无法高效求解，`-s2` 策略通过 refutation-based 剪枝处理
2. **可达性检查不需要数据量化**：可达性用无 payload 版本的 mCRL2 验证更快
3. **安全不变式和可达性是互补的**：`[true*] forall x. [a(x)] val(P(x))` 可能空真（a 不可达时自动成立），需配合 `<true* . a> true` 确保分支可达
