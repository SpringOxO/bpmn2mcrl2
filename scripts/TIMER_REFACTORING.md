# 定时器建模重构文档 (Timer Refactoring)

## 重构目标

优化定时器的转换逻辑，解决以下问题：
1. **解耦定时器与业务进程**：原实现中定时器逻辑嵌入在业务进程内，导致计时与业务逻辑耦合。
2. **支持独立触发**：定时器应作为独立进程运行，能够独立于业务状态进行计时。
3. **支持重新触发**：定时器在触发后应能自动开始下一轮计时。
4. **提高验证性能**：通过优化递归结构，避免在模型验证时出现状态空间爆炸。

## 修改内容

### 1. 独立定时器进程
为每个带有周期性定时器（Cycle Timer）的启动事件生成一个独立的 `Timer` 进程。
- **名称**：`Timer_[StartEventID]`
- **逻辑**：`(tau @ t) . s_trigger_[ID](oid) . Timer_[ID](oid, t + interval)`
- **初始化**：在 `init` 部分独立启动，初始时间为0。

### 2. 触发机制
使用 mCRL2 的同步动作实现定时器与业务进程的通信。
- **动作**：`s_trigger_[ID]` (发送), `r_trigger_[ID]` (接收), `c_trigger_[ID]` (同步结果)。
- **规则**：`s_trigger | r_trigger -> c_trigger`。
- **强制同步**：在 `allow` 集合中仅保留 `c_trigger`，强制定时器必须与业务进程同步。

### 3. 业务进程递归结构优化
业务进程修改为顺序递归结构，以支持持续的触发响应：
- **逻辑**：`Process(oid) = (r_trigger1(oid) . Logic1 + r_trigger2(oid) . Logic2 + ...) . Process(oid)`
- **优势**：
  - 清晰表达了业务进程对定时器信号的监听。
  - 避免了使用 `||` 递归导致的无限并行状态空间爆炸，使 `mcrl22lps` 等工具能够高效处理。

### 4. 代码实现细节
- 修改 `build_start_scope` 函数，识别周期性定时器并自动注册同步规则和生成 `Timer` 进程。
- 修改 `convert_bpmn_to_mcrl2` 主循环，根据是否存在周期性定时器自动调整业务进程的递归定义。
- 更新警告信息，更准确地描述定时器建模方式（"modeled as separate process trigger"）。

## 验证示例 (loan-granting.bpmn)

重构后生成的 mCRL2 代码结构如下：

```mcrl2
proc
  % 业务进程：等待触发并执行逻辑，然后再次进入等待状态
  loan_process(oid: OrderId) = 
    r_trigger_startevent_1(oid) . (Logic...) . loan_process(oid);

  % 独立定时器进程：每300秒触发一次同步信号
  Timer_startevent_1(oid: OrderId, t: Real) = 
    (tau @ t) . s_trigger_startevent_1(oid) . Timer_startevent_1(oid, t + 300);

init
  allow({c_trigger_startevent_1, ...},
    comm({s_trigger_startevent_1 | r_trigger_startevent_1 -> c_trigger_startevent_1},
      Timer_startevent_1(order_id(1), 0) || loan_process(order_id(1))
    )
  );
```

## 使用说明

重构后的工具支持以下验证流程：
1. `python scripts/bpmn2mcrl2.py`：生成 .mcrl2 文件。
2. `mcrl22lps --timed output.mcrl2 output.lps`：将模型转换为线性过程（LPS）。
3. 使用 `lpsxsim` 或 `ltsgraph` 进行分析。
