"""
A cog that handles searching for anime/manga/ln found
in brackets.
"""
from enum import Enum
from discord import Embed
from minoshiro import Medium, Minoshiro, Site
import asyncio
import re


class Replace(Enum):
    MAL = 1
    AL = 2
    AP = 3
    ANIDB = 4
    KITSU = 5
    MU = 6
    LNDB = 7
    NU = 8
    VNDB = 9


def clean_message(message) -> str:
    """
    Returns a message, but stripped of all code markup and emojis
    Uses regex to parse
    :param message: a message string
    :returns: message string - code markup and emojis
    """
    no_multi_codeblocks = re.sub(
        r"^`{3}([\S]+)?\n([\s\S]+)\n`{3}", "", message.clean_content)
    no_single_codeblocks = re.sub(r"\`(.*\s?)\`", "", no_multi_codeblocks)
    no_emojis = re.sub(r'<:.+?:([0-9]{15,21})>', "", no_single_codeblocks)
    return no_emojis


def get_all_searches(message, expanded_allowed):
    matches = 0
    for match in re.finditer(
            "\{{2}([^}]*)\}{2}|\<{2}([^>]*)\>{2}|\]{2}([^]]*)\[{2}",
            message, re.S):
        matches += 1
        if matches > 1:
            expanded_allowed = False
        if '<<' in match.group(0):
            cleaned_search = re.sub(r"\<{2}|\>{2}", "", match.group(0))
            yield {
                'medium':  Medium.MANGA,
                'search': cleaned_search,
                'expanded': expanded_allowed}
        if '{{' in match.group(0):
            cleaned_search = re.sub(r"\{{2}|\}{2}", "", match.group(0))
            yield {
                'medium': Medium.ANIME,
                'search': cleaned_search,
                'expanded': expanded_allowed}
        if ']]' in match.group(0):
            cleaned_search = re.sub(r"\]{2}|\[{2}", "", match.group(0))
            yield {
                'medium': Medium.LN,
                'search': cleaned_search,
                'expanded': expanded_allowed}

        message = re.sub(re.escape(match.group(0)), "", message)

    for match in re.finditer("\{([^{}]*)\}|\<([^<>]*)\>|\]([^[\]]*)\[",
                             message, re.S):
        if '<' in match.group(0):
            cleaned_search = re.sub(r"\<|\>", "", match.group(0))
            yield {
                'medium': Medium.MANGA,
                'search': cleaned_search,
                'expanded': False}
        if '{' in match.group(0):
            cleaned_search = re.sub(r"\{|\}", "", match.group(0))
            yield {
                'medium': Medium.ANIME,
                'search': cleaned_search,
                'expanded': False}
        if ']' in match.group(0):
            cleaned_search = re.sub(r"\]|\[", "", match.group(0))
            yield {
                'medium': Medium.LN,
                'search': cleaned_search,
                'expanded': False}
    return


def get_response_dict(entry_info, medium):
    assert (Site.MAL in entry_info.keys() or
            Site.ANILIST in entry_info.keys()),\
        "Entry must have either mal or anilist responses"
    resp_dict = {}
    resp_dict['info'] = {}
    url_string = ''
    genre_string = ''
    resp_dict['title'] = entry_info[Site.MAL]['title'] if entry_info[Site.MAL]\
        else entry_info[Site.ANILIST]['title']['romaji']
    resp_dict['info']['medium'] = (medium.name).title()
    resp_dict['synopsis'] = entry_info[Site.MAL]['synopsis']\
        if entry_info[Site.MAL] else entry_info[Site.ANILIST]['description']
    for key in entry_info.keys():
        if entry_info[key]['url']:
            url_string += f'[{Replace(key.value).name}]'\
                          f'({entry_info[key]["url"]}), '
    resp_dict['links'] = url_string.strip(', ')
    if entry_info[Site.ANILIST] and entry_info[Site.ANILIST]['genres']:
        for genre in entry_info[Site.ANILIST]['genres']:
            genre_string += f'{genre}, '
        resp_dict['info']['genres'] = genre_string.rstrip(', ')
    resp_dict['info']['status'] = entry_info[Site.MAL]['status']\
        if entry_info[Site.MAL] else entry_info[Site.ANILIST]['status']
    resp_dict['image'] = entry_info[Site.MAL]['image'] if entry_info[Site.MAL]\
        else entry_info[Site.ANILIST]['coverImage']['medium']
    if medium == Medium.ANIME:
        resp_dict['info']['episodes'] = entry_info[Site.MAL]['episodes']\
            if entry_info[Site.MAL] else entry_info[Site.ANILIST]['episodes']
        resp_dict['info']['next episode'] = \
            entry_info[Site.ANILIST]['nextAiringEpisode']\
            if entry_info[Site.ANILIST] else None
    else:
        resp_dict['info']['chapters'] = entry_info[Site.MAL]['chapters']\
            if entry_info[Site.MAL] else entry_info[Site.ANILIST]['chapters']
        resp_dict['info']['volumes'] = entry_info[Site.MAL]['volumes']\
            if entry_info[Site.MAL] else entry_info[Site.ANILIST]['volumes']
    return resp_dict


class Search:

    def __init__(self, bot):
        self.bot = bot
        self.logger = bot.logger
        self.footer_title = ''
        for x in range(0, 59):
            self.footer_title += '\_'
        self.footer = bot.footer
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.mino_setup())

    async def mino_setup(self):
        self.mino = await Minoshiro.from_postgres(
            self.bot.mal_config, self.bot.database_config
        )

    async def on_message(self, message):
        if message.author.bot:
            return

        cleaned_message = clean_message(message)
        cleaned_message = await self.__execute_commands(
                cleaned_message, message.channel)
        entry_info = {}
        for thing in get_all_searches(cleaned_message, True):
            self.logger.info(f'Searching for {thing["search"]}')
            try:
                async for data in self.mino.yield_data(
                        thing['search'], thing['medium']):
                    entry_info[data[0]] = data[1]
            except Exception as e:
                self.logger.warning(f'Error searching for {thing["search"]}: '
                                    f'{e}')
            resp = get_response_dict(entry_info, thing['medium'])
            embed = self.__build_entry_embed(resp, thing['expanded'])
            if embed is not None:
                self.logger.info('Found entry, creating message')
                await message.channel.send(embed=embed)

    async def __execute_commands(self, message, channel):
        for match in re.finditer("\{([^{}]*)\}|\<([^<>]*)\>|\]([^[\]]*)\[",
                                 message, re.S):
            command = re.sub('[<>{}[\]]', '', match.group(0))
            if command.startswith('!'):
                if command.lower() == '!toggle expanded':
                    pass
                if command.lower() == '!help':
                    await channel.send(embed=self.__print_help_embed())
                message = re.sub(re.escape(match.group(0)), "", message)
        return message

    def __print_help_embed(self):
        try:
            embed_title = "__Help__"
            help_info = \
                'You can call the bot by using specific tags on one of the '\
                'active servers.\n\nAnime can be called using {curly braces},'\
                ' manga can be called using <arrows> and light novels can be'\
                ' called using reverse ]square braces[ (e.g.{Nisekoi} or '\
                '<Bonnouji> or ]Utsuro no Hako to Zero no Maria\[).\n\n'\
                '{Single} will give you a normal set of information while'\
                ' {{double}} will give you expanded information. '\
                'Examples of these requests can be found [here]'\
                '(https://github.com/dashwav/Discordoragi/wiki/Example-Output)'
            embed = Embed(
                title=embed_title,
                description=help_info
            )
            """
            embed.add_field(
                name=' ',
                value=help_info
            )
            """
            embed.add_field(
                name=self.footer_title,
                value=self.footer
            )
            return embed
        except Exception as e:
            self.logger.warning(f'Exception occured when printing help: {e}')

    def __build_entry_embed(self, entry_info, is_expanded):
        info_text = '('
        for key, data in entry_info['info'].items():
            info_text += f'{key.title()}: {data} | '
        info_text = info_text.rstrip(' | ') + ')'

        try:
            embed = Embed(
                title=entry_info['title'],
                description=entry_info['links'],
                type='rich'
            )
            embed.set_thumbnail(url=entry_info['image'])
            embed.add_field(
                name='__Info__',
                value=info_text
            )
            if is_expanded:
                if len(entry_info['synopsis'].rstrip()) > 1023:
                    desc_text = entry_info['synopsis'].rstrip()[:1020] + '...'
                else:
                    desc_text = entry_info['synopsis'].rstrip()
                embed.add_field(
                    name='__Description__',
                    value=desc_text
                )
            embed.add_field(
                name=self.footer_title,
                value=self.footer
            )
            return embed
        except Exception as e:
            self.logger.warning(f'Error creating embed: {e}')
