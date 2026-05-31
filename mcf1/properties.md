# 集装箱流程 mCRL2 模型验证性质列表

本文档整理了针对集装箱流程 BPMN 转换出的 mCRL2 模型，所提取的 10 个关键业务性质。这些性质使用 μ-calculus 语法编写，涵盖了可达性、安全性及时序约束、以及必然性。

## 一、 可达性性质 (Reachability)

此类性质主要验证：**在流程的某些分支中，是否有可能成功执行关键操作**。

### P1: 流程正常完结的可达性
* **含义**: 整个集装箱业务流程是有可能顺利流转，并最终到达货主（Owner）正常结束节点（完成支付并终止）的。这用于验证模型存在成功的完整执行路径。
* **公式**: `<true* . event_0470qt9(order_id(1))> true`
* **对应文件**: `p1.mcf`

### P5: 码头装船的可达性
* **含义**: 验证集装箱能够被集装箱码头（CT）成功装载到船上，即 `load_ctn` 动作在模型中是可达的，不会被死锁或无尽的等待完全阻塞。
* **公式**: `<true* . load_ctn(order_id(1))> true`
* **对应文件**: `p5.mcf`

### P8: 边检人员信息登记的可达性
* **含义**: 边检站（SBGS）在收到船代的船员名单后，能够成功完成人员信息登记（`personnel_information_registration`）。
* **公式**: `<true* . personnel_information_registration(order_id(1))> true`
* **对应文件**: `p8.mcf`

## 二、 安全性与时序约束 (Safety / Precedence)

此类性质主要验证：**在现实业务中，“必须先做A，才能做B”的严格时序约束是否在协同模型中得到满足**。如果被违反，说明流程设计可能发生违规跳步。

### P2: 货主启动的前置条件
* **含义**: 在没有填写委托书（`fill_out_certificate_of_entrustment`）之前，货主不能执行后续的订单处理操作。验证起点的严格顺序。
* **公式**: `[!fill_out_certificate_of_entrustment(order_id(1))* . handle_order_include_customs_order(order_id(1))] false`
* **对应文件**: `p2.mcf`

### P3: 海关内部的处理时序
* **含义**: 在海关内部流程中，货物必须先经过检验检疫（`ciq`），才能进行海关查验（`inspection`）。验证单一参与方内部的工序约束。
* **公式**: `[!ciq(order_id(1))* . inspection(order_id(1))] false`
* **对应文件**: `p3.mcf`

### P4: 费用支付的前置条件
* **含义**: 货主必须在接收到船代（SA）发出的费用单（跨参与方消息流 `c_flow_0ot4jwi`）之后，才能进行最终的费用支付（`payment`）。
* **公式**: `[!c_flow_0ot4jwi(order_id(1))* . payment(order_id(1))] false`
* **对应文件**: `p4.mcf`

### P6: 跨参与方的核心风控规则 (先放行后装船)
* **含义**: 实际业务中极其重要的一条红线：没有经过海关处理（`ciq` 作为代表步骤），码头绝对不允许装载集装箱（`load_ctn`）。这是跨系统的强约束验证。
* **公式**: `[!ciq(order_id(1))* . load_ctn(order_id(1))] false`
* **对应文件**: `p6.mcf`

### P7: 货代工作完成的依赖约束
* **含义**: 货代（FF）的流程不能在它收到货主下达的订单（消息流 `c_flow_04xili0`）之前就直接走向完结（`event_1vcgyyd`）。
* **公式**: `[!c_flow_04xili0(order_id(1))* . event_1vcgyyd(order_id(1))] false`
* **对应文件**: `p7.mcf`

### P10: 船舶离港/流程结束的时序约束
* **含义**: 集装箱码头（CT）必须先完成集装箱装载（`load_ctn`），然后才能宣告任务完成（并发出船舶离港通知，随后进入结束节点 `event_0eqptfn`）。
* **公式**: `[!load_ctn(order_id(1))* . event_0eqptfn(order_id(1))] false`
* **对应文件**: `p10.mcf`

## 三、 必然性/活性性质 (Liveness)

此类性质主要验证：**如果系统正常流转且没有死锁，执行了A之后，最终是否不可避免地一定会执行B**。

### P9: 支付完成的必然性
* **含义**: 只要货主填写了委托书（启动了整个业务协作模型），在其对应的每一条有效执行路径上，最终必定会引导到完成最终支付（`payment`）。这个性质很强，能够检查系统各个协同环节是否都完备且没有会卡死流程的逻辑漏洞。
* **公式**: `[true* . fill_out_certificate_of_entrustment(order_id(1))] mu X . ([!payment(order_id(1))]X && <true>true)`
* **对应文件**: `p9.mcf`
