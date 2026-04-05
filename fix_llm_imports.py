import os

files = ['src/llm_service.py', 'src/summary_generator.py']

for file in files:
    with open(f"/root/Culture-Calendar/{file}", "r") as f:
        content = f.read()
    
    # Simple replace - anthropic -> openai
    content = content.replace('from anthropic import Anthropic', 'from openai import OpenAI')
    content = content.replace('self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")', 'self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")')
    content = content.replace('ANTHROPIC_API_KEY not found', 'OPENROUTER_API_KEY not found')
    content = content.replace('Anthropic(api_key=self.anthropic_api_key)', 'OpenAI(base_url="https://openrouter.ai/api/v1", api_key=self.openrouter_api_key)')
    content = content.replace('self.anthropic =', 'self.openai =')
    content = content.replace('if self.anthropic_api_key', 'if self.openrouter_api_key')
    content = content.replace('if not self.anthropic:', 'if not self.openai:')
    content = content.replace('self.anthropic.messages.create(', 'self.openai.chat.completions.create(')
    content = content.replace('system=system_prompt,', '')
    content = content.replace('messages=[', 'messages=[{"role": "system", "content": system_prompt},')
    content = content.replace('model="claude-3-5-sonnet-20241022"', 'model="anthropic/claude-3.5-sonnet"')
    content = content.replace('self.client = Anthropic(api_key=self.anthropic_api_key)', 'self.client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=self.openrouter_api_key)')
    
    with open(f"/root/Culture-Calendar/{file}", "w") as f:
        f.write(content)

print("Done replacing.")
