# Sample5 Scenario2: Depot Inventory Check

本场景从 `samples/sample4/bpmn/all.bpmn` 中抽取 Depot 相关流程，并增量加入空箱库存校验。

核心变化：

- 保留 Depot 原流程中的 `SA ask received`、`send Empty CTN to Transport`、`send CTN arrival info to SA`、`Outbound and receipt recieved`、`send Outbound CTN to Container Terminal`。
- 将外部 Shipping Agency、Transport、Container Terminal 简化为一个 `Environment` 泳池。
- 在发送空箱前加入 `check container inventory` 和异或网关。
- `Container_Count > 0` 时发送空箱，并通过 `mcrl2:update Container_Count = Container_Count - 1` 更新库存。
- `Container_Count == 0` 时发送缺货等待消息，等待定时器补货后通过 `mcrl2:update Container_Count = Container_Count + 1` 回到库存判断。

## 本次提交内容

Add:

- 新增 `samples/sample5/scenario2/bpmn/depot_inventory_check.bpmn`，作为从 sample4 Depot 片段抽取并细化出的库存校验小场景。
- 新增 `samples/sample5/scenario2/mcf/inventory_branches_reachable.mcf`，验证库存充足分支和缺货等待分支都可达。
- 新增 `samples/sample5/scenario2/verify.ps1`，一键完成 BPMN 转换、生成 LPS/LTS、检查数据表达式和执行 mCF。
- 新增 `samples/sample5/scenario2/mcrl2/` 下的转换与验证产物，便于复现实验结果。

Fix:

- 扩展 `scripts/bpmn2mcrl2.py`，支持从 BPMN `documentation` 中识别 `mcrl2:update X = expr`，并在生成的 mCRL2 中体现为进程参数更新。
- 调整排他网关分支生成逻辑，使带数据更新的分支不会在合流后丢失更新后的参数值。
- 保留并验证原有 sample4 全流程转换与 mCF 检查能力，确认本次扩展没有破坏已有模型。

## 快速使用

在仓库根目录执行默认验证：

```powershell
powershell -ExecutionPolicy Bypass -File samples\sample5\scenario2\verify.ps1
```

这个命令会自动完成：

- 将 `bpmn/depot_inventory_check.bpmn` 转换为 mCRL2。
- 检查生成结果中是否包含 `Container_Count`、`> 0`、`== 0`、`- 1`、`+ 1` 等数据判断和状态更新。
- 生成 LPS 和 LTS。
- 执行 `mcf/inventory_branches_reachable.mcf`，确认库存充足分支和缺货等待分支都可达。

默认验证会在转换时禁用 timer 特殊语义，把“等待补货”当作普通事件处理，从而生成可枚举的 LPS/LTS。

如果只想检查保留时间语义的 timed LPS 能否生成，可执行：

```powershell
powershell -ExecutionPolicy Bypass -File samples\sample5\scenario2\verify.ps1 -Timed -SkipLts
```

生成文件位于：

```text
samples/sample5/scenario2/mcrl2/
```

其中默认验证生成 `depot_inventory_check_output.mcrl2`、`depot_inventory_check.lps`、`depot_inventory_check.lts`；timed 验证生成 `depot_inventory_check_timed_output.mcrl2` 和 `depot_inventory_check_timed.lps`。
