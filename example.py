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

from yatgl import Client, NationGroup, Template, UserAgent


async def main():
    # Lazy initialization with singleton
    user_agent = UserAgent('nation here', 'yatgl example script', '0.0.1')
    Client(client_key='client key here', user_agent=user_agent)

    # If you want, you can change the delay, like so:
    # Client(delay=200)

    # You can queue telegrams manually...
    Client().queue_tg(Template('secret key', 'tgid'), 'nation here')

    try:
        # ...or you can use a mass telegram function
        await Client().mass_telegram(Template('secret key', 'tgid'), NationGroup.NEW_FOUNDS)

        # or you can use multiple with asyncio.gather e.g.
        # func1 = Client().mass_telegram(Template('secret key', 'tgid'), NationGroup.NEW_FOUNDS)
        # func2 = Client().mass_telegram(Template('secret key', 'tgid'), NationGroup.NEW_REGION_MEMBERS,
        #                                region='testregionia')
        # await asyncio.gather(func1, func2)
    except KeyboardInterrupt:
        await Client().stop()


if __name__ == '__main__':
    asyncio.run(main())
