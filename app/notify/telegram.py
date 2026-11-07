from dataclasses import dataclass
from typing import Protocol

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

Button = tuple[str, str]
Keyboard = list[list[Button]]


@dataclass
class Outgoing:
    text: str
    keyboard: Keyboard | None = None


class Notifier(Protocol):
    async def send(self, text: str, keyboard: Keyboard | None = None) -> None: ...
    async def send_audio(self, audio: bytes, title: str) -> None: ...


def to_markup(keyboard: Keyboard | None) -> InlineKeyboardMarkup | None:
    if keyboard is None:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=data) for label, data in row]
            for row in keyboard
        ]
    )


class TelegramNotifier:
    def __init__(self, token: str, chat_id: int):
        self.bot = Bot(token=token)
        self.chat_id = chat_id

    async def send(self, text: str, keyboard: Keyboard | None = None) -> None:
        await self.bot.send_message(
            chat_id=self.chat_id,
            text=text,
            reply_markup=to_markup(keyboard),
        )

    async def send_audio(self, audio: bytes, title: str) -> None:
        await self.bot.send_audio(
            chat_id=self.chat_id,
            audio=audio,
            title=title,
        )
