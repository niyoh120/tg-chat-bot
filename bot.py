import html
import json
import logging
import traceback
import functools as ft
import asyncio

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    filters,
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    PicklePersistence,
)
import pydantic as pyd
import httpx

from dotenv import load_dotenv

load_dotenv()

import chatgpt

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

logger = logging.getLogger(__file__)


class Config(pyd.BaseSettings):
    bot_token: str

    class Config:
        env_file = ".env"
        env_prefix = "telegram_"


config = Config()


def log(fn):
    ft.wraps(fn)

    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.info(f"update: {update.to_json()}")
        logger.info(f"bot_data: {context.bot_data}")
        logger.info(f"chat_data: {context.chat_data}")
        logger.info(f"user_data: {context.user_data}")
        return await fn(update, context)

    return wrapper


STATE_CHATTING = 1


@log
async def begin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.effective_chat is not None
    await context.bot.send_message(chat_id=update.effective_chat.id, text="让我们开始一次新的聊天")
    return STATE_CHATTING


@log
async def end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.effective_chat is not None
    assert context.user_data is not None
    context.user_data.clear()
    await context.bot.send_message(chat_id=update.effective_chat.id, text="下次再会")
    return ConversationHandler.END


@log
async def timeout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.effective_chat is not None
    assert context.user_data is not None
    context.user_data.clear()
    await context.bot.send_message(
        chat_id=update.effective_chat.id, text="会话已超时, 请重新开始一次新的聊天"
    )
    return ConversationHandler.END


@log
async def list_conversations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.effective_chat is not None
    text = "没有历史聊天记录"
    try:
        choices = await asyncio.to_thread(chatgpt.new_bot().get_conversations)
        if len(choices) > 0:
            text = str(choices)
    except httpx.HTTPError as e:
        text = str(e)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text)


# async def select_conversation(update:Update, context: ContextTypes.DEFAULT_TYPE):
#     assert update.effective_chat
#     text = ""
#     try:
#         choices = await chatgpt.new_async_bot().get_conversations()
#         if len(choices) < 1:
#             text = "没有历史聊天记录"
#     except httpx.HTTPError as e:
#         text = str(e)
#     await context.bot.send_message(chat_id=update.effective_chat.id, text=text)


@log
async def clear_conversations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.effective_chat is not None
    assert context.user_data is not None

    text = "清理所有历史聊天记录成功"
    try:
        await asyncio.to_thread(chatgpt.new_bot().clear_conversations)
        context.user_data.clear()
    except httpx.HTTPError as e:
        text = str(e)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text)


def get_answer(prompt, conversation_id, parent_id):
    chatgpt_bot = chatgpt.new_bot()
    text = ""
    for resp in chatgpt_bot.ask(
        prompt,
        conversation_id=conversation_id,
        parent_id=parent_id,
    ):
        text = resp["message"]
    return text, chatgpt_bot.conversation_id, chatgpt_bot.parent_id


@log
async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE):
    assert update.message is not None
    assert update.effective_chat is not None
    prompt = update.message.text
    if prompt is None or prompt.strip() == "":
        return
    assert context.user_data is not None

    text = "没有回复"
    conversation_id = context.user_data.get("chatgpt_conversation_id", None)
    parent_id = context.user_data.get("chatgpt_parent_id", None)

    try:
        text, conversation_id, parent_id = await asyncio.to_thread(
            get_answer, prompt, conversation_id, parent_id
        )
        context.user_data["chatgpt_conversation_id"] = conversation_id
        context.user_data["chatgpt_parent_id"] = parent_id
    except httpx.HTTPStatusError as e:
        text = str(e)
    await update.message.reply_text(text)
    return STATE_CHATTING


DEVELOPER_CHAT_ID = 123456


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    # Log the error before we do anything else, so we can see it even if something breaks.
    logger.error(msg="Exception while handling an update:", exc_info=context.error)

    # traceback.format_exception returns the usual python message about an exception, but as a
    # list of strings rather than a single string, so we have to join them together.
    tb_list = traceback.format_exception(
        None, context.error, context.error.__traceback__
    )
    tb_string = "".join(tb_list)

    # Build the message with some markup and additional information about what happened.
    # You might need to add some logic to deal with messages longer than the 4096 character limit.
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        "An exception was raised while handling an update\n"
        "<pre>update ="
        f" {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
        "</pre>\n\n"
        f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
        f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )

    # # Finally, send the message
    # await context.bot.send_message(
    #     chat_id=DEVELOPER_CHAT_ID, text=message, parse_mode=ParseMode.HTML
    # )


if __name__ == "__main__":
    logger.info(f"bot config: {config.dict()}")
    logger.info(f"chatgpt config: {chatgpt.config.dict()}")

    persistence = PicklePersistence(filepath="data")
    application = (
        ApplicationBuilder().token(config.bot_token).persistence(persistence).build()
    )

    converstation_handler = ConversationHandler(
        entry_points=[CommandHandler("begin", begin)],  # type: ignore
        states={
            STATE_CHATTING: [MessageHandler(filters.TEXT & (~filters.COMMAND), ask)],
            ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, end)],
        },  # type: ignore
        fallbacks=[CommandHandler("end", end)],  # type: ignore
    )
    list_handler = CommandHandler("list", list_conversations)
    clear_handler = CommandHandler("clear", clear_conversations)

    application.add_handlers([converstation_handler, list_handler, clear_handler])
    application.add_error_handler(error_handler)

    application.run_polling()
