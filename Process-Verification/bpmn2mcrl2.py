import xml.etree.ElementTree as ET
import re
from pathlib import Path
from collections import deque

def clean_name(name):
    """清理节点名称，使其符合 mCRL2 的动作命名规范（小写字母、数字、下划线）"""
    if not name:
        return "unnamed_action"
    clean = re.sub(r'[^a-zA-Z0-9]', '_', name).strip('_').lower()
    return clean if clean else "action"

def convert_bpmn_to_mcrl2(bpmn_filepath, output_filepath):
    print(f"正在解析 BPMN 文件: {bpmn_filepath} ...")

    tree = ET.parse(bpmn_filepath)
    root = tree.getroot()
    ns = {"bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL"}

    supported_tags = {
        "startEvent",
        "endEvent",
        "task",
        "serviceTask",
        "userTask",
        "receiveTask",
        "sendTask",
        "manualTask",
        "scriptTask",
        "businessRuleTask",
        "callActivity",
        "subProcess",
        "exclusiveGateway",
        "parallelGateway",
    }

    def node_type(elem):
        return elem.tag.split("}", 1)[-1]

    def seq(exprs):
        parts = [e for e in exprs if e and e != "delta"]
        if not parts:
            return "delta"
        return " . ".join(parts)

    def collect_reachable(start, flows_map):
        q = deque([start])
        seen = set()
        while q:
            cur = q.popleft()
            if cur in seen:
                continue
            seen.add(cur)
            for nxt in flows_map.get(cur, []):
                q.append(nxt)
        return seen

    def distance_map(start, flows_map):
        q = deque([(start, 0)])
        dist = {}
        while q:
            cur, d = q.popleft()
            if cur in dist:
                continue
            dist[cur] = d
            for nxt in flows_map.get(cur, []):
                q.append((nxt, d + 1))
        return dist

    def find_parallel_join(branch_starts, flows_map):
        if not branch_starts:
            return None
        reach_sets = [collect_reachable(s, flows_map) for s in branch_starts]
        candidates = set.intersection(*reach_sets) if reach_sets else set()
        if not candidates:
            return None
        dist_maps = [distance_map(s, flows_map) for s in branch_starts]
        best = None
        best_score = None
        for c in sorted(candidates):
            score = sum(dm.get(c, 10**9) for dm in dist_maps)
            if best_score is None or score < best_score:
                best = c
                best_score = score
        return best

    def build_expr(node_id, nodes_map, node_types_map, flows_map, stop_nodes=None, visited=None):
        if stop_nodes is None:
            stop_nodes = set()
        if visited is None:
            visited = set()
        if node_id in stop_nodes:
            return "delta"
        if node_id in visited:
            return "delta"

        current_visited = set(visited)
        current_visited.add(node_id)

        ntype = node_types_map.get(node_id, "unknown")
        next_nodes = flows_map.get(node_id, [])

        if ntype == "endEvent":
            return nodes_map.get(node_id, "end_event")

        if ntype == "parallelGateway":
            if len(next_nodes) <= 1:
                if not next_nodes:
                    return "delta"
                return build_expr(next_nodes[0], nodes_map, node_types_map, flows_map, stop_nodes, current_visited)
            join = find_parallel_join(next_nodes, flows_map)
            branch_exprs = []
            for b in next_nodes:
                branch_exprs.append(
                    build_expr(
                        b,
                        nodes_map,
                        node_types_map,
                        flows_map,
                        stop_nodes | ({join} if join else set()),
                        current_visited,
                    )
                )
            parallel_expr = "(" + " || ".join(be for be in branch_exprs if be and be != "delta") + ")"
            if join:
                return seq(
                    [
                        parallel_expr,
                        build_expr(join, nodes_map, node_types_map, flows_map, stop_nodes, current_visited),
                    ]
                )
            return parallel_expr

        if ntype == "exclusiveGateway":
            if not next_nodes:
                return "delta"
            choices = [
                build_expr(n, nodes_map, node_types_map, flows_map, stop_nodes, current_visited)
                for n in next_nodes
            ]
            choices = [c for c in choices if c and c != "delta"]
            return "(" + " + ".join(choices) + ")" if choices else "delta"

        action_expr = nodes_map.get(node_id, clean_name(node_id))
        if not next_nodes:
            return action_expr
        if len(next_nodes) == 1:
            tail = build_expr(next_nodes[0], nodes_map, node_types_map, flows_map, stop_nodes, current_visited)
            return seq([action_expr, tail])
        branches = [
            build_expr(n, nodes_map, node_types_map, flows_map, stop_nodes, current_visited)
            for n in next_nodes
        ]
        branches = [b for b in branches if b and b != "delta"]
        return seq([action_expr, "(" + " + ".join(branches) + ")" if branches else "delta"])

    all_actions = set()
    proc_defs = []

    for process in root.findall(".//bpmn:process", ns):
        process_id = process.attrib.get("id", "Process")
        proc_name = clean_name(process_id)

        nodes = {}
        node_types_map = {}
        start_nodes = []
        flows = {}

        for elem in process:
            tag = node_type(elem)
            if tag in supported_tags:
                node_id = elem.attrib["id"]
                node_name = elem.attrib.get("name", node_id)
                nodes[node_id] = clean_name(node_name)
                node_types_map[node_id] = tag
                if tag == "startEvent":
                    start_nodes.append(node_id)
            elif tag == "sequenceFlow":
                source = elem.attrib["sourceRef"]
                target = elem.attrib["targetRef"]
                flows.setdefault(source, []).append(target)

        if not start_nodes:
            continue

        for node_id, action_name in nodes.items():
            if node_types_map.get(node_id) not in {"exclusiveGateway", "parallelGateway"}:
                all_actions.add(action_name)

        start_exprs = [
            build_expr(s, nodes, node_types_map, flows, stop_nodes=set(), visited=set())
            for s in start_nodes
        ]
        start_exprs = [e for e in start_exprs if e and e != "delta"]
        body = " || ".join(start_exprs) if len(start_exprs) > 1 else (start_exprs[0] if start_exprs else "delta")
        proc_defs.append((proc_name, body))

    if not proc_defs:
        print("❌ 错误：没有找到可翻译的 BPMN process。")
        return

    actions_str = ",\n  ".join(sorted(all_actions))
    proc_str = "\n\n".join([f"  {name} = {body};" for name, body in proc_defs])
    init_body = " || ".join(name for name, _ in proc_defs)

    mcrl2_code = f"""% Auto-generated mCRL2 from BPMN 
% Improved version with process separation and gateway semantics

% 1. 定义动作
act 
  {actions_str};

% 2. 定义流程（按 BPMN process）
proc 
{proc_str}

% 3. 初始化
init 
  {init_body};
"""

    with open(output_filepath, 'w', encoding='utf-8') as f:
        f.write(mcrl2_code)
        
    print(f"✅ 转换成功！mCRL2 代码已保存至: {output_filepath}")

if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent.parent
    input_file = project_root / "samples" / "sample1" / "camunda" / "message_cossitence.bpmn"
    output_file = Path(__file__).resolve().parent / "message_cossitence_output.mcrl2"
    
    try:
        convert_bpmn_to_mcrl2(str(input_file), str(output_file))
    except FileNotFoundError:
        print(f"❌ 找不到文件 {input_file}，请确保文件名拼写正确并在同一目录下。")
