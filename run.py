"""
Actually runs the code
"""
from bot import Discordoragi
from cogs import Search


def run():
    bot = Discordoragi()
    cogs = [
      Search(bot)
    ]
    bot.start_bot(cogs)


if __name__ == '__main__':
    run()
