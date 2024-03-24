"""
YATGL sample code
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

from yatgl import Client, Template


async def add_some_tgs():
    while True:
        print('inserted 3 more telegrams into queue')
        Client().queue_tg(Template('secret key', 'tgid'), '1')
        Client().queue_tg(Template('secret key', 'tgid'), '2')
        Client().queue_tg(Template('secret key', 'tgid'), '3')
        await asyncio.sleep(500)


async def main():
    # Lazy initialization with singleton
    Client(client_key='client key here')

    # If you want, you can change the delay, like so:
    # Client(delay=200)

    # Queue some telegrams
    Client().queue_tg(Template('secret key', 'tgid'), 'nation here')
    Client().queue_tg(Template('secret key', 'tgid'), 'nation here')

    try:
        await asyncio.gather(Client().start(), add_some_tgs())
    except KeyboardInterrupt:
        await Client().stop()


if __name__ == '__main__':
    asyncio.run(main())
