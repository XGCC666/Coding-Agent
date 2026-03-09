import os
import json
import subprocess
import re
from openai import OpenAI
from dotenv import load_dotenv

# ==========================================
# 阶段 1：基础脚手架与底层武器库
# ==========================================
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")
base_url = os.getenv("OPENAI_BASE_URL")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o")

if not api_key:
    raise ValueError("严重错误: 找不到 API Key，请检查 .env 文件！")

# 补丁 1：强制 60 秒超时，防止中转接口假死
client = OpenAI(
    api_key=api_key, 
    base_url=base_url,
    timeout=60.0 
)

def read_file(filename):
    if not os.path.exists(filename):
        return f"Error: File '{filename}' does not exist."
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
            # 补丁 2：超大文件截断保护，防止撑爆第三方 API
            MAX_CHARS = 12000 
            if len(content) > MAX_CHARS:
                return content[:MAX_CHARS] + f"\n\n...[系统警告：文件内容过长，为防止网络超时，已截断并只显示前 {MAX_CHARS} 个字符。AI 请基于当前信息继续工作]..."
            return content
    except Exception as e:
        return f"Error reading file: {str(e)}"

def write_file(filename, content):
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Success: File '{filename}' written successfully."
    except Exception as e:
        return f"Error writing file: {str(e)}"

def execute_command(command):
    venv_dir = "venv"
    if os.path.exists(venv_dir):
        is_windows = (os.name == 'nt')
        python_path = os.path.join(venv_dir, "Scripts", "python") if is_windows else os.path.join(venv_dir, "bin", "python")
        pip_path = os.path.join(venv_dir, "Scripts", "pip") if is_windows else os.path.join(venv_dir, "bin", "pip")

        if command.startswith("python "):
            command = command.replace("python ", f"{python_path} ", 1)
        elif command.startswith("python3 "):
            command = command.replace("python3 ", f"{python_path} ", 1)
        elif command.startswith("pip "):
            command = command.replace("pip ", f"{pip_path} ", 1)
        elif command.startswith("pip3 "):
            command = command.replace("pip3 ", f"{pip_path} ", 1)

    print(f"    🖥️ [终端执行] > {command}")
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            return result.stdout.strip() if result.stdout else "Command executed successfully."
        else:
            return f"Command Error:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 60 seconds."
    except Exception as e:
        return f"Error: {str(e)}"

tools = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read file content.",
            "parameters": {"type": "object", "properties": {"filename": {"type": "string"}}, "required": ["filename"]}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write text to a file.",
            "parameters": {"type": "object", "properties": {"filename": {"type": "string"}, "content": {"type": "string"}}, "required": ["filename", "content"]}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_command",
            "description": "Execute terminal command (auto-routed to venv if exists).",
            "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}
        }
    }
]

# ==========================================
# 阶段 2：任务状态解析器
# ==========================================
def get_next_task_and_update(filepath, update_status=None, task_to_update=None):
    if not os.path.exists(filepath):
        return None
        
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    if update_status is None:
        for line in lines:
            match = re.search(r'- \[\s\] (.*)', line)
            if match:
                return match.group(1).strip()
        return None
    else:
        new_lines = []
        updated = False
        for line in lines:
            if not updated and task_to_update in line and "- [ ]" in line:
                new_lines.append(line.replace("- [ ]", f"- [{update_status}]", 1))
                updated = True
            else:
                new_lines.append(line)
                
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        return updated

# ==========================================
# 阶段 3：打工人引擎 (防假死 + 强迫症拆分)
# ==========================================
def execute_subtask(task_description):
    print(f"  👷 [打工人] 开始执行: {task_description}")
    
    # 补丁 3：严厉警告 AI 闭嘴干活，不要大段总结
    messages = [
        {"role": "system", "content": """你是一个底层代码执行员。目标：完成给定的单一子任务。
【动态拆分协议】（极其重要）：
如果评估发现任务复杂（例如需要写多行代码、设计架构或包含多个步骤），你必须触发拆解：
1. 先调用 read_file 读取 todo.md。
2. 拿到内容后，再调用 write_file 覆写 todo.md。在当前任务的正下方，插入至少 3-5 个更细化的微观任务（格式必须为 `- [ ] 细分任务内容`）。
3. 插入完成后，直接回复“已拆解细化完毕”并结束当前思考。
⚠️ 绝对禁止并发调用工具！你必须严格串行工作：先 read_file，等拿到返回结果后，再在下一步思考中调用 write_file！
⚠️ 【输出限制】：如果你读取了文档，绝对不要在你的回复中大段总结或重复文档内容！这会导致网络超时！你只需回复“已阅读完毕”，然后立即进入下一步拆分或写代码！
如果任务足够简单，请大胆使用 execute_command 写代码和跑测试。完成任务后，用一句话汇报结果。遇到报错请自我分析并修复。"""},
        {"role": "user", "content": f"当前任务：{task_description}"}
    ]

    step_count = 0
    MAX_STEPS = 15

    while step_count < MAX_STEPS:
        step_count += 1
        print(f"    ⏳ [等待大模型思考中... 第 {step_count} 轮请求]") 
        
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME, 
                messages=messages, 
                tools=tools, 
                tool_choice="auto",
                parallel_tool_calls=False # 禁用并发工具调用
            )
        except Exception as e:
            print(f"    🚨 [API 网络请求报错]: {str(e)}")
            return False, "API 网络断开或超时"

        message = response.choices[0].message
        messages.append(message)

        if message.tool_calls:
            for tool_call in message.tool_calls:
                func_name = tool_call.function.name
                try:
                    args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    print(f"    🚨 [JSON 解析错误]: {tool_call.function.arguments}")
                    args = {}
                
                target = args.get('filename') or args.get('command')
                print(f"    🛠️ [调用工具] {func_name} | {target}")
                
                if func_name == "write_file":
                    result = write_file(args.get("filename", ""), args.get("content", ""))
                elif func_name == "read_file":
                    result = read_file(args.get("filename", ""))
                elif func_name == "execute_command":
                    result = execute_command(args.get("command", ""))
                else:
                    result = "Error: Unknown."
                
                display_res = result[:200] + "..." if len(result) > 200 else result
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": func_name,
                    "content": result
                })
        else:
            print(f"  ✅ [打工人汇报]: {message.content.strip()}")
            return True, message.content

    print(f"  🚨 [打工人报警]: 尝试了 {MAX_STEPS} 次依然失败，触发超时熔断！")
    return False, "达到最大重试次数，任务失败。"

# ==========================================
# 阶段 4：包工头引擎
# ==========================================
def manager_loop(global_goal):
    todo_file = "todo.md"
    
    if not os.path.exists(todo_file):
        print("\n🧠 [包工头] 接收到大项目，正在思考架构并生成 todo.md 计划表...")
        prompt = f"你是一个顶级架构师。请把以下宏大目标拆解为具体的执行步骤。必须以 Markdown 复选框格式输出（例如 '- [ ] 1. 创建 venv'）。任务必须颗粒度极细，一步一步来。不要输出任何解释说明，只输出复选框列表。\n目标：{global_goal}"
        
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                timeout=60.0
            )
            plan = response.choices[0].message.content
            plan = plan.replace("```markdown", "").replace("```", "").strip()
            write_file(todo_file, plan)
            print("📝 [包工头] 计划表生成完毕！准备开始自动流水线挂机...\n")
        except Exception as e:
            print(f"🚨 [包工头网络报错]: {str(e)}")
            return

    while True:
        current_task = get_next_task_and_update(todo_file)
        
        if not current_task:
            print("\n🎉🎉🎉 [包工头] 汇报老板，todo.md 中的所有任务已全部圆满完成！")
            break
            
        print(f"\n" + "="*50)
        print(f"🎯 [包头工分派任务] -> {current_task}")
        print("="*50)
        
        success, msg = execute_subtask(current_task)
        
        if success:
            get_next_task_and_update(todo_file, update_status="x", task_to_update=current_task)
            print(f"✒️ [包工头] 任务顺利完成，已在 todo.md 中打钩 [x]！")
        else:
            get_next_task_and_update(todo_file, update_status="FAILED", task_to_update=current_task)
            print(f"\n🛑 [严重警告] 任务卡死！已在 todo.md 标记 [FAILED]。流水线已紧急停机！请人工介入。")
            break

# ==========================================
# 阶段 5：入口组装
# ==========================================
if __name__ == "__main__":
    print("🚀 欢迎使用 LTA 长序列全自动智能体 (挂机版)")
    print("💡 提示：你可以直接输入宏大目标，或者在当前目录手动创建一个 todo.md 然后按回车启动。")
    
    try:
        user_input = input("\n👑 [老板指令] 请输入您的宏大项目需求: \n> ")
        if user_input.strip():
            manager_loop(user_input)
        elif os.path.exists("todo.md"):
            print("检测到已存在的 todo.md，直接开始挂机续跑...")
            manager_loop("继续执行现有 todo")
        else:
            print("退出系统。")
    except KeyboardInterrupt:
        print("\n👋 已手动强制停机。进度已保存在 todo.md 中，下次可断点续传。")