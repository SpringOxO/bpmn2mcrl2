# Scenario2 MCF Update

本文件仅记录这次对 `scenario2` 的 mCF 更新，不修改原有 `README.md`。

## 本次更新

- 新增 `mcf/inventory_safety_invariants.mcf`
- 更新 `mcf/inventory_branches_reachable.mcf`
- 更新 `verify.ps1`，让它同时检查两个 mCF

## 新增性质

### 库存安全不变式

发送空箱时，携带的库存数量必须满足 `cnt >= 0`：

```mcf
[true*] forall cnt: Int .
  [c_send_empty_ctn_to_transport___count___1_to_transport__empty_ctn_received(order_id(1), cnt)] val(cnt >= 0)
```

### 分支可达性

确认库存充足分支和缺货等待分支都可达：

```mcf
<true* . c_send_empty_ctn_to_transport___count___1_to_transport__empty_ctn_received(order_id(1), 10)> true
&&
<true* . c_notify_sa__empty_ctn_shortage_to_sa__shortage_waiting_received(order_id(1))> true
```

## 验证结果

当前验证已跑通：

- BPMN 转换
- LPS 生成
- LTS 生成
- 两条 mCF

## 使用方式

在仓库根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File samples\sample5\scenario2\verify.ps1
```
