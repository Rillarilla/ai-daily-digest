import time
from google.oauth2 import service_account
from google import genai
from google.genai import types


SERVICE_ACCOUNT_FILE = r'./transsion-sw-cd-6610d5d50199.json'
SCOPES = ['https://www.googleapis.com/auth/cloud-platform']

credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=SCOPES
)

client = genai.Client(
    vertexai=True,
    project="transsion-sw-cd",
    location="global",
    credentials=credentials
)


def call_gemini(
    prompt: str,
    model_name: str = "gemini-3.1-pro-preview",
    temperature: float = 0.0,
    max_output_tokens: int = 10000,
    thinking_budget: int = -1,
    stop: list[str] | None = None,
) -> str:
    content = types.Content(
        role="user",
        parts=[types.Part(text=prompt)]
    )

    config = types.GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        thinking_config=types.ThinkingConfig(thinking_budget=thinking_budget),
        safety_settings=[
            types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
            types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF"),
        ],
        stop_sequences=stop,
    )

    response = client.models.generate_content(
        model=model_name,
        contents=[content],
        config=config,
    )

    if response and response.prompt_feedback and response.prompt_feedback.block_reason:
        text = f"模型响应被拦截：{response.prompt_feedback.block_reason}"
        if response.prompt_feedback.block_message:
            text += f"，原因：{response.prompt_feedback.block_message}"
    elif not response or not response.candidates:
        text = "模型未生成有效响应"
    else:
        candidate = response.candidates[0]
        if candidate.content and candidate.content.parts:
            part_text = candidate.content.parts[0].text
            text = part_text.strip() if part_text else "生成内容为空"
        else:
            text = "生成内容为空"

    return text if text.strip() else "生成内容为空"


if __name__ == '__main__':
    prompt = r"我需要多组特殊的数据。初始数据为1，2，0，7，下一组在上一组的基础上所有数字加1，下一组应该是2,3,1,8。以此类推，帮我生成102组"

    start = time.time()
    result = call_gemini(prompt)
    print(result)
    print(f"耗时：{time.time() - start:.2f}s，输入长度：{len(prompt)}，输出长度：{len(result)}")