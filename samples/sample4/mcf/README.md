# Sample4 mCF Verification Properties

本目录包含针对 `samples/sample4` 集装箱全流程模型的 12 条 mCF 验证性质。当前这些性质均已使用 `samples/sample4/mcrl2/all.lps` 通过 `lps2pbes` 和 `pbes2bool` 验证，结果均为 `true`。

结论：这 12 条性质满足组长要求的“进入模型检查阶段，对集装箱全流程模型编写 mCF 验证特性是否正常”。相比 `mcf1` 中偏基础的单点性质，这组性质覆盖了端到端可达性、局部顺序约束、并行网关同步、跨参与方消息协作、海关/码头联动、付款闭环和参与方结束一致性，因此无需修改现有公式。

验证命令示例：

```powershell
lps2pbes --formula=samples\sample4\mcf\01_main_happy_path_reachable.mcf samples\sample4\mcrl2\all.lps property.pbes
pbes2bool property.pbes
```

| 编号 | mCF 文件 | 测试类型 | 测试内容 | 主要覆盖点 | 当前结果 |
| --- | --- | --- | --- | --- | --- |
| 1 | `01_main_happy_path_reachable.mcf` | 端到端可达性 | 检查从 Owner 下单开始，经过 FF、SA、Transport、Depot、CT、Customs、离港、费用单、付款，最终 Owner 结束的完整主路径是否存在。 | 全流程 happy path、跨参与方协作、最终闭环 | `true` |
| 2 | `02_all_participants_can_finish.mcf` | 全局可达性 | 检查 Owner、FF、SA、SBGS、Customs Broker、Customs、Container Terminal、Transport、Depot 的结束事件是否都可达。 | 所有参与方无不可达终点 | `true` |
| 3 | `03_no_business_message_before_owner_order.mcf` | 安全性/顺序约束 | 检查 Owner 订单到达 FF 之前，下游 S/O、报关信息、申报、放箱等业务消息不能提前发生。 | 起始订单对下游流程的前置约束 | `true` |
| 4 | `04_ff_parallel_split_and_join_are_ordered.mcf` | 并行网关同步 | 检查 FF 的两个并行分支，即发 S/O 给 SA 和发订单信息给 Customs Broker，必须都完成后才能同步汇合并进入后续网关。 | FF 并行 split/join、`c_sync_join_1`、`gateway_15l9l3p` | `true` |
| 5 | `05_ff_equipment_receipt_requires_manifest_and_sa_receipt.mcf` | 跨参与方消息顺序 | 检查 FF 向 Transport 发送 Equipment Receipt 之前，必须已经收到 SA 的 Manifest 和 Equipment Receipt。 | SA -> FF -> Transport 的消息依赖 | `true` |
| 6 | `06_transport_join_and_owner_ctn_release.mcf` | Transport 业务顺序 | 检查 Transport 向 Owner 放空箱前必须收到 Depot 空箱和 FF receipt；向 Depot 回传 outbound CTN/receipt 前必须已收到 Owner outbound CTN。 | Transport 并行输入、Owner/Depot 交互、箱流转顺序 | `true` |
| 7 | `07_depot_handover_to_ct_requires_transport_package.mcf` | Depot 业务顺序/响应性 | 检查 Depot 不能在收到 Transport 的 outbound CTN/receipt 前向 CT 发送 outbound CTN；收到后存在继续发送给 CT 并结束 Depot 的路径。 | Transport -> Depot -> CT 链路 | `true` |
| 8 | `08_ct_parallel_join_and_load_guard.mcf` | CT 并行网关同步 | 检查 CT 装箱前，Manifest、船到港消息、Depot outbound CTN 三路输入必须都到达，并完成 CT 的同步汇合网关。 | Container Terminal 三路并行输入、`c_sync_join_3`、`gateway_10irkpy`、`load_ctn` | `true` |
| 9 | `09_customs_parallel_join_and_inspection_guard.mcf` | Customs 并行网关同步 | 检查 Customs 执行 CIQ/inspection 前，必须已经收到 Manifest、CT 到港消息、报关申报、Inspection Appointment。 | Customs 四类前置输入、`c_sync_join_2`、`gateway_127z0iq` | `true` |
| 10 | `10_customs_clearance_broadcast_requires_ciq_inspection.mcf` | 海关放行顺序/响应性 | 检查海关放行广播必须发生在 CIQ 和 inspection 之后，且先向 Customs Broker 放行，再向 CT 放行，最终 Customs 可结束。 | CIQ、inspection、Customs clearance 广播顺序 | `true` |
| 11 | `11_departure_expense_payment_chain.mcf` | 业务闭环顺序/响应性 | 检查船离港通知必须在装箱和 CT 收到海关放行之后；费用单必须在离港后；付款必须在费用单后；之后 Owner 可结束。 | CT 放行、departure、expense note、payment 闭环 | `true` |
| 12 | `12_no_participant_finishes_before_required_milestones.mcf` | 结束一致性 | 检查各参与方不能早于自身关键业务里程碑结束，例如 Owner 不能早于付款结束，CT 不能早于离港结束，Depot 不能早于发送 outbound CTN 给 CT 结束。 | 各参与方终止状态与关键动作一致 | `true` |

