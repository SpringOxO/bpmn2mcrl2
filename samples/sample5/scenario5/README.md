# Sample5 Scenario5：货主支付费用的资金核对

本场景针对 `Owner` 与 `Environment` 之间的付款核对流程建模。

## 当前缺陷

原流程中的货主支付任务 `Activity_1p1hn9r` 是一个单一动作，默认执行一次支付后即可结清费用。

这个建模过于简化，无法表达实际业务中常见的“已付金额不足，应继续催缴余额并再次付款”的情况。

## BPMN 修改方案

本场景将 `Activity_1p1hn9r` 改造成带数据状态的支付循环：

- `Environment` 先返回金额信息，包括 `Amount_Due`、`Amount_Paid` 和 `Current_Payment`。
- `Owner` 执行 `Activity_1p1hn9r`，将本次付款额累加到已付金额：
  `Amount_Paid = Amount_Paid + Current_Payment`
- 支付后进入异或网关 `Gateway_PaymentEnough`。
- 分支 A：当 `Amount_Paid >= Amount_Due` 时，发送结清通知并结束流程。
- 分支 B：当 `Amount_Paid < Amount_Due` 时，执行“催缴余额”任务，等待 `Environment` 再次发起补充付款，然后回到 `Activity_1p1hn9r`。

## mCRL2 检验重点

转换后的 mCRL2 模型会把金额变量建模为进程参数：

- `Amount_Due: Int`
- `Amount_Paid: Int`
- `Current_Payment: Int`

核心更新逻辑会体现在生成模型中：

```text
pay_freight_charges(oid) .
cont_activity_1p1hn9r(oid, Amount_Due, Amount_Paid + Current_Payment, Current_Payment)
```

异或网关条件会被转换为 mCRL2 守卫：

```text
(Amount_Paid >= Amount_Due)
(Amount_Paid < Amount_Due)
```

本场景的 mCF 属性文件会检查：

- 催缴余额分支可达。
- 支付结清状态可达。
- 结清通知通信可达。

## 文件结构

```text
samples/sample5/scenario5/
  bpmn/owner_payment_reconciliation.bpmn
  mcf/payment_reconciliation_reachable.mcf
  mcrl2/
  verify.ps1
  README.md
```

## 运行验证

在仓库根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File samples\sample5\scenario5\verify.ps1
```

验证脚本会依次完成：

- 将 BPMN 转换为 mCRL2。
- 检查生成模型中是否包含金额变量、比较条件和付款累加更新。
- 使用 `mcrl22lps` 生成 LPS。
- 使用 `lps2lts` 生成 LTS。
- 使用 `lps2pbes` 和 `pbes2bool` 检查 mCF 属性。

生成文件位于：

```text
samples/sample5/scenario5/mcrl2/
```

验证通过时会输出：

```text
mCF result: true
Payment reconciliation verification completed.
```
