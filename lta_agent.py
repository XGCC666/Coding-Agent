import os
import json
import subprocess
import re
import time
import openai
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

client = OpenAI(
    api_key=api_key, 
    base_url=base_url,
    timeout=180.0  # 放宽到 3 分钟，适应长文本
)

def read_file(filename):
    if not os.path.exists(filename):
        return f"Error: File '{filename}' does not exist."
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
            MAX_CHARS = 3500 
            if len(content) > MAX_CHARS:
                return content[:MAX_CHARS] + f"\n\n...[系统警告：文件过长已截断。AI请基于当前前言部分继续后续工作]..."
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

def insert_subtasks(target_task, new_tasks_str):
    """微创手术：精准在目标任务下方插入子任务，绝不破坏原有文件内容"""
    filepath = "todo.md"
    if not os.path.exists(filepath):
        return "Error: todo.md not found."
        
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    new_lines = []
    inserted = False
    # 去除任务前面的复选框，方便精准匹配
    clean_target = re.sub(r'^- \[[ xFAILED]+\] ', '', target_task).strip()
    
    for line in lines:
        new_lines.append(line)
        if not inserted and clean_target in line:
            # 找到目标任务，在其下方插入新任务
            for task_line in new_tasks_str.strip().split('\n'):
                if task_line.strip():
                    clean_new_task = task_line.strip()
                    if not clean_new_task.startswith("- ["):
                        clean_new_task = f"- [ ] {clean_new_task}"
                    # 加两个空格作为缩进，层级更清晰
                    new_lines.append(f"  {clean_new_task}\n") 
            inserted = True
            
    if inserted:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        return "Success: 子任务已安全、精准地插入到 todo.md 中，未丢失任何原有数据。"
    else:
        return "Error: 在 todo.md 中找不到目标任务，插入失败。"

def execute_command(command):
    # 🛑 终极防御：物理拦截 AI 的所有 Git 企图
    if command.strip().startswith("git "):
        print(f"    🛡️ [系统拦截] AI 试图执行危险操作: {command}")
        return "❌ Error: 权限拒绝！老板已下令禁止 AI 执行任何 git 命令。请跳过版本控制，专注写代码！"

    venv_dir = "venv"
    if os.path.exists(venv_dir):
        # 强制 Windows 路径规范
        python_path = os.path.join(venv_dir, "Scripts", "python.exe")
        pip_path = os.path.join(venv_dir, "Scripts", "pip.exe")

        if command.startswith("python "):
            command = command.replace("python ", f"{python_path} ", 1)
        elif command.startswith("pip "):
            command = command.replace("pip ", f"{pip_path} ", 1)

    print(f"    🖥️ [终端执行] > {command}")
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
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
            "description": "Execute terminal command in Windows.",
            "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "insert_subtasks",
            "description": "当任务过于复杂时，调用此工具将任务拆解，并安全地插入到 todo.md 中。",
            "parameters": {
                "type": "object", 
                "properties": {
                    "target_task": {"type": "string", "description": "当前执行的任务名称。"}, 
                    "new_tasks_str": {"type": "string", "description": "新子任务列表，每行一个。例如：'- [ ] 子任务1\\n- [ ] 子任务2'"}
                }, 
                "required": ["target_task", "new_tasks_str"]
            }
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
# 阶段 3：打工人引擎 (包含 API 智能重试机制)
# ==========================================
def execute_subtask(task_description):
    print(f"  👷 [打工人] 开始执行: {task_description}")
    
    messages = [
        {"role": "system", "content": """你是一个底层代码执行员。目标：完成给定的单一子任务。
【动态拆分协议】（极其重要）：
如果评估发现任务复杂（包含多个步骤或需大量写代码），你必须触发拆解：
1. 必须调用 `insert_subtasks` 工具，将当前任务拆分为 3-5 个更细化的微观任务。
2. ⚠️ 绝对禁止使用 `write_file` 覆写 todo.md，那会导致其他任务丢失！你只能使用 `insert_subtasks`！
3. 插入完成后，直接回复“已拆解细化完毕”并结束当前思考。
⚠️ 绝对禁止并发调用工具！你必须严格串行工作。
【输出限制】：专心调用工具，绝不要在回复中大段总结或复读文档内容！"""},
        {"role": "user", "content": f"当前任务：{task_description}"}
    ]

    step_count = 0
    MAX_STEPS = 40

    while step_count < MAX_STEPS:
        step_count += 1
        print(f"    ⏳ [等待大模型思考中... 第 {step_count}/{MAX_STEPS} 步]") 
        
        # --- API 智能重试模块 ---
        api_retry_count = 0
        response = None
        while api_retry_count < 5: 
            try:
                response = client.chat.completions.create(
                    model=MODEL_NAME, 
                    messages=messages, 
                    tools=tools, 
                    tool_choice="auto",
                    parallel_tool_calls=False 
                )
                break 
            except openai.RateLimitError:
                print(f"    ⚠️ [API 429 频率限制]: 等待 30 秒后重试... ({api_retry_count+1}/5)")
                time.sleep(30)
            except openai.APITimeoutError:
                print(f"    ⚠️ [API 504 超时假死]: 节点无响应，等待 15 秒后重试... ({api_retry_count+1}/5)")
                time.sleep(15)
            except openai.InternalServerError:
                print(f"    ⚠️ [API 500/502 服务器崩溃]: 等待 20 秒后重试... ({api_retry_count+1}/5)")
                time.sleep(20)
            except openai.APIConnectionError:
                print(f"    ⚠️ [网络断连]: 等待 10 秒后重试... ({api_retry_count+1}/5)")
                time.sleep(10)
            except Exception as e:
                print(f"    ⚠️ [未知 API 错误]: {str(e)}。等待 10 秒后重试... ({api_retry_count+1}/5)")
                time.sleep(10)
            api_retry_count += 1
            
        if response is None:
            return False, "API 连续崩溃 5 次，当前子任务被迫中断。"
        # ------------------------

        message = response.choices[0].message
        messages.append(message)

        if message.tool_calls:
            for tool_call in message.tool_calls:
                func_name = tool_call.function.name
                try:
                    args = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                
                target = args.get('filename') or args.get('command') or args.get('target_task')
                print(f"    🛠️ [调用工具] {func_name} | {target}")
                
                if func_name == "write_file":
                    result = write_file(args.get("filename", ""), args.get("content", ""))
                elif func_name == "read_file":
                    result = read_file(args.get("filename", ""))
                elif func_name == "execute_command":
                    result = execute_command(args.get("command", ""))
                elif func_name == "insert_subtasks":
                    result = insert_subtasks(args.get("target_task", ""), args.get("new_tasks_str", ""))
                else:
                    result = "Error: Unknown."
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": func_name,
                    "content": result
                })
        else:
            print(f"  ✅ [打工人汇报]: {message.content.strip()}")
            return True, message.content

    print(f"  🚨 [打工人报警]: 陷入逻辑死循环，触发 {MAX_STEPS} 步超时熔断！")
    return False, "达到最大思考步数，任务执行陷入僵局。"

# ==========================================
# 阶段 4：包工头引擎 (包含任务级冷却重启)
# ==========================================
def manager_loop(global_goal):
    todo_file = "todo.md"
    
    if not os.path.exists(todo_file):
        print("\n🧠 [包工头] 接收到大项目，请手动提供包含 4 个阶段的 todo.md！")
        return

    while True:
        current_task = get_next_task_and_update(todo_file)
        
        if not current_task:
            print("\n🎉🎉🎉 [包工头] 汇报老板，todo.md 中的所有任务已全部圆满完成！")
            break
            
        print(f"\n" + "="*50)
        print(f"🎯 [包头工分派任务] -> {current_task}")
        print("="*50)
        
        # --- 任务级重启机制 (大冷却) ---
        MAX_TASK_RETRIES = 3 
        task_retry_count = 0
        
        while task_retry_count < MAX_TASK_RETRIES:
            success, msg = execute_subtask(current_task)
            
            if success:
                get_next_task_and_update(todo_file, update_status="x", task_to_update=current_task)
                print(f"✒️ [包工头] 任务顺利完成，已打钩 [x]！休息 3 秒防高频并发...")
                time.sleep(3)
                break 
            else:
                task_retry_count += 1
                print(f"\n🛑 [任务受挫] 原因: {msg}")
                if task_retry_count < MAX_TASK_RETRIES:
                    print(f"🛡️ [挂机保护激活] 为防止死循环或系统崩溃，流水线进入 120 秒深度冷却期...")
                    print(f"⏳ 倒计时 2 分钟后，将对当前任务进行第 {task_retry_count + 1} 次重新派发！")
                    time.sleep(120) 
                else:
                    get_next_task_and_update(todo_file, update_status="FAILED", task_to_update=current_task)
                    print(f"\n☠️ [彻底失败] 任务重试 {MAX_TASK_RETRIES} 次均告失败，已标记 [FAILED]。请人工排查！")
                    return 
        # ------------------------------

# ==========================================
# 阶段 5：入口组装
# ==========================================
if __name__ == "__main__":
    print("🚀 欢迎使用 LTA 长序列全自动智能体 (终极防御挂机版)")
    
    try:
        if os.path.exists("todo.md"):
            print("检测到 todo.md，挂机流水线已启动...")
            manager_loop("继续执行现有 todo")
        else:
            print("请先在目录下创建包含任务的 todo.md 文件！")
    except KeyboardInterrupt:
        print("\n👋 已手动强制停机。进度已保存在 todo.md 中。")