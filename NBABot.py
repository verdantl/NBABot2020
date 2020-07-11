from datetime import datetime
import dateparser
import os
from typing import Optional, Tuple, Union, List, Dict, Any
import bs4
import discord
import requests
from discord.ext.commands import Bot
from dotenv import load_dotenv
from nba_api.stats.endpoints import playergamelog, drafthistory, \
    playoffpicture, commonplayerinfo, leaguegamelog
from nba_api.stats.library.parameters import SeasonAll, Season
from nba_api.stats.static import players, teams
from pandas import DataFrame

from team_colors import TEAM_TO_COLORS

BOT_PREFIX = "!"
YEAR = str(datetime.now().year)
ACTIVE_PLAYER_LIST = players.get_active_players()
PLAYER_LIST = players.get_players()
TEAM_LIST = teams.get_teams()

load_dotenv()
TOKEN, GUILD = os.getenv('DISCORD_TOKEN'), os.getenv('DISCORD_GUILD')
CHANNEL_ID = os.getenv('CHANNEL_ID')

bot = Bot(command_prefix=BOT_PREFIX)


def get_game_df():
    return leaguegamelog.LeagueGameLog(direction='DESC').get_data_frames()[0]

#
# GAME_DF = get_game_df()


def playoff_verification(playoff: str) -> str:
    """Verifies if playoff is a regular season or playoff season.
     Returns 'Year' if the string is numeric.
     """

    lowercase = playoff.lower()
    if playoff.isnumeric():
        return 'Year'
    elif lowercase in ['playoff', 'playoffs']:
        return 'Playoffs'
    elif lowercase in ['regular', 'reg']:
        return 'Regular'
    else:
        return 'Did not recognize. Try again.'


def sort(lst: Tuple[Any]) -> Tuple[str, str, Union[str, None], str, str]:
    """Organizes arguments in lst in a more accessible format.
    Length of lst must be >= 2, but less than or equal to 6.
    """
    first_name, last_name, third, year, season = lst[0], lst[1], None, '2019', \
                                                 'Regular'
    if 3 <= len(lst):
        if lst[2].isnumeric():
            year = lst[2]
            season = sort_helper(lst, 4)
        elif playoff_verification(lst[2]) == 'Did not recognize. Try again.':
            third = lst[2]
            pot_year, pot_season = sort_helper(lst, 4), sort_helper(lst, 5)
            if pot_year == 'Year':
                year, season = lst[3], pot_season
            else:
                season = pot_year
        else:
            season = playoff_verification(lst[2])
    if third is not None and third.lower() == 'jr':
        third = 'jr.'
    return first_name, last_name, third, year, season


def sort_helper(lst: Tuple[str], index: int) -> str:
    """Helper function for the sort function above. Helps set the default value
    of the season to 'Regular' if it does not exist in lst.
    """

    if len(lst) >= index:
        return playoff_verification(lst[index - 1])
    else:
        return 'Regular'


def find_player(first_name: str, last_name: str, lst: list) -> Optional:
    """Finds the player in the lst by first_name and last_name. lst should be
    one of the lists given by the nba_api.
    """

    nba_player = None

    for active_player in lst:

        if active_player['first_name'].lower() == first_name and \
                active_player['last_name'].lower() == last_name:
            nba_player = active_player

    return nba_player


def find_picture(player_team: str, id: int):
    """Finds the picture for player/team based on the id by scraping off the
    nba website.
    """

    search_url = 'https://stats.nba.com/' + player_team + '/' + str(id)
    res = requests.get(search_url)
    res.raise_for_status()

    soup = bs4.BeautifulSoup(res.text, 'html.parser')
    image = soup.find("meta", property="og:image")
    url = image["content"] if image else "No meta title given"

    return url


def load_player_dataframe(nba_player, year: str, season_type: str):
    """Returns a data frame of the stats for nba_player in year for the regular
    or post season, depending on the value of season.
    """

    player_id = nba_player['id']
    if season_type == 'Regular':
        gamelog = playergamelog.PlayerGameLog(player_id=player_id, season=year)
    else:
        gamelog = playergamelog.PlayerGameLog(player_id=player_id, season=year,
                                              season_type_all_star='Playoffs')

    return gamelog.get_data_frames()[0]


def avg_values(df) -> dict:
    avg_stats = ['PTS', 'MIN', 'FG_PCT', 'FT_PCT', 'AST', 'REB', 'STL',
                 'BLK']
    statistics = {}

    for stat_name in avg_stats:
        if stat_name.endswith('PCT'):
            attempts = stat_name[0:2] + 'A'
            made = stat_name[0:2] + 'M'
            try:
                percent = df[made].sum() / df[attempts].sum()
                value = str(round(percent * 100, 1)) + '%'
            except ZeroDivisionError:
                value = 'nan'
        else:
            value = str(round(df[stat_name].mean(), 1))
        statistics[stat_name] = value
    return statistics


def conference() -> List:
    """Converts conference data frames to readable strings used by bot command.
    """

    east, west = playoffpicture.PlayoffPicture().get_data_frames()[2], \
                 playoffpicture.PlayoffPicture().get_data_frames()[3]
    values = []
    for conf in (east, west):
        table = ''
        for i in range(len(conf.CONFERENCE)):
            team_value = '. '.join([str(conf['RANK'][i]), conf['TEAM'][i]])
            table += team_value + '\n'
        values.append(table)
    return values


def convert_year(year: str) -> str:
    """Converts year to one year lower."""
    return str(int(year) + 1)


def embed_creator(info: Tuple[str, Optional[str], Any],
                  thumbnail: Optional[str], image: Optional[str],
                  dict_fields: Dict[str, str]) -> discord.Embed:
    """Creates an embed based on the information provided."""
    embed = discord.Embed(title=info[0], description=info[1], color=info[2])

    if thumbnail is not None:
        embed.set_thumbnail(url=thumbnail)
    if image is not None:
        embed.set_image(url=image)
    for field in dict_fields:
        embed.add_field(name=field, value=dict_fields[field])
    return embed


@bot.event
async def on_ready():
    channel = bot.get_channel(int(CHANNEL_ID))
    await channel.send('Connecting...')

    await channel.send(embed=embed_creator((f"NBABot {YEAR} is online",
                                            "View stats for NBA players and "
                                            "teams.", 0x0000FF
                                            ), None,
                                           "https://content.sportslogos.net"
                                           "/news/2017/07/"
                                           "New-NBA-Logo-1.png",
                                           {"NBA": 'Use **!player'
                                                   f'** or **!team** to find out'
                                                   f' more about 'f'the commands'
                                                   f' you can use to 'f'get info'
                                                   f'rmation about both!'}))
    print(f'{bot.user} has connected to Discord!')


@bot.command()
async def pull(ctx):
    """Shows a random player from the current season."""
    random_player = ACTIVE_PLAYER_LIST[random.randint(0,
                                                      len(ACTIVE_PLAYER_LIST - 1))]
    df_log = load_player_dataframe(random_player, '2019', 'Regular')
    team_abb, team_name = season_helper(random_player, '2019', df_log)
    statistics = {'GP': str(len(df_log))}
    statistics.update(avg_values(df_log))
    embed = embed_creator(('2019-2020 Season',
                           ','.join([random_player['full_name'],
                                     team_name.upper()]),
                           TEAM_TO_COLORS[team_abb]),
                          None, find_picture('player', random_player['id']),
                          statistics)
    await ctx.send(embed=embed)

@bot.command()
async def player(ctx):
    """Shows commands that can access player statistics."""
    embed = discord.Embed(title='Player Help', description='This is the player '
                                                           'help section.')
    embed.add_field(name='**!season**',
                    value='Use **!season** followed by the player, year, and '
                          "playoff condition to display a player\'s main stats "
                          "for a given year. If year or playoff condition is "
                          "not entered, the default year is 2019 and default "
                          "season is regular season. \n"
                          "You should put the starting year of the season, e.g."
                          " 2018 for the 2018-2019 season.\n"
                          "Example: **!season james harden 2018 playoffs**")
    # embed.add_field(name='**!last_game**',
    #                 value='Use **!last_game** followed by the player name to '
    #                       "display a player\'s last game matchup, points and "
    #                       "minutes.\n"
    #                       "Example: **!last_game kobe bryant**")
    embed.add_field(name='**!career**',
                    value='Use **!career** followed by the player name to '
                          "display a player\'s stats over their career.\n"
                          "Example: **!career allen iverson**")
    embed.add_field(name='**!draft**', value='Use **!draft** followed by the '
                                             'year and draft pick number to find'
                                             ' the draft pick for that year. '
                                             'Default year and draft are set to'
                                             ' 2019 and 1.\n'
                                             "Example: **!draft 2019 3**"'')

    await ctx.send(embed=embed)


def season_helper(nba_player, year, df_log):
    team_abb, team_name = None, None
    if year == '2019':

        player_info = commonplayerinfo.CommonPlayerInfo(
            player_id=nba_player['id'])
        df_player = player_info.get_data_frames()[0]
        team_abb, team_name = df_player['TEAM_ABBREVIATION'][0], \
                              ' '.join([df_player['TEAM_CITY'][0],
                                        df_player['TEAM_NAME'][0]])
    elif len(df_log['MATCHUP']) > 0:
        team_abb = df_log['MATCHUP'][0][0:3]
        team_name = [team for team in TEAM_LIST if team['abbreviation'] ==
                     team_abb][0]['full_name']
    return team_abb, team_name


@bot.command()
async def season(ctx, *args):
    """Shows the player main stats for the season. Default year and season is
    set to 2019, regular season."""

    if len(args) < 2:
        await ctx.send("Please enter the player's full name")
    else:
        await ctx.send('Loading...')
        values = sort(args)
        first_name, last_name = values[0], values[1]
        if values[2] is not None:
            last_name = last_name + ' ' + values[2]
        year, nba_season, nba_player = values[3], values[4], \
                                       find_player(first_name, last_name,
                                                   ACTIVE_PLAYER_LIST)
        if nba_player is None:
            await ctx.send(
                'The player you asked for is either inactive or your '
                'query cannot be followed.')
        else:
            df_log = load_player_dataframe(nba_player, year, nba_season)
            team_abb, team_name = season_helper(nba_player, year, df_log)

            if team_abb is None or team_name is None:
                await ctx.send('Player did not play this season.')
            else:
                embed = discord.Embed(
                    title=year + '-' + convert_year(year) + ' ' +
                          nba_season + ' Season Stats',
                    description=', '.join(
                        [nba_player['full_name'],
                         team_name.upper()]),
                    color=TEAM_TO_COLORS[team_abb])
                embed.set_thumbnail(
                    url=find_picture('player', nba_player['id']))
                statistics = {'GP': str(len(df_log))}
                statistics.update(avg_values(df_log))
                for key in statistics:
                    embed.add_field(name=key, value=statistics[key])

                await ctx.send(embed=embed)


@bot.command()
async def career(ctx, *args):
    """Shows the player stats for their career.
    Default is for regular season.
    """
    await ctx.send('Loading...')
    if len(args) < 2:
        await ctx.send("Please enter the player's full name.")
        return
    first_name, last_name, third, year, season_type = sort(args)
    if third is not None:
        last_name = last_name + ' ' + third
    nba_player = find_player(first_name, last_name, PLAYER_LIST)
    nba_season = season_type

    if season_type.lower() == 'playoff' or season_type.lower() == 'playoffs':
        nba_season = 'Playoffs'

    if nba_player is None:
        await ctx.send('The player you asked for does not exist in the '
                       'database.')

    else:
        df_log = load_player_dataframe(nba_player, SeasonAll.all, nba_season)
        statistics = {'GP': str(len(df_log))}
        statistics.update(avg_values(df_log))
        playoffs = ''
        if nba_season == 'Playoffs':
            playoffs = ' ' + nba_season
        embed = discord.Embed(title='Career' + playoffs + ' Stats',
                              description=nba_player['full_name'],
                              color=0x738ADB)
        embed.set_thumbnail(url=find_picture('player', nba_player['id']))

        for key in statistics:
            embed.add_field(name=key, value=statistics[key])

        await ctx.send(embed=embed)


# @bot.command()
# async def last_game(ctx, first_name, last_name):
#     """Shows the player stats for their last game, along with the date and
#     against which team."""
#     nba_player = find_player(first_name, last_name, PLAYER_LIST)
#     if nba_player is None:
#         await ctx.send('The player you asked for does not exist in the '
#                        'database.')
#     else:
#         df_player = load_player_dataframe(nba_player, SeasonAll.all, 'Regular')
#         game = df_player.iloc[0, :]
#         year = str(game.SEASON_ID[1:])
#         game_df = get_game_df(year)
#         game_log = game_df[game_df.GAME_ID == game.Game_ID]
#         team_name = [team['full_name'] for team in TEAM_LIST if
#                      team['abbreviation'] == df_player.MATCHUP[0][0:3]][0]
#
#         for i in range(len(game_log)):
#             temp = game_log.iloc[i, :]
#             if temp.TEAM_NAME == team_name:
#                 first = temp.PTS
#             else:
#                 second = temp.PTS
#         info = ('Last Game: **' + nba_player['full_name'] + '**', ', '.join(
#             [df_player.MATCHUP[0], df_player.GAME_DATE[0]]), TEAM_TO_COLORS[
#                     df_player.MATCHUP[0][0:3]])
#         fields = {'POINTS': df_player.PTS[0], 'MINUTES': df_player.MIN[0],
#                   'SCORE': '-'.join([str(first), str(second)])}
#         url = find_picture('player', nba_player['id'])
#         embed = embed_creator(info, url, None, fields)
#
#         await ctx.send(embed=embed)


@bot.command()
async def standings(ctx):
    """Shows the current league standings in each conference."""
    east, west = conference()

    url = 'https://www.gamblingsites.net/wp-content/uploads/2019/07/nba' \
          '-eastern-western-conference-winner-2020.jpg '
    await ctx.send(embed=embed_creator(('NBA STANDINGS', None, 0x3DFF33),
                                       url, None,
                                       {"Western Conference": west,
                                        'Eastern Conference': east}))


@bot.command()
async def team(ctx):
    """Shows commands that can be performed to access team statistics."""
    embed = discord.Embed(title='Teams Help Section')
    embed.add_field(name='**!teams**', value='Use **!teams** to get a list of'
                                             'all NBA teams in alphabetical '
                                             'order.')
    embed.add_field(name='**!standings**', value='Use **!standings** to get the'
                                                 'current playoff rankings.')
    embed.add_field(name='**!teams**', value='Use **!teams** to get a list of'
                                             'the NBA teams in alphabetical '
                                             'order.')
    embed.add_field(name='**!get_games**', value='Use **!get_games**, followed '
                                                 'by an optional date, to get '
                                                 'all of the games that '
                                                 'occurred '
                                                 'on that date. If no date is'
                                                 ' entered, uses the current'
                                                 ' date.')
    embed.add_field(name='**!last**', value='Use **!last** followed by the team'
                                            ' name to get the last game and '
                                            'score for the entered team. \n'
                                            'Example: !last miami heat')
    await ctx.send(embed=embed)


@bot.command()
async def teams(ctx):
    """Shows a list of NBA teams in alphabetical order."""

    team_lst = []
    for nba in TEAM_LIST:
        team_lst.append(nba['full_name'])
    embed = discord.Embed(title='NBA TEAMS', description=None, color=0x3354FF)
    field_team = ''
    for i in range(len(team_lst)):
        if i != 0 and i % 10 == 0:
            embed.add_field(name='_', value=field_team)
            field_team = ''
        else:
            field_team += team_lst[i] + '\n'
    embed.add_field(name='_', value=field_team)
    await ctx.send(embed=embed)


@bot.command()
async def get_games(ctx, *args):
    """Gets all of the games from the current season that happened on a certain
    month, day, and year. If nothing is entered, the default will be set to the
    current day."""
    if len(args) == 0:
        today = datetime.now()
        date = datetime(today.year, today.month, today.day).strftime("%Y-%m-%d")
    else:
        value = ' '.join(args)
        try:
            today = dateparser.parse(date_string=value)
            date = datetime(today.year, today.month, today.day).strftime("%Y"
                                                                         "-%m"
                                                                         "-%d")
        except AttributeError:
            await ctx.send('Improper date format. Please try again.')
            return
    if today.year == 2020 or (today.year == 2019 and today.month > 7):
        game_df = GAME_DF  # this saves time, don't have to retrieve the game_df
    elif today.month > 7:
        game_df = get_game_df(str(today.year))
    else:
        game_df = get_game_df(str(today.year - 1))

    selected = game_df[game_df['GAME_DATE'] == date]
    game_ids = []
    fields = {}
    for i in range(len(selected)):
        row = selected.iloc[i, :]
        if row['GAME_ID'] not in game_ids:
            game_ids.append(row['GAME_ID'])
            first, second = game_finder(game_df, row['GAME_ID'], row)
            fields[first['MATCHUP']] = '-'.join([str(first.PTS),
                                                 str(second.PTS)])
    info = ('**Get Games**', 'Games occuring on ' + date + ':', 0xBEC0C2)
    embed = embed_creator(info, None, None, fields)
    await ctx.send(embed=embed)


def game_finder(game_df: DataFrame, game_id: int, first: DataFrame):
    game = game_df[game_df['GAME_ID'] == game_id]

    second = game.iloc[0, :]
    if first.TEAM_ID == second.TEAM_ID:
        second = game.iloc[1, :]
    return first, second


@bot.command()
async def next(ctx, *args):
    """Gets the next game for a certain team."""
    # TODO Will be implemented when the NBA season returns from the COVID-19 situation.
    pass


def team_finder(df: DataFrame, team_name: str):
    """Helps find teams from data frame."""
    name = team_name.lower()
    team_dict = [team for team in TEAM_LIST if (team['full_name'].lower() ==
                                                name or team[
                                                    'abbreviation'] == name or
                                                team['nickname'] ==
                                                name or team['city'] == name)][
        0]
    return df[df['TEAM_ID'] == team_dict['id']]


@bot.command()
async def last(ctx, *args):
    """Gets the last game for a team for a given team."""
    values = []
    for value in args:
        values.append(value.lower())
    team_name = ' '.join(values)

    first = team_finder(GAME_DF, team_name).iloc[0, :]

    if len(first) == 0:
        await ctx.send('The team you are looking for does not exist.')

    else:

        first, second = game_finder(GAME_DF, first.GAME_ID, first)

        info, fields = (first.GAME_DATE, first.MATCHUP,
                        TEAM_TO_COLORS[first.MATCHUP[:3]]), \
                       {first.TEAM_NAME: first.PTS,
                        second.TEAM_NAME: second.PTS}
        pic_url = f'https://a.espncdn.com/i/teamlogos/nba/500' \
                  f'/{first.MATCHUP[:3]}.png'
        embed = embed_creator(info, pic_url, None, fields)
        await ctx.send(embed=embed)


@bot.command()
async def draft(ctx, year='2019', pick='1'):
    """Get the indicated draft pick for year.
    Default year is 2019 and default pick is set to 1.
    """
    await ctx.send('Loading...')
    drafting = drafthistory.DraftHistory(season_year_nullable=year,
                                         overall_pick_nullable=pick)
    df_draft = drafting.get_data_frames()[0]
    if len(df_draft) == 0:
        await ctx.send('The draft pick you entered does not exist in the '
                       'databases.')
        return
    embed = discord.Embed(title=year + ' NBA Draft', description='Pick No. ' +
                                                                 pick)
    embed.add_field(name=df_draft.PLAYER_NAME[0], value=df_draft.TEAM_CITY[0] +
                                                        ' ' +
                                                        df_draft.TEAM_NAME[0])
    embed.set_thumbnail(url=find_picture('player', df_draft['PERSON_ID'][0]))

    await ctx.send(embed=embed)


bot.run(TOKEN)
