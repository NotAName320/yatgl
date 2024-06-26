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
from collections import deque
from collections.abc import Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from enum import Enum
from logging import getLogger
from typing import NamedTuple

import aiohttp
from bs4 import BeautifulSoup

API_URL = 'https://www.nationstates.net/cgi-bin/api.cgi'
VERSION = '1.0.6'


logger = getLogger(__name__)


class Template(NamedTuple):
    secret_key: str
    tgid: str


class TelegramRequest(NamedTuple):
    template: Template
    recipient: str


@dataclass
class UserAgent:
    nation_name: str
    script_name: str
    script_version: str

    def __str__(self):
        return (f'yatgl v{VERSION} Developed by nation=Notanam, used by nation={self.nation_name} in '
                f'script={self.script_name} v{self.script_version}')


class NationGroup(Enum):
    NEW_WA_MEMBERS = 0
    ALL_WA_MEMBERS = 1
    NEW_FOUNDS = 2
    ALL_WA_DELEGATES = 3
    NEW_REGION_MEMBERS = 4
    ALL_REGION_MEMBERS = 5
    DELEGATES_APPROVING = 7
    DELEGATES_NOT_APPROVING = 9


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
    user_agent: UserAgent = None
    delay: int = 185
    sent = set()
    queue: deque[TelegramRequest] = deque()
    _tg_task = None
    _queueing_tasks = []
    _session: aiohttp.ClientSession = None

    def __init__(self, **kwargs):
        """
        Change attributes of the Singleton.

        Note that while you can send the delay for a telegram less than 180 seconds, it's your responsibility not to do
        this for recruitment telegrams.
        """
        if 'client_key' in kwargs:
            self.client_key = kwargs.pop('client_key')
        if 'user_agent' in kwargs:
            self.user_agent = kwargs.pop('user_agent')
            if self._session:
                self._session.headers['User-Agent'] = str(self.user_agent)
        if 'delay' in kwargs:
            delay = kwargs.pop('delay')
            if delay < 30:
                raise ValueError('Delay can\'t be less than 30.')
            self.delay = delay

    def queue_tg(self, template: Template, recipient: str):
        """
        Enqueues a telegram template with a recipient.
        :param template: The telegram template.
        :param recipient: The nation you want to recieve the telegram.
        """
        self.queue.appendleft(TelegramRequest(template, recipient))
        logger.debug(f'queued {template.tgid} to {recipient}')

    async def start(self):
        """
        Starts sending telegrams if the client has stopped, otherwise does nothing.

        Ensure that a client key has been provided.
        """
        if not self.client_key:
            raise AttributeError('No client key provided.')
        if not self.user_agent:
            raise AttributeError('Please set a User Agent.')
        if not self._tg_task:
            self._tg_task = asyncio.create_task(self._process_queue())
            if not self._session or self._session.closed:
                headers = {
                    'User-Agent': str(self.user_agent)
                }
                self._session = aiohttp.ClientSession(headers=headers)
            await self._tg_task

    async def stop(self):
        """
        Stops sending telegrams and/or queueing if the client has started, otherwise does nothing.
        """
        if self._tg_task:
            self._tg_task.cancel()
            for task in self._queueing_tasks:
                task.cancel()
            await self._session.close()
            self._tg_task, self._queueing_tasks = None, []

    async def mass_telegram(self, template: Template, group: NationGroup, *, regions: str | Iterable[str] = None,
                            proposal: str = None):
        """
        Starts the telegram queue while autoqueueing a certain group of nations using the API.

        Ensure that a client key has been provided.
        :param template: The template to send to the nations.
        :param group: The group of nations to target specified by the enum :class:`NationGroup`.
        :param regions: A list of regions.
        :param proposal: A proposal ID.
        """
        if not self._session or self._session.closed:
            headers = {
                'User-Agent': str(self.user_agent)
            }
            self._session = aiohttp.ClientSession(headers=headers)
        task = asyncio.create_task(self._mass_queue(template, group, regions, proposal))
        self._queueing_tasks.append(task)
        await asyncio.gather(self.start(), task)

    async def _mass_queue(self, template: Template, group: NationGroup, regions: str | Iterable[str] | None,
                          proposal: str | None):
        if group in {NationGroup.DELEGATES_APPROVING, NationGroup.DELEGATES_NOT_APPROVING} and not proposal:
            raise AttributeError('Proposal ID not provided to client.')
        if group in {NationGroup.ALL_REGION_MEMBERS, NationGroup.NEW_REGION_MEMBERS} and not regions:
            raise AttributeError('Region(s) not provided to client.')
        elif isinstance(regions, str):
            regions = [regions]

        # why did i code it like this?
        if group.value % 2 == 1:
            # here's where i throw good software principles out the book in favor of huge ass switch statements
            match group:
                case NationGroup.ALL_REGION_MEMBERS:
                    for region in regions:
                        for nation in await self._get_region_members(region):
                            self.queue_tg(template, nation)

                case NationGroup.ALL_WA_MEMBERS:
                    for nation in await self._get_wa_members():
                        self.queue_tg(template, nation)

                case NationGroup.ALL_WA_DELEGATES:
                    for nation in await self._get_wa_delegates():
                        self.queue_tg(template, nation)

                case NationGroup.DELEGATES_APPROVING:
                    for nation in await self._get_proposal_delegates_approving(proposal):
                        self.queue_tg(template, nation)

                case NationGroup.DELEGATES_NOT_APPROVING:
                    all_delegates_approving = set(await self._get_proposal_delegates_approving(proposal))
                    for nation in await self._get_wa_delegates():
                        if nation not in all_delegates_approving:
                            self.queue_tg(template, nation)
        else:
            # generate a list of nations to not send messages to
            existing = set()
            if group is NationGroup.NEW_REGION_MEMBERS:
                for region in regions:
                    existing.update(await self._get_region_members(region))
            elif group is NationGroup.NEW_WA_MEMBERS:
                existing = set(await self._get_wa_members())

            while True:
                match group:
                    case NationGroup.NEW_REGION_MEMBERS:
                        for region in regions:
                            for nation in await self._get_region_members(region):
                                if nation not in existing:
                                    self.queue_tg(template, nation)
                                    existing.add(nation)

                    case NationGroup.NEW_WA_MEMBERS:
                        for member in await self._get_wa_members():
                            if member not in existing:
                                self.queue_tg(template, member)
                                existing.add(member)

                    case NationGroup.NEW_FOUNDS:
                        for nation in await self._get_new_founds():
                            if nation not in existing:
                                self.queue_tg(template, nation)
                                existing.add(nation)

                await asyncio.sleep(60)

    async def _get_region_members(self, region: str) -> list[str]:
        data = {
            'q': 'nations',
            'region': region
        }

        async with self._api_request_wait(API_URL, data=data) as resp:
            parsed = BeautifulSoup(await resp.text(), 'xml')
            return parsed.REGION.NATIONS.string.split(':')

    async def _get_wa_members(self) -> list[str]:
        data = {
            'q': 'members',
            'wa': '1'
        }

        async with self._api_request_wait(API_URL, data=data) as resp:
            parsed = BeautifulSoup(await resp.text(), 'xml')
            return parsed.WA.MEMBERS.string.split(',')

    async def _get_wa_delegates(self) -> list[str]:
        data = {
            'q': 'delegates',
            'wa': '1'
        }

        async with self._api_request_wait(API_URL, data=data) as resp:
            parsed = BeautifulSoup(await resp.text(), 'xml')
            return parsed.WA.DELEGATES.string.split(',')

    async def _get_new_founds(self) -> list[str]:
        data = {
            'q': 'newnations'
        }

        async with self._api_request_wait(API_URL, data=data) as resp:
            parsed = BeautifulSoup(await resp.text(), 'xml')
            return parsed.WORLD.NEWNATIONS.string.split(',')

    async def _get_proposal_delegates_approving(self, proposal: str, council='1') -> list[str]:
        data = {
            'q': 'proposals',
            'wa': council
        }

        async with self._api_request_wait(API_URL, data=data) as resp:
            parsed = BeautifulSoup(await resp.text(), 'xml')
            proposal_xml = parsed.find(id=proposal)
            if proposal_xml:
                return proposal_xml.APPROVALS.string.split(':')

        if council == '1':
            return await self._get_proposal_delegates_approving(proposal, '2')
        else:
            return []

    @asynccontextmanager
    async def _api_request_wait(self, url: str, data: dict):
        while True:
            async with self._session.post(url, data=data) as resp:
                if resp.status == 429:
                    retry_after = int(resp.headers['Retry-After'])
                    logger.warning(f'Hit normal API rate limit! Retrying in {retry_after}...')
                    await asyncio.sleep(retry_after)
                else:
                    if remaining := int(resp.headers['RateLimit-Remaining']) <= 7:
                        logger.info('Getting close to rate limit, slowing down requests a bit...')
                        await asyncio.sleep(int(resp.headers['RateLimit-Reset']) / remaining)
                    yield resp
                    break

    async def _process_queue(self):
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

        while True:
            async with self._session.post(API_URL, data=data) as resp:
                if resp.status == 429:
                    retry_after = int(resp.headers['Retry-After'])
                    logger.warning(f'Got too many requests error from NationStates sending {telegram.template.tgid} to '
                                   f'{recipient}! Retrying in {retry_after}s')
                    await asyncio.sleep(retry_after)
                elif 'queued' in await resp.text():
                    self.sent.add(recipient)
                    logger.info(f'Sent {telegram.template.tgid} to {telegram.recipient}')
                    break
                else:
                    logger.error(f'Telegram errored sending {telegram.template.tgid} to {telegram.recipient}:'
                                 f'{await resp.text()}')
                    break
