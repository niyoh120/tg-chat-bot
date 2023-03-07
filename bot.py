import html
import json
import logging
import traceback

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import filters, ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler
import pydantic as pyd
import httpx

import chatgpt

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__file__)

class Config(pyd.BaseSettings):
    bot_token:str

    class Config:
        env_file = ".env"
        env_prefix = "telegram_"
    
config = Config()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.effective_chat
    await context.bot.send_message(chat_id=update.effective_chat.id, text="I'm a chatgpt bot, please talk to me!")

async def list_conversations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.effective_chat
    try:
        text = await chatgpt.chatbot.get_conversations()
    except httpx.HTTPError as e:
        text = str(e)
    if not text:
        text = "no conversation"
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text)

async def clear_conversations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.effective_chat
    try:
        await chatgpt.chatbot.clear_conversations()
    except httpx.HTTPError as e:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=str(e))

async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.message
    assert update.effective_chat
    prompt = update.message.text
    if prompt is None:
        return
    text = ""
    try:
        async for resp in chatgpt.chatbot.ask(prompt):
            text = resp["data"]
    except httpx.HTTPStatusError as e:
        text = str(e)
    if not text:
        text = "no answer"
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text)

DEVELOPER_CHAT_ID = 123456

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    # Log the error before we do anything else, so we can see it even if something breaks.
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

    # traceback.format_exception returns the usual python message about an exception, but as a
    # list of strings rather than a single string, so we have to join them together.
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    # Build the message with some markup and additional information about what happened.
    # You might need to add some logic to deal with messages longer than the 4096 character limit.
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        f"An exception was raised while handling an update\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
        "</pre>\n\n"
        f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
        f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )

    # # Finally, send the message
    # await context.bot.send_message(
    #     chat_id=DEVELOPER_CHAT_ID, text=message, parse_mode=ParseMode.HTML
    # )

if __name__ == '__main__':
    logger.info(f"bot config: {config.dict()}")
    logger.info(f"chatgpt config: {chatgpt.config.dict()}")

    application = ApplicationBuilder().token(config.bot_token).build()
    
    start_handler = CommandHandler('start', start)
    list_handler = CommandHandler("list", list_conversations)
    clear_handler = CommandHandler("clear", clear_conversations)
    ask_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), ask)

    application.add_handlers([start_handler, list_handler, clear_handler, ask_handler])
    application.add_error_handler(error_handler)
    
    application.run_polling()