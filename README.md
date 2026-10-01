# AI Bash Assistant

An AI-powered Bash Assistant built with Python, Streamlit, and OpenAI. It executes read-only bash commands securely and features a safety harness that intercepts modifying commands (like `mkdir`, `cp`, `mv`) to require explicit user approval. This prevents accidental filesystem modifications while maintaining a fluid conversational interface.

## Features
- **Secure Execution**: Whitelists safe, read-only commands for automatic execution.
- **Approval Harness**: Intercepts state-modifying commands and waits for explicit user authorization.
- **Cross-Platform Compatibility**: Executes commands cleanly through `bash -c`, enabling operation across different OS environments.
- **ChatGPT-like UI**: A beautiful chat interface built entirely with Streamlit and custom CSS.

## Setup Instructions

1. **Set up the virtual environment**
```bash
python -m venv venv

# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Configure Environment Variables**  
Create a `.env` file in the root directory and add your OpenAI API Key:
```env
OPENAI_API_KEY=your-api-key-here
```

4. **Run the Application**
```bash
streamlit run app.py
```
