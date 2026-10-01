import os
import subprocess
import json
from openai import OpenAI


# ============================================================
# 1. LLM
# ============================================================
API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = "gpt-4o-mini"

if API_KEY:
    client = OpenAI(api_key=API_KEY)
else:
    client = None

# ============================================================
# 2. AGENT STATE
# ============================================================

state = {
    "commands_executed": [],
    "last_command": None
}

# ============================================================
# 3. COMMAND SECURITY RULES
# ============================================================

# Commands that the agent is NEVER allowed to execute.

BLOCKED_COMMANDS = {
    "rm",
    "rmdir",
    "shutdown",
    "reboot",
    "mkfs",
    "fdisk",
    "dd",
    "sudo",
    "su"
}


# Commands that are safe for our demo.

ALLOWED_COMMANDS = {
    "pwd",
    "ls",
    "find",
    "grep",
    "cat",
    "head",
    "tail",
    "wc",
    "du",
    "df",
    "whoami",
    "date",
    "echo"
}


# Commands that can modify the environment.
# These require explicit user approval.

MODIFYING_COMMANDS = {
    "mkdir",
    "touch",
    "cp",
    "mv"
}


# ============================================================
# 4. EXTRACT BASE COMMAND
# ============================================================

def get_base_command(command):
    """
    Extract the first command from a shell command.

    Example:

        ls -la

    returns:

        ls
    """

    parts = command.strip().split()

    if not parts:
        return ""

    return parts[0]


# ============================================================
# 5. HARNESS VALIDATION
# ============================================================

def validate_command(command):
    """
    The harness checks the command before Bash executes it.
    """

    command = command.strip()

    if not command:
        return False, "Empty command."

    # --------------------------------------------------------
    # Prevent command chaining
    # --------------------------------------------------------

    dangerous_operators = [
        ";",
        "&&",
        "||",
        "|",
        ">",
        ">>"
    ]

    for operator in dangerous_operators:

        if operator in command:

            return (
                False,
                f"Shell operator '{operator}' is not allowed."
            )


    # --------------------------------------------------------
    # Get command name
    # --------------------------------------------------------

    base_command = get_base_command(command)


    # --------------------------------------------------------
    # Block dangerous commands
    # --------------------------------------------------------

    if base_command in BLOCKED_COMMANDS:

        return (
            False,
            f"Command '{base_command}' is blocked by the harness."
        )


    # --------------------------------------------------------
    # Allow read-only commands
    # --------------------------------------------------------

    if base_command in ALLOWED_COMMANDS:

        return True, "Read-only command approved."


    # --------------------------------------------------------
    # Modifying commands require approval
    # --------------------------------------------------------

    if base_command in MODIFYING_COMMANDS:

        return (
            "APPROVAL_REQUIRED",
            f"Command '{base_command}' modifies the filesystem."
        )


    # --------------------------------------------------------
    # Unknown commands
    # --------------------------------------------------------

    return (
        False,
        f"Command '{base_command}' is not in the allowed command list."
    )


# ============================================================
# 6. BASH TOOL
# ============================================================

def execute_bash(command):
    """
    Execute a Bash command after passing through
    the Agent Harness.
    """

    validation, message = validate_command(command)


    # --------------------------------------------------------
    # Command blocked
    # --------------------------------------------------------

    if validation is False:

        return {
            "status": "BLOCKED",
            "message": message
        }


    # --------------------------------------------------------
    # Command needs approval
    # --------------------------------------------------------

    if validation == "APPROVAL_REQUIRED":

        print("\n" + "=" * 60)
        print("HARNESS: APPROVAL REQUIRED")
        print("=" * 60)

        print(f"\nCommand:")
        print(command)

        print(f"\nReason:")
        print(message)

        answer = input("\nAllow this command? (yes/no): ")

        if answer.lower() != "yes":

            return {
                "status": "REJECTED",
                "message": "User did not approve the command."
            }


    # --------------------------------------------------------
    # Execute command
    # --------------------------------------------------------

    try:

        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=10
        )


        # Save execution state

        state["last_command"] = command

        state["commands_executed"].append(command)


        return {
            "status": "SUCCESS",
            "command": command,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.returncode
        }


    except subprocess.TimeoutExpired:

        return {
            "status": "ERROR",
            "message": "Command timed out."
        }


# ============================================================
# 7. TOOL DEFINITIONS FOR LLM
# ============================================================

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "execute_bash",
            "description": (
                "Execute a Bash command through the safety harness. "
                "Only use this when a shell command is necessary."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": (
                            "The Bash command to execute."
                        )
                    }
                },
                "required": ["command"]
            }
        }
    }
]


# ============================================================
# 8. SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
You are a beginner-friendly AI Bash Assistant.

Your job is to help the user inspect and manage files
using Bash commands.

You have one tool:

execute_bash(command)

Important rules:

1. Use Bash only when necessary.

2. Prefer simple read-only commands such as:
   pwd
   ls
   find
   grep
   cat
   head
   tail
   wc
   du
   df
   whoami
   date

3. Never try to bypass the harness.

4. Never construct commands using:
   sudo
   rm
   shutdown
   reboot
   mkfs
   fdisk
   dd

5. Do not use shell chaining such as:
   ;
   &&
   ||
   |
   >
   >>

6. If a command modifies files, the harness will ask the
   user for approval.

7. Do not claim that a command was executed unless the
   tool actually returned SUCCESS.

8. Explain the result in simple language.
"""


# ============================================================
# 9. AGENT LOOP
# ============================================================

def run_agent(user_message):

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
        },
        {
            "role": "user",
            "content": user_message
        }
    ]


    while True:

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto"
        )


        assistant_message = response.choices[0].message


        # ----------------------------------------------------
        # No tool call
        # ----------------------------------------------------

        if not assistant_message.tool_calls:

            return assistant_message.content


        # ----------------------------------------------------
        # Add assistant message to conversation
        # ----------------------------------------------------

        messages.append(assistant_message)


        # ----------------------------------------------------
        # Process tool calls
        # ----------------------------------------------------

        for tool_call in assistant_message.tool_calls:

            tool_name = tool_call.function.name

            arguments = json.loads(
                tool_call.function.arguments
            )


            if tool_name == "execute_bash":

                command = arguments["command"]

                print("\nAgent wants to execute:")
                print(f"  $ {command}")


                result = execute_bash(command)


                print("\nHarness result:")
                print(result)


                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps(result)
                    }
                )


# ============================================================
# 10. MAIN CHAT LOOP
# ============================================================

def main():

    if client is None:
        print("Harness ready. Set OPENAI_API_KEY before using the LLM client.")
        return

    print("=" * 60)
    print("        AI BASH ASSISTANT")
    print("        Agent Harness Engineering Demo")
    print("=" * 60)

    print("""
Try:

  What directory am I in?

  Show me the files in this directory.

  How much disk space is available?

  Find Python files.

  Show me the first 10 lines of main.py.

  Create a folder called demo.

  Delete everything in this directory.

Type 'exit' to quit.
""")


    while True:

        user_input = input("\nYou: ")

        if user_input.lower() == "exit":

            print("\nGoodbye!")
            break


        try:

            answer = run_agent(user_input)

            print("\nAgent:")
            print(answer)


        except Exception as e:

            print("\nError:")
            print(e)


# ============================================================
# 11. PROGRAM ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()