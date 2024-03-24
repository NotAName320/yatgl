"""
YATGL client
Copyright (C) 2024 Nota

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import asyncio
from logging import getLogger
from collections import deque
from typing import NamedTuple

import aiohttp


logger = getLogger(__name__)


class Template(NamedTuple):
    secret_key: str
    tgid: str


class TelegramRequest(NamedTuple):
    template: Template
    recipient: str


class _ClientMeta(type):
    """
    Singleton metaclass for Client, making sure that two action queues never exist at once

    Not meant to be externally instantiated.
    """
    _instance = None

    def __call__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(_ClientMeta, cls).__call__(*args, **kwargs)
        else:
            cls._instance.__init__(*args, **kwargs)
        return cls._instance


class Client(metaclass=_ClientMeta):
    """
    A telegram client. This is a singleton object, meaning assigning it to a variable and calling its bare constructor
    every time you want to use it is functionally identical.

    Must be instantiated with a client key to work.

    >>>Client(client_key='client key here')

    >>>temp = Template(secret_key='secret key here', tgid='telegram id here')

    >>>Client().queue_tg(temp, recipient='nation here')

    >>>asyncio.run(Client().start())
    """
    client_key: str = None
    delay: int = 185
    sent = set()
    queue: deque[TelegramRequest] = deque()
    _task = None
    _session: aiohttp.ClientSession

    def __init__(self, **kwargs):
        """
        Change attributes of the Singleton.

        Note that while you can send the delay for a telegram less than 180 seconds, it's your responsibility not to do
        this for recruitment telegrams.
        """
        if 'client_key' in kwargs:
            self.client_key = kwargs.pop('client_key')
        if 'delay' in kwargs:
            delay = kwargs.pop('delay')
            if delay < 30:
                raise ValueError('Delay can\'t be less than 180.')
            self.delay = delay

    def queue_tg(self, template: Template, recipient: str):
        """
        Enqueues a telegram template with a recipient.
        :param template: The telegram template.
        :param recipient: The nation you want to recieve the telegram.
        """
        self.queue.appendleft(TelegramRequest(template, recipient))

    async def start(self):
        """
        Starts sending telegrams if the client has stopped, otherwise does nothing.

        Ensure that a client key has been provided.
        """
        if not self.client_key:
            raise AttributeError('No client key provided.')
        if not self._task:
            self._task = asyncio.create_task(self._process_stack())
            self._session = aiohttp.ClientSession()
            await self._task

    async def stop(self):
        """
        Stops sending telegrams if the client has started, otherwise does nothing.
        """
        if self._task:
            self._task.cancel()
            await self._session.close()
            self._task = None

    async def _process_stack(self):
        while True:
            if self.queue:
                await self._send_tg(self.queue.pop())
                await asyncio.sleep(self.delay)
            # so it doesn't block our async queue
            await asyncio.sleep(0)

    async def _send_tg(self, telegram: TelegramRequest):
        recipient = telegram.recipient.lower().replace(' ', '_')
        data = {
            'a': 'sendTG',
            'client': self.client_key,
            'tgid': telegram.template.tgid,
            'key': telegram.template.secret_key,
            'to': recipient
        }
        async with self._session.post('https://www.nationstates.net/cgi-bin/api.cgi', data=data) as resp:
            if await resp.text() == 'queued':
                self.sent.add(recipient)
                logger.info(f'Sent {telegram.template.tgid} to {telegram.recipient}')
            else:
                logger.error(f'Telegram errored sending {telegram.template.tgid} to {telegram.recipient}:'
                             f'{await resp.text()}')
