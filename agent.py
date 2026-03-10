import os
import json
import subprocess
from openai import OpenAI
from dotenv import load_dotenv  # 新增：导入 dotenv 库

# 1. 加载 .env 文件中的环境变量
load_dotenv()

# 2. 从环境变量中安全地读取配置，不再硬编码！
api_key = os.getenv("OPENAI_API_KEY")
base_url = os.getenv("OPENAI_BASE_URL")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o") # 如果没填，默认用 gpt-4o

if not api_key:
    raise ValueError("严重错误: 找不到 API Key，请检查 .env 文件！")

client = OpenAI(
    api_key=api_key,
    base_url=base_url 
)

# --- 2. 工具库 (底层武器库) ---

def read_file(filename):
    """读取文件内容"""
    if not os.path.exists(filename):
        return f"Error: File '{filename}' does not exist."
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"

def write_file(filename, content):
    """写入文件内容"""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Success: File '{filename}' written successfully."
    except Exception as e:
        return f"Error writing file: {str(e)}"

def execute_command(command):
    """在终端执行命令，智能路由到 venv 环境"""
    
    # 智能拦截：如果存在 venv，自动替换 python 和 pip 的路径
    venv_dir = "venv"
    if os.path.exists(venv_dir):
        # 判断是 Windows 还是 Mac/Linux
        is_windows = (os.name == 'nt')
        python_path = os.path.join(venv_dir, "Scripts", "python") if is_windows else os.path.join(venv_dir, "bin", "python")
        pip_path = os.path.join(venv_dir, "Scripts", "pip") if is_windows else os.path.join(venv_dir, "bin", "pip")

        # 替换开头的命令，确保依赖安装和运行都在 venv 中
        if command.startswith("python "):
            command = command.replace("python ", f"{python_path} ", 1)
        elif command.startswith("python3 "):
            command = command.replace("python3 ", f"{python_path} ", 1)
        elif command.startswith("pip "):
            command = command.replace("pip ", f"{pip_path} ", 1)
        elif command.startswith("pip3 "):
            command = command.replace("pip3 ", f"{pip_path} ", 1)

    print(f"  [终端实际执行] > {command}")
    
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            return result.stdout.strip() if result.stdout else "Command executed successfully (no output)."
        else:
            return f"Command Error:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 60 seconds."
    except Exception as e:
        return f"Error: {str(e)}"

# --- 3. 工具的 JSON Schema 注册 ---
tools = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the content of a file. Essential for checking existing code or reading the todo.md plan.",
            "parameters": {
                "type": "object",
                "properties": {"filename": {"type": "string"}},
                "required": ["filename"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write code or text to a file. Used to create scripts or update the todo.md plan.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["filename", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_command",
            "description": "Execute a bash/terminal command. Use this to run 'python -m venv venv', 'pip install', or run scripts.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"]
            }
        }
    }
]

# --- 4. 灵魂注入：系统提示词 ---
SYSTEM_PROMPT = """你是一个顶级的 AI 架构师和全自动编程代理。
你运行在一个全新的空文件夹中。你必须严格遵循以下【规划-执行】工作流：

【环境规范】（极其重要）：
1. 如果任务需要第三方库，你的首要行动必须是调用 execute_command 运行 `python -m venv venv` 来创建虚拟环境。
2. 创建完毕后，你可以正常输出 `pip install xxx` 或 `python xxx.py`，底层系统会自动帮你将命令路由到 venv 内部，你不需要手动激活环境。

【工作流规范】：
第一步：使用 write_file 创建 `todo.md`。将任务拆解为具体的复选框步骤（例如 `- [ ] 1. 创建 venv 环境`，`- [ ] 2. 安装 requests 库` 等）。
第二步：每次行动前，使用 read_file 读取 `todo.md` 确认进度。
第三步：编写代码、运行测试。如果测试报错，自我分析并修改代码，直到测试通过。
第四步：每完成并成功测试一个小任务，必须使用 write_file 覆写 `todo.md`，把 `[ ]` 改成 `[x]`。
第五步：直到所有任务打钩，向用户汇报完成。

严禁一次性写大量代码而不测试。必须步步为营，改一点，测一点，打个钩！"""

# --- 5. ReAct 核心循环 ---
def run_agent(task_description):
    print(f"🚀 [任务下达]: {task_description}\n")
    
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task_description}
    ]

    while True:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            tools=tools,
            tool_choice="auto"
        )
        message = response.choices[0].message
        messages.append(message) 

        if message.tool_calls:
            for tool_call in message.tool_calls:
                func_name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)
                
                target = args.get('filename') or args.get('command')
                print(f"\n🤖 [AI 决定行动] 🛠️ {func_name} | 🎯 {target}")
                
                if func_name == "write_file":
                    result = write_file(args["filename"], args["content"])
                elif func_name == "read_file":
                    result = read_file(args["filename"])
                elif func_name == "execute_command":
                    result = execute_command(args["command"])
                else:
                    result = "Error: Unknown function."
                
                # 在终端显示简短结果
                display_res = result[:300] + "\n...(截断输出)" if len(result) > 300 else result
                print(f"   [执行反馈] ⬇️\n{display_res.strip()}")
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": func_name,
                    "content": result
                })
        else:
            print(f"\n✅ [任务圆满完成]:\n{message.content}")
            break

if __name__ == "__main__":
    print("🤖 欢迎使用专属 AI 编程代理 (输入 'exit' 退出)")
    while True:
        try:
            user_input = input("\n📝 请下达新任务 (或按 Ctrl+C 退出): \n> ")
            if user_input.lower() in ['exit', 'quit']:
                break
            if not user_input.strip():
                continue
            
            run_agent(user_input)
            
        except KeyboardInterrupt:
            print("\n👋 代理已休眠。")
