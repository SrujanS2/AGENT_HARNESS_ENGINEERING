import streamlit as st
import json
import subprocess
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

from agent_harness import validate_command, SYSTEM_PROMPT, TOOLS, state as agent_state

# --- PAGE CONFIG ---
st.set_page_config(page_title="AI Bash Assistant", page_icon="💻", layout="centered")

# --- CUSTOM CSS FOR CHATGPT LOOK ---
st.markdown("""
<style>
    /* Main Background & Text Color */
    .stApp {
        background-color: #212121;
        color: #ececec;
        font-family: Söhne, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, Noto Sans, sans-serif;
    }
    
    /* Hide top header */
    .stApp > header {
        display: none !important;
    }
    
    /* Center the chat and limit width */
    .block-container {
        max-width: 800px !important;
        padding-top: 1rem !important;
        padding-bottom: 6rem !important;
    }
    
    /* Chat Input Container */
    .stChatInputContainer {
        padding-bottom: 20px !important;
        background: transparent !important;
        border: none !important;
    }
    [data-testid="stChatInput"] {
        background-color: #2f2f2f !important;
        border-radius: 26px !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        padding: 5px 15px !important;
    }
    [data-testid="stChatInput"] textarea {
        color: white !important;
        background-color: transparent !important;
    }
    
    /* Hide avatars conditionally if you want, but for now let's style them */
    [data-testid="chatAvatarIcon-assistant"], [data-testid="chatAvatarIcon-user"], [data-testid="chatAvatarIcon-tool"] {
        border-radius: 50% !important;
    }
    
    /* User Message Bubble */
    .stChatMessage.user {
        background-color: #2f2f2f !important;
        border-radius: 18px !important;
        padding: 10px 20px !important;
        margin-left: auto;
        width: fit-content;
        max-width: 80%;
    }
    
    /* Assistant Message */
    .stChatMessage.assistant {
        background-color: transparent !important;
    }
    
    /* Tool/System Message */
    .stChatMessage.tool {
        background-color: #171717 !important;
        border-left: 3px solid #10a37f;
        padding: 10px !important;
        border-radius: 8px !important;
    }

    /* Buttons */
    .stButton>button {
        background-color: #10a37f;
        color: white;
        border: none;
        border-radius: 8px;
        font-weight: 600;
    }
    .stButton>button:hover {
        background-color: #0b8a69;
        color: white;
    }
    
    /* Code blocks */
    pre {
        background-color: #0d0d0d !important;
        border: 1px solid #333 !important;
        border-radius: 8px !important;
    }
    
    /* Hide dividers */
    hr {
        display: none !important;
    }
    
    /* Hide title since ChatGPT has none */
    h1 {
        display: none !important;
    }
</style>
""", unsafe_allow_html=True)

# --- HEADER (Hidden by CSS, but keeping logical structure) ---
st.title("ChatGPT UI - Bash Assistant")

# --- INITIALIZATION ---
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

if "pending_tool_calls" not in st.session_state:
    st.session_state.pending_tool_calls = []

if "awaiting_approval" not in st.session_state:
    st.session_state.awaiting_approval = False

API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = "gpt-4o-mini"

if not API_KEY:
    st.error("⚠️ `OPENAI_API_KEY` is missing! Please set it in your `.env` file or environment.")
    st.stop()

client = OpenAI(api_key=API_KEY)

# --- CHAT HISTORY RENDER ---
for msg in st.session_state.messages:
    if msg["role"] == "system":
        continue
    elif msg["role"] == "assistant":
        if msg.get("content"):
            with st.chat_message("assistant", avatar="🤖"):
                st.markdown(msg["content"])
        if msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                with st.chat_message("assistant", avatar="🛠️"):
                    try:
                        args = json.loads(tc["function"]["arguments"])
                        st.code(f"$ {args.get('command')}", language="bash")
                    except:
                        pass
    elif msg["role"] == "user":
        with st.chat_message("user", avatar="👤"):
            st.markdown(msg["content"])
    elif msg["role"] == "tool":
        with st.chat_message("tool", avatar="⚙️"):
            try:
                res = json.loads(msg["content"])
                if res.get("status") == "SUCCESS":
                    if res.get("stdout"):
                        st.code(res.get("stdout"), language="bash")
                    if res.get("stderr"):
                        st.code(res.get("stderr"), language="bash")
                    if not res.get("stdout") and not res.get("stderr"):
                        st.caption("*(Command executed successfully with no output)*")
                else:
                    st.error(f"**[{res.get('status')}]** {res.get('message')}")
            except:
                st.write(msg["content"])

# --- PROCESS PENDING TOOL CALLS ---
if st.session_state.pending_tool_calls:
    tc = st.session_state.pending_tool_calls[0]
    args = json.loads(tc["function"]["arguments"])
    command = args.get("command", "")
    
    validation, val_msg = validate_command(command)
    
    if validation is False:
        res = {"status": "BLOCKED", "message": val_msg}
        st.session_state.messages.append({
            "role": "tool",
            "tool_call_id": tc["id"],
            "content": json.dumps(res)
        })
        st.session_state.pending_tool_calls.pop(0)
        st.rerun()
        
    elif validation == "APPROVAL_REQUIRED":
        st.session_state.awaiting_approval = True
        
        with st.chat_message("assistant", avatar="🛡️"):
            st.markdown(f"### 🛡️ Harness Approval Required")
            st.warning(f"**Reason:** {val_msg}")
            st.code(command, language="bash")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("✅ Approve", key=f"approve_{tc['id']}", use_container_width=True, type="primary"):
                    try:
                        result = subprocess.run(
                            ["bash", "-c", command], capture_output=True, text=True, timeout=10
                        )
                        res = {
                            "status": "SUCCESS",
                            "command": command,
                            "stdout": result.stdout,
                            "stderr": result.stderr,
                            "return_code": result.returncode
                        }
                        agent_state["last_command"] = command
                        agent_state["commands_executed"].append(command)
                    except subprocess.TimeoutExpired:
                        res = {"status": "ERROR", "message": "Command timed out."}
                    
                    st.session_state.messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(res)
                    })
                    st.session_state.pending_tool_calls.pop(0)
                    st.session_state.awaiting_approval = False
                    st.rerun()
                    
            with col2:
                if st.button("🚫 Reject", key=f"reject_{tc['id']}", use_container_width=True):
                    res = {
                        "status": "REJECTED",
                        "message": "User did not approve the command."
                    }
                    st.session_state.messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(res)
                    })
                    st.session_state.pending_tool_calls.pop(0)
                    st.session_state.awaiting_approval = False
                    st.rerun()
        st.stop()
        
    else:
        # Execute immediately
        try:
            result = subprocess.run(
                ["bash", "-c", command], capture_output=True, text=True, timeout=10
            )
            res = {
                "status": "SUCCESS",
                "command": command,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "return_code": result.returncode
            }
            agent_state["last_command"] = command
            agent_state["commands_executed"].append(command)
        except subprocess.TimeoutExpired:
            res = {"status": "ERROR", "message": "Command timed out."}
        
        st.session_state.messages.append({
            "role": "tool",
            "tool_call_id": tc["id"],
            "content": json.dumps(res)
        })
        st.session_state.pending_tool_calls.pop(0)
        st.rerun()

# --- AUTO-REPLY IF TOOL FINISHED ---
if st.session_state.messages and st.session_state.messages[-1]["role"] == "tool" and not st.session_state.pending_tool_calls:
    with st.spinner("Agent is thinking..."):
        api_messages = []
        for m in st.session_state.messages:
            if m["role"] == "assistant" and "tool_calls" in m:
                api_messages.append({
                    "role": "assistant",
                    "content": m.get("content"),
                    "tool_calls": m["tool_calls"]
                })
            else:
                api_messages.append(m)

        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=api_messages,
                tools=TOOLS,
                tool_choice="auto"
            )
            
            msg = response.choices[0].message
            msg_dict = msg.model_dump(exclude_none=True)
            st.session_state.messages.append(msg_dict)
            
            if msg.tool_calls:
                for tc in msg_dict["tool_calls"]:
                    st.session_state.pending_tool_calls.append(tc)
            
            st.rerun()
        except Exception as e:
            st.error(f"Error communicating with OpenAI: {e}")
            st.stop()

# --- USER INPUT ---
if prompt := st.chat_input("Ask the AI Bash Assistant... (e.g., 'What directory am I in?')"):
    if st.session_state.awaiting_approval:
        st.toast("⚠️ Please approve or reject the pending command first.", icon="⚠️")
    else:
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # Trigger an initial agent response
        with st.spinner("Agent is thinking..."):
            api_messages = []
            for m in st.session_state.messages:
                if m["role"] == "assistant" and "tool_calls" in m:
                    api_messages.append({
                        "role": "assistant",
                        "content": m.get("content"),
                        "tool_calls": m["tool_calls"]
                    })
                else:
                    api_messages.append(m)

            try:
                response = client.chat.completions.create(
                    model=MODEL,
                    messages=api_messages,
                    tools=TOOLS,
                    tool_choice="auto"
                )
                
                msg = response.choices[0].message
                msg_dict = msg.model_dump(exclude_none=True)
                st.session_state.messages.append(msg_dict)
                
                if msg.tool_calls:
                    for tc in msg_dict["tool_calls"]:
                        st.session_state.pending_tool_calls.append(tc)
                
                st.rerun()
            except Exception as e:
                st.error(f"Error communicating with OpenAI: {e}")
                st.stop()
