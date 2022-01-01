import asyncio
import json
import random
import re
from datetime import datetime, timedelta, timezone
from keep_alive import keep_alive

import discord
import numpy

import settings
from classes import GameInfo
from google_input import FilterRuleTable, GoogleInput

TOKEN = settings.TOKEN
client = discord.Client(intents=discord.Intents.all())
jst = timezone(timedelta(hours=9), 'JST')
table = FilterRuleTable.from_file("google_ime_default_roman_table.txt")
gi = GoogleInput(table)
dt_now = datetime.now(jst)
with open('susida.json', encoding='utf-8') as f:
    sushida_dict = json.load(f)
player_list = []
ongoing_game_dict = {}
alphabet_regex = re.compile('[ -~]+')
global_ranking_file_path = './global-ranking.json'
mobile_ranking_file_path = './mobile-ranking.json'
with open(global_ranking_file_path) as f:
    global_ranking_dict: dict = json.load(f)
with open(mobile_ranking_file_path) as f:
    mobile_ranking_dict: dict = json.load(f)

keep_alive()

@client.event
async def on_ready():
    print('ready')

@client.event
async def on_message(message):
    if message.author.bot:
        return
    if message.guild is None:
        await dm_commands(message)
    elif message.content in {'ty.ranking', 'ty.ランキング', 'ty.ランキング'}:
        await send_global_ranking(message)
    elif message.content in {'ty.タイピング', 'ty.typing', 'ty.start'}:
        await game_start(message)
    elif message.content in {'終了', 'end', 'shuuryou'}:
        await end_game(message)
    elif message.content in {'次', 'next', 'tugi', 'tsugi'}:
        await next_question(message)
    elif message.channel.id in ongoing_game_dict:
        await answering(message)
    elif message.content in {'ty.ヘルプ', 'ty.help'}:
      await help_message(message)


async def game_start(message):
    if message.channel.id in ongoing_game_dict:
        await message.channel.send('既にこのチャンネルでゲームが進行中です。参加者の方はゲームを終了させて下さい。')
        return
    game_info = GameInfo(channel_id=message.channel.id)
    # モバイルかどうか判別
    if message.author.is_on_mobile():
        embed_title = '📱レベルを選択して下さい'
    else:
        embed_title = 'レベルを選択して下さい'
    embed = discord.Embed(title=embed_title, description='レベルの番号を送って下さい。',
                          color=0x85cc00)
    val = 0
    while val < 15:
        val = val + 1
        if val == 13:
            embed.add_field(name='［13］14文字以上', value='最高難易度の14文字以上の問題です。', inline=False)
            break
        embed.add_field(name='［' + str(val) + '］' + str(val + 1) + '文字', value=str(val + 1) + '文字の問題です。',
                        inline=False)
    wizzard = await message.channel.send(embed=embed)

    def reaction_check(reaction, user):
        if reaction.message.id == wizzard.id:
            if not user.bot:
                if str(reaction) in {'➡', '✋'}:
                    return True
        return False

    def bot_check(m):
        return m.channel == message.channel and m.author == message.author \
               and m.author.bot is not True

    level_select = await client.wait_for('message', check=bot_check)
    try:
        word_count = int(level_select.content) + 1
    except ValueError:
        embed = discord.Embed(title='エラー：キャンセルしました',
                              description='レベルの番号以外が入力されました。\n半角数字で、レベルの番号を入力して下さい。', color=discord.Color.red())
        await wizzard.edit(embed=embed)
        return
    if str(word_count) not in sushida_dict:
        embed = discord.Embed(title='エラー：キャンセルしました',
                              description='レベルの番号以外が入力されました。\n半角数字で、レベルの番号を入力して下さい。', color=discord.Color.red())
        await wizzard.edit(embed=embed)
        return
    question_list_index = 0
    game_info.question_index_num = question_list_index
    game_info.question_list = random.sample(sushida_dict[str(word_count)], 10)
    game_info.word_count = word_count
    embed = discord.Embed(title='参加する人はリアクションを押して下さい。',
                          description='参加する人は✋のリアクションを押して下さい。\n➡のリアクションで募集を締め切ります。')
    await wizzard.edit(embed=embed)
    await wizzard.add_reaction('✋')
    await wizzard.add_reaction('➡')
    level_loop = True
    while level_loop is True:
        reaction, user = await client.wait_for('reaction_add', check=reaction_check)
        if str(reaction) == '➡':
            if len(game_info.player_list) == 0:
                await message.channel.send('参加リアクションが押されていないため、ゲームを開始できません。\n'
                                           'ゲームをキャンセルします。')
                await wizzard.delete()
                return
            break
        if user.id in game_info.player_list:
            continue
        if user.id in player_list:
            await message.channel.send(f'{user.mention} 既に他のゲームに参加しています。先にそちらを終了させてください。')
            continue
        player_list.append(user.id)
        game_info.add_player(user.id)
        continue
    await wizzard.remove_reaction(emoji='➡', member=client.user)
    await wizzard.remove_reaction(emoji='✋', member=client.user)
    embed = discord.Embed(title='第' + str(question_list_index + 1) + '問',
                          description=game_info.question_list[question_list_index][1])
    game_start_notice = await message.channel.send('3秒後にゲームを開始します。')
    await asyncio.sleep(1)
    await game_start_notice.edit(content='2秒後にゲームを開始します。')
    await asyncio.sleep(1)
    await game_start_notice.edit(content='1秒後にゲームを開始します。')
    await asyncio.sleep(1)
    await game_start_notice.delete()
    msg = await message.channel.send(embed=embed)
    game_info.start_time = msg.created_at.timestamp()
    ongoing_game_dict[message.channel.id] = game_info
    return


async def end_game(message):
    if message.channel.id not in ongoing_game_dict:
        await message.channel.send('このチャンネルで進行中のゲームはありません。')
        return
    game_info = get_game_info(message.channel.id)
    if not message.channel.permissions_for(message.author).manage_messages:
        if message.author.id not in game_info.player_list:
            await message.channel.send('あなたはこのチャンネルで進行中のゲームに参加していません。')
            return
        elif message.author.id == "752814117806407710":
              embed: discord.Embed = generate_ranking_embed(game_info)
              await message.channel.send(embed=embed)
              for user_id in game_info.player_list:
                  player_list.remove(user_id)
              del ongoing_game_dict[message.channel.id]
              await message.channel.send('現在進行中のゲームを終了しました。')
              return 

    embed: discord.Embed = generate_ranking_embed(game_info)
    await message.channel.send(embed=embed)
    for user_id in game_info.player_list:
        player_list.remove(user_id)
    del ongoing_game_dict[message.channel.id]
    await message.channel.send('現在進行中のゲームを終了しました。')
    return


async def send_global_ranking(message):
    embed = discord.Embed(title='グローバルランキング(上位10位)',
                          description='このBotが導入されている全サーバーでのランキングです。'
                                      '\n※ランキングに載るには、レベル10(11文字)で全問題に回答する必要があります。'
                                      '\n100位までのランキングを表示するには、60秒以内に⏩のリアクションをして下さい。',
                          color=discord.Color.dark_magenta())
    global_ranking = ranking_sort(global_ranking_dict)
    for list_top in global_ranking:
        if global_ranking.index(list_top) == 10:
            break
        player = client.get_user(int(list_top[0]))
        if player is None:
            player = await client.fetch_user(int(list_top[0]))
        player_time = list_top[1]
        embed.add_field(name='［' + str(global_ranking.index(list_top) + 1) + '位］' + player.name + 'さん',
                        value='平均タイム：' + f'{player_time:.3f}' + '秒',
                        inline=False)
        continue
    ranking_msg = await message.channel.send(embed=embed)
    await ranking_msg.add_reaction('⏩')

    def reaction_check(reaction, user):
        if reaction.message.id == ranking_msg.id:
            if not user.bot:
                if str(reaction) == '⏩':
                    return True
        return False

    try:
        reaction, user = await client.wait_for('reaction_add', check=reaction_check, timeout=60)
    except asyncio.TimeoutError:
        await ranking_msg.remove_reaction(emoji='⏩', member=client.get_user(736243567931949136))
        return
    else:
        embed = discord.Embed(title='グローバルランキング(上位100位)',
                              description='このBotが導入されている全サーバーでのランキングです。'
                                          '\n※ランキングに載るには、レベル10(11文字)で全問題に回答する必要があります。',
                              color=discord.Color.dark_magenta())
        for list_top in global_ranking:
            if global_ranking.index(list_top) == 100:
                break
            player = client.get_user(int(list_top[0]))
            if player is None:
                player = await client.fetch_user(int(list_top[0]))
            player_name = player.name
            player_time = list_top[1]
            embed.add_field(name='［' + str(global_ranking.index(list_top) + 1) + '位］' + player_name + 'さん',
                            value='平均タイム：' + f'{player_time:.3f}' + '秒',
                            inline=False)
            continue
        await ranking_msg.edit(embed=embed)
    return


async def next_question(message):
    game_info: GameInfo = get_game_info(message.channel.id)
    if game_info is None:
        return
    if message.author.id not in game_info.player_list:
        return
    question_index_num = game_info.question_index_num
    # 問題番号を1追加
    question_index_num = question_index_num + 1
    not_answered_player = ""
    for user_id in game_info.player_list:
        if game_info.competitor_status[user_id] != 'answered':
            not_answered_player = f'{not_answered_player}{client.get_user(user_id).name}\n'
    if len(not_answered_player) != 0:
        await message.channel.send('問題に未回答の人がいます。次の問題に進めてよろしいですか？\n'
                                   '進める場合は、もう一度「次」と入力してください。\n'
                                   '未回答の人：\n```' + not_answered_player + '```')

        def bot_check(m):
            return m.channel == message.channel and m.author == message.author \
                   and m.author.bot is not True

        next_question_confirm = await client.wait_for('message', check=bot_check)
        if next_question_confirm.content in {'次', 'next', 'tugi', 'tsugi'}:
            pass
        else:
            return
    for user_id in game_info.player_list:
        game_info.competitor_status[user_id] = 'answering'
    if len(game_info.question_list) - 1 == question_index_num:
        embed_title = f'最終問題です！第{question_index_num + 1}問'
    else:
        embed_title = f'第{question_index_num + 1}問'
    embed = discord.Embed(title=embed_title,
                          description=game_info.question_list[question_index_num][1])
    msg = await message.channel.send(embed=embed)
    game_info.start_time = msg.created_at.timestamp()
    game_info.question_index_num = question_index_num
    ongoing_game_dict[message.channel.id] = game_info

async def help_message(message):
    embed = discord.Embed(title="ヘルプ・コマンド一覧",
                          description="こんな感じ\n"
                                      "問「新入生歓迎会」：解「しんにゅうせいかんげいかい」or「sinnnyuuseikanngeikai」\n"
                                      "ひらがなもしくはローマ字で回答して下さい。\n"
                                      "また、完答後に自己ベストが出ると🚩の絵文字が表示されます。(未実装)",
                          color=0x0008ff)
    embed.add_field(name='ty.タイピング',
                    value="・レベルを選択し、ゲームを開始します。\n選択したレベルからランダムに10問出題されます。", inline=False)
    embed.add_field(name='次',
                    value="・次の問題を出します。\n(進行中のゲームがない場合には反応しません。)", inline=False)
    embed.add_field(name='終了',
                    value="・現在進行中のゲームを終了させます。", inline=False)
    embed.add_field(name='ty.ランキング or ty.ranking',
                    value="全サーバーでのランキングを表示します。", inline=False)
    await message.channel.send(embed=embed)
    return

async def answering(message):
    game_info = get_game_info(message.channel.id)
    if game_info is None:
        return
    if message.author.id in game_info.player_list:
        if game_info.competitor_status[message.author.id] == 'answering':
            question_index_num = game_info.question_index_num
            if alphabet_regex.fullmatch(message.content):
                message.content = rome_to_hiragana(message.content)
                message.content = message.content.replace('!', '！')
                message.content = message.content.replace('?', '？')
                message.content = message.content.strip()
            answer = game_info.question_list[question_index_num][0]
            if message.content == answer:
                end_time = message.created_at.timestamp()
                start_time = game_info.start_time
                embed = discord.Embed(title='正解です！',
                                      description='解答時間：' + str(end_time - start_time) + '秒')
                await message.channel.send(message.author.mention, embed=embed)
                if len(game_info.question_list) - 1 == question_index_num:
                    game_info.competitor_status[message.author.id] = 'ended'
                else:
                    game_info.competitor_status[message.author.id] = 'answered'
                game_info.competitor_time_list[message.author.id].append(end_time - start_time)
                finished_user_count = 0
                for user_id in game_info.player_list:
                    if game_info.competitor_status[user_id] == 'ended':
                        finished_user_count = finished_user_count + 1
                if len(game_info.question_list) - 1 == question_index_num:
                    game_info.competitor_status[message.author.id] = 'ended'
                    embed2 = discord.Embed(title='平均タイム',
                                           description='あなたの平均タイムです', color=discord.Color.dark_teal())
                    name = message.author.name
                    average = numpy.average(game_info.competitor_time_list[message.author.id])
                    if len(game_info.competitor_time_list[message.author.id]) != len(
                            game_info.question_list):
                        add_global_ranking = False
                        not_answered = str(
                            len(game_info.question_list) - len(
                                game_info.competitor_time_list[message.author.id])) + '問'
                    else:
                        not_answered = 'なし'
                        if game_info.word_count == 11:
                            add_global_ranking = True
                        else:
                            add_global_ranking = False
                    embed2.add_field(name=name + 'さん',
                                     value=f'平均タイム：{average:.3f}秒\n未回答の問題：{not_answered}')
                    await message.channel.send(embed=embed2)
                    if add_global_ranking is True:
                        ranking_add(player_id=message.author.id, score=average)
                ongoing_game_dict[message.channel.id] = game_info
                if finished_user_count == len(game_info.competitor_time_list):
                    embed2 = generate_ranking_embed(game_info)
                    for user_id in game_info.player_list:
                        player_list.remove(user_id)
                    del ongoing_game_dict[message.channel.id]
                    await message.channel.send('ゲームが終了しました', embed=embed2)
                return
            else:
                embed = discord.Embed(title='不正解です！',
                                      description='もう一度お試し下さい。')
                await message.channel.send(message.author.mention, embed=embed)
                return


async def dm_commands(message):
    if message.content == 'サーバー':
        await message.channel.send(str(len(client.guilds)))
    elif message.content == '使用中':
        await message.channel.send(str(len(ongoing_game_dict.keys())))


def ranking_add(player_id, score, ranking='global'):
    if ranking == 'mobile':
        current_score = mobile_ranking_dict.get(str(player_id))
        if current_score is not None:
            if current_score < score:
                return
        mobile_ranking_dict[str(player_id)] = score
        with open(mobile_ranking_file_path, 'w') as e:
            json.dump(mobile_ranking_dict, e, indent=4)
        return
    else:
        current_score = global_ranking_dict.get(str(player_id))
        if current_score is not None:
            if current_score < score:
                return
        global_ranking_dict[str(player_id)] = score
        with open(global_ranking_file_path, 'w') as e:
            json.dump(global_ranking_dict, e, indent=4)
        return


def ranking_sort(ranking_dict: dict):
    ranking = sorted(ranking_dict.items(), key=lambda x: x[1])
    return ranking


def generate_ranking_embed(game_info: GameInfo):
    embed = discord.Embed(title='平均タイム',
                          description='参加者の平均タイムです', color=discord.Color.red())
    competitor_average_time = {}
    for user_id in game_info.player_list:
        average = numpy.average(game_info.competitor_time_list[user_id])
        competitor_average_time[user_id] = average
    competitor_ranking = sorted(competitor_average_time.items(), key=lambda x: x[1])
    for val in competitor_ranking:
        player_id = val[0]
        player_time = val[1]
        rank = competitor_ranking.index(val) + 1
        name = client.get_user(player_id).name
        if len(game_info.competitor_time_list[player_id]) != len(
                game_info.question_list):
            not_answered = str(
                len(game_info.question_list) - len(
                    game_info.competitor_time_list[player_id])) + '問'
        else:
            not_answered = 'なし'
        embed.add_field(name='［' + str(rank) + '位］' + name + 'さん',
                        value='平均タイム：' + f'{player_time:.3f}' + '秒\n未回答の問題：' + not_answered,
                        inline=False)
    return embed


def generate_average_embed(message):
    pass


def rome_to_hiragana(input_string):
    output = ""
    for c in input_string:
        result = gi.input(c)
        if result.fixed:
            output += result.fixed.output
        else:
            if not result.tmp_fixed and not result.next_candidates:
                output += result.input
    return output


def get_game_info(channel_id: int):
    game_info: GameInfo = ongoing_game_dict.get(channel_id)
    return game_info


client.run(TOKEN)
