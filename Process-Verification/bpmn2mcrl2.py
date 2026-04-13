import xml.etree.ElementTree as ET
import sys
import re
from pathlib import Path

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
    ns = {'bpmn': 'http://www.omg.org/spec/BPMN/20100524/MODEL'}
    
    nodes = {}  
    start_node_id = None
    
    for event in root.findall('.//bpmn:startEvent', ns):
        nodes[event.attrib['id']] = clean_name(event.attrib.get('name', 'start_event'))
        start_node_id = event.attrib['id']
        
    for task in root.findall('.//bpmn:task', ns):
        nodes[task.attrib['id']] = clean_name(task.attrib.get('name', task.attrib['id']))
        
    for event in root.findall('.//bpmn:endEvent', ns):
        nodes[event.attrib['id']] = clean_name(event.attrib.get('name', 'end_event'))

    if not start_node_id:
        print("❌ 错误：在 BPMN 中没有找到 Start Event！")
        return

    flows = {} 
    for flow in root.findall('.//bpmn:sequenceFlow', ns):
        source = flow.attrib['sourceRef']
        target = flow.attrib['targetRef']
        flows[source] = target

    current_id = start_node_id
    process_steps = []
    
    while current_id:
        if current_id in nodes:
            process_steps.append(nodes[current_id])
        current_id = flows.get(current_id) 

    actions_str = ",\n  ".join(set(process_steps))
    process_str = " . \n  ".join(process_steps)
    
    mcrl2_code = f"""% Auto-generated mCRL2 from BPMN 
% MVP Demo Version - Sequential Flow Only

% 1. 定义动作
act 
  {actions_str};

% 2. 定义流程
proc 
  MainProcess = 
  {process_str};

% 3. 初始化
init 
  MainProcess;
"""

    with open(output_filepath, 'w', encoding='utf-8') as f:
        f.write(mcrl2_code)
        
    print(f"✅ 转换成功！mCRL2 代码已保存至: {output_filepath}")

if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent.parent
    input_file = project_root / "samples" / "sample1" / "camunda" / "message_cossitence.bpmn"
    output_file = Path(__file__).resolve().parent / "demo_output.mcrl2"
    
    try:
        convert_bpmn_to_mcrl2(str(input_file), str(output_file))
    except FileNotFoundError:
        print(f"❌ 找不到文件 {input_file}，请确保文件名拼写正确并在同一目录下。")
