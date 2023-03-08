from revChatGPT.V1 import AsyncChatbot, Chatbot
import pydantic as pyd

class Config(pyd.BaseSettings):
    access_token:str
    class Config:
        env_file = '.env'
        env_prefix = "chatgpt_"

config = Config()

def new_async_bot():
    return AsyncChatbot(config=config.dict())

def new_bot():
    return Chatbot(config=config.dict())