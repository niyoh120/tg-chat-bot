import logging
from revChatGPT.V1 import AsyncChatbot, log
import pydantic as pyd

log.setLevel(logging.DEBUG)

class Config(pyd.BaseSettings):
    access_token:str
    class Config:
        env_file = '.env'
        env_prefix = "chatgpt_"

config = Config()
chatbot = AsyncChatbot(config=config.dict())