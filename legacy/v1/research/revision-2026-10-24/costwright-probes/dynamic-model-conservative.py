from langchain_openai import ChatOpenAI
model_name = "gpt-5"
client = ChatOpenAI(model=model_name, max_tokens=16)
