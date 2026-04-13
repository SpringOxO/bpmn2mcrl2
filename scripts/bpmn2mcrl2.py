import xml.etree.ElementTree as ET
import re
from pathlib import Path
from collections import deque

def clean_name(name):
    """清理名称以符合 mCRL2 规范"""
    if not name: return "unnamed_action"
    # 替换非字母数字字符为下划线，转小写
    clean = re.sub(r'[^a-zA-Z0-9]', '_', name).strip('_').lower()
    return clean if clean else "action"

def convert_bpmn_to_mcrl2(bpmn_filepath, output_filepath):
    print(f"正在解析 BPMN 协作模型: {bpmn_filepath} ...")
    tree = ET.parse(bpmn_filepath)
    root = tree.getroot()
    ns = {"bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL"}

    # --- 1. 全局状态存储 ---
    sync_state = {
        "count": 0, 
        "rules": [], 
        "all_sync_actions": set(), 
        "extra_procs": [], 
        "init_procs": [],
        "messages": [],           # 存储格式: {"name": x, "src_proc": x, "tgt_proc": x}
        "exact_msg_nodes": {},    # 兼容 node_id 直接相连的 messageFlow
        "used_actions": set()
    }

    # --- 2. 解析 Collaboration 与 Process 映射 ---
    # 建立 Participant ID -> Process ID 的映射
    part_to_proc = {}
    for part in root.findall(".//bpmn:participant", ns):
        part_to_proc[part.attrib.get("id")] = part.attrib.get("processRef")

    # 建立 Node ID -> Process ID 的映射
    node_to_proc = {}
    for process in root.findall(".//bpmn:process", ns):
        p_id = process.attrib.get("id")
        for elem in process:
            if "id" in elem.attrib:
                node_to_proc[elem.attrib["id"]] = p_id

    # 解析消息流
    for mflow in root.findall(".//bpmn:messageFlow", ns):
        src = mflow.attrib.get("sourceRef")
        tgt = mflow.attrib.get("targetRef")
        m_name = clean_name(mflow.attrib.get("name", "msg"))
        
        # 溯源真正的发送/接收 Process
        src_proc = part_to_proc.get(src) or node_to_proc.get(src)
        tgt_proc = part_to_proc.get(tgt) or node_to_proc.get(tgt)
        
        sync_state["messages"].append({
            "name": m_name,
            "src_proc": src_proc,
            "tgt_proc": tgt_proc
        })
        
        # 如果是直接挂在 Task 上的 MessageFlow
        if src in node_to_proc: sync_state["exact_msg_nodes"][src] = ("s", m_name)
        if tgt in node_to_proc: sync_state["exact_msg_nodes"][tgt] = ("r", m_name)
        
        sync_state["rules"].append(f"s_{m_name} | r_{m_name} -> c_{m_name}")
        sync_state["all_sync_actions"].update({f"s_{m_name}", f"r_{m_name}", f"c_{m_name}"})

    # --- 3. 核心辅助函数 ---
    def node_type(elem): return elem.tag.split("}", 1)[-1]

    def seq(exprs):
        parts = [e for e in exprs if e and e != "delta" and e != ""]
        return " . ".join(parts) if parts else "delta"

    def find_parallel_join(branch_starts, flows_map):
        def get_reach(s):
            q, seen = deque([s]), set()
            while q:
                curr = q.popleft()
                if curr not in seen:
                    seen.add(curr); q.extend(flows_map.get(curr, []))
            return seen
        reach_sets = [get_reach(s) for s in branch_starts]
        candidates = set.intersection(*reach_sets) if reach_sets else set()
        return sorted(list(candidates))[0] if candidates else None

    # --- 4. 递归转换引擎 (新增 current_proc_id 传递) ---
    def build_expr(node_id, nodes_map, node_types_map, flows_map, current_proc_id, stop_node=None, visited=None):
        if not node_id or node_id == stop_node:
            return "" 
        
        if visited and node_id in visited:
            return "delta"
        
        visited = visited or set(); visited.add(node_id)
        ntype = node_types_map.get(node_id)
        next_nodes = flows_map.get(node_id, [])

        if ntype == "endEvent":
            name = clean_name(nodes_map.get(node_id, "end_event"))
            sync_state["used_actions"].add(name)
            return f"{name}(oid)"

        if ntype == "parallelGateway" and len(next_nodes) > 1:
            join = find_parallel_join(next_nodes, flows_map)
            sync_state["count"] += 1
            sid = sync_state["count"]
            t_s, t_r, t_c = f"s_start_gw_{sid}", f"r_start_gw_{sid}", f"c_start_gw_{sid}"
            # 1. 拆分接收端(r_join)和通信完成端(c_join)
            r_join = f"r_sync_join_{sid}"
            c_join = f"c_sync_join_{sid}"
            sync_state["all_sync_actions"].update({t_s, t_r, t_c, r_join, c_join})

            for i, b_start in enumerate(next_nodes):
                b_name = f"gw_{sid}_branch_{i}"
                s_sig = f"s_sync_{sid}_{i}"
                sync_state["all_sync_actions"].add(s_sig)
                b_body = build_expr(b_start, nodes_map, node_types_map, flows_map, current_proc_id, stop_node=join)
                sync_state["extra_procs"].append(f"  {b_name}(oid: OrderId) = {t_r}(oid) . {seq([b_body, f'{s_sig}(oid)'])} . delta;")
                sync_state["init_procs"].append(f"{b_name}(order_id(1))")

            j_logic = build_expr(join, nodes_map, node_types_map, flows_map, current_proc_id, stop_node=stop_node)
            # 2. Handler 强制执行 r_ 前缀的动作
            sync_state["extra_procs"].append(f"  gw_{sid}_handler(oid: OrderId) = {r_join}(oid) . {j_logic};")
            sync_state["init_procs"].append(f"gw_{sid}_handler(order_id(1))")

            sync_state["rules"].append(f"{t_s} | {' | '.join([t_r]*len(next_nodes))} -> {t_c}")
            
            # 3. Comm 规则必须包含所有分支的 s_ 和 Handler 的 r_
            s_syncs = [f"s_sync_{sid}_{i}" for i in range(len(next_nodes))]
            sync_state["rules"].append(f"{' | '.join(s_syncs)} | {r_join} -> {c_join}")
            return f"{t_s}(oid) . delta"

        # --- 核心修复：带上下文的动作推断机制 ---
        if node_id in sync_state["exact_msg_nodes"]:
            role, m_name = sync_state["exact_msg_nodes"][node_id]
            action_expr = f"{role}_{m_name}(oid)"
            sync_state["used_actions"].add(f"{role}_{m_name}")
        else:
            raw_name = nodes_map.get(node_id, "")
            action_name = clean_name(raw_name if raw_name else node_id)
            matched_msg = False
            
            # 提取去除 send/recv/receive 前缀后的核心词
            def get_core(name):
                return name.replace("send_", "").replace("recv_", "").replace("receive_", "")
            
            for msg in sync_state["messages"]:
                m_name = msg["name"]
                core_m = get_core(m_name)
                match_str = core_m if core_m else m_name
                
                # 如果任务名包含核心词，且当前进程属于该消息的源头或目标
                if match_str and match_str in action_name:
                    if current_proc_id == msg["src_proc"]:
                        action_expr = f"s_{m_name}(oid)"
                        sync_state["used_actions"].add(f"s_{m_name}")
                        matched_msg = True
                        break
                    elif current_proc_id == msg["tgt_proc"]:
                        action_expr = f"r_{m_name}(oid)"
                        sync_state["used_actions"].add(f"r_{m_name}")
                        matched_msg = True
                        break
            
            if not matched_msg:
                if ntype not in ["parallelGateway", "exclusiveGateway", "startEvent"]:
                    sync_state["used_actions"].add(action_name)
                    action_expr = f"{action_name}(oid)"
                else:
                    action_expr = ""

        if ntype == "exclusiveGateway":
            branches = [f"tau . {build_expr(n, nodes_map, node_types_map, flows_map, current_proc_id, stop_node)}" for n in next_nodes]
            return f"({' + '.join(branches)})"
        
        if next_nodes:
            tail = build_expr(next_nodes[0], nodes_map, node_types_map, flows_map, current_proc_id, stop_node)
            return seq([action_expr, tail])
        return action_expr

    # --- 5. 执行解析 ---
    main_procs_code = []
    for process in root.findall(".//bpmn:process", ns):
        p_id = process.attrib.get("id", "Process")
        clean_p_id = clean_name(p_id)
        nodes_map, node_types_map, start_nodes, flows_map = {}, {}, [], {}
        
        for elem in process:
            tag = node_type(elem)
            if tag in ["startEvent", "endEvent", "serviceTask", "receiveTask", "parallelGateway", "exclusiveGateway", "task"]:
                eid = elem.attrib["id"]
                nodes_map[eid] = elem.attrib.get("name", eid)
                node_types_map[eid] = tag
                if tag == "startEvent": start_nodes.append(eid)
            elif tag == "sequenceFlow":
                flows_map.setdefault(elem.attrib["sourceRef"], []).append(elem.attrib["targetRef"])

        for s in start_nodes:
            # 传入原生的 p_id 作为 current_proc_id 上下文
            logic = build_expr(flows_map.get(s, [None])[0], nodes_map, node_types_map, flows_map, p_id)
            main_procs_code.append(f"  {clean_p_id}(oid: OrderId) = {logic};")
            sync_state["init_procs"].append(f"{clean_p_id}(order_id(1))")

    # --- 6. 渲染输出 ---
    final_declarations = sorted(sync_state["used_actions"] | sync_state["all_sync_actions"])
    
    forbidden_prefixes = ("s_", "r_", "s_sync")
    allow_acts = [a for a in final_declarations if not a.startswith(forbidden_prefixes)]

    mcrl2_code = f"""% Auto-generated mCRL2 with Collaboration & Parallel Support
sort OrderId = struct order_id(pid: Pos);

act 
  {', '.join(final_declarations)} : OrderId;

proc 
{chr(10).join(main_procs_code)}
{chr(10).join(sync_state['extra_procs'])}

init 
  allow({{{', '.join(sorted(allow_acts))}}},
    comm({{{', '.join(sync_state['rules'])}}},
      {' || '.join(sync_state['init_procs'])}
    )
  );
"""
    with open(output_filepath, 'w', encoding='utf-8') as f:
        f.write(mcrl2_code)
    print(f"✅ 转换完成！输出至: {output_filepath}")

if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent.parent
    input_file = project_root / "samples" / "sample1" / "camunda" / "message_cossitence.bpmn"
    output_file = project_root / "samples" / "sample1" / "mcrl2" / "message_cossitence_output.mcrl2"
    
    output_file.parent.mkdir(parents=True, exist_ok=True)
    convert_bpmn_to_mcrl2(str(input_file), str(output_file))