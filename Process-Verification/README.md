# Process Verification（BPMN -> mCRL2）

这个目录提供了一个最小可运行脚本，用于把 BPMN 流程文件转换为 mCRL2 代码，便于后续形式化验证。

## 文件说明

- `bpmn2mcrl2.py`：将 BPMN 顺序流转换为 mCRL2（MVP 版本）
- `demo_output.mcrl2`：脚本运行后生成的输出文件

## 当前默认验证样例

脚本默认读取以下 BPMN 文件进行验证：

`samples/sample1/camunda/message_cossitence.bpmn`

脚本内部已使用相对项目根目录的绝对路径计算方式，不依赖你运行命令时所在目录。

## 运行方式

在项目根目录执行：

```bash
python3 Process-Verification/bpmn2mcrl2.py
```

成功后会看到类似输出：

```text
正在解析 BPMN 文件: .../samples/sample1/camunda/message_cossitence.bpmn ...
✅ 转换成功！mCRL2 代码已保存至: .../Process-Verification/demo_output.mcrl2
```

## 输出结果

生成文件路径：

`Process-Verification/demo_output.mcrl2`

该文件包含：

- `act`：从 BPMN 节点名称提取并清洗后的动作集合
- `proc MainProcess`：按顺序流连接得到的主流程
- `init MainProcess`：流程初始化入口

## 已知限制（MVP）

当前脚本主要支持顺序流的基础转换，不包含完整 BPMN 语义：

- 仅解析 `startEvent`、`task`、`endEvent`
- 按单一路径遍历 `sequenceFlow`
- 未处理网关分支/并发、消息事件、子流程等复杂结构
