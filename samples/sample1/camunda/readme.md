# 消息一致性建模 - Camunda BPMN 模型说明

## 模型基本信息

- 文件名：`message_consistency.bpmn`
- 建模工具：Camunda Modeler 5.44+
- 适用场景：跨组织物流协作消息交互、消息同步一致性验证

## 参与方命名规范（严格遵循课程要求）

| 中文名 | 英文名 | 缩写 | 模型中名称 |
|--------|--------|------|------------|
| 货代 | Freight Forwarder | FFW | Freight Forwarder (FFW) |
| 船代 | Shipping Agency | SAG | Shipping Agency (SAG) |

## 模型功能

1. 货代（FFW）发起业务请求
2. 船代（SAG）并行返回 **舱单(Manifest)** 与 **设备交接单(EIR)**
3. 货代通过并行网关等待两条消息全部到达，实现**消息一致性同步**
4. 支持测试：消息时序无关性、并行网关隐藏、消息完整性验证

## BPMN 核心元素

- 参与方池（Participant）：FFW、SAG
- 消息流（messageFlow）：跨组织消息传递
- 并行网关（parallelGateway）：并行发送/消息汇聚
- 接收任务/发送任务：消息收发行为

## BPMN → mCRL2 映射规则

| BPMN 元素        | mCRL2 对应         |
|------------------|--------------------|
| messageFlow      | comm 通信算子      |
| parallelGateway  | \|\| 并行算子      |
| sequenceFlow     | . 顺序算子         |
| 任务节点         | act 动作声明       |

## 验证点（作业可直接使用）

- 消息必须成对到达，缺一不可
- 消息到达顺序不影响流程正确性
- 无死锁、无消息丢失
- 可用于并行网关隐藏场景验证
