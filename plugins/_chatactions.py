# Ultroid - UserBot
# Copyright (C) 2021-2023 TeamUltroid
#
# This file is a part of < https://github.com/TeamUltroid/Ultroid/ >
# PLease read the GNU Affero General Public License in
# <https://www.github.com/TeamUltroid/Ultroid/blob/main/LICENSE/>.

import asyncio
from typing import Union

import requests
from telethon import events
from telethon.errors.rpcerrorlist import UserNotParticipantError
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.utils import get_display_name

from pyUltroid.dB import stickers
from pyUltroid.dB.echo_db import check_echo
from pyUltroid.dB.forcesub_db import get_forcesetting
from pyUltroid.dB.gban_mute_db import is_gbanned
from pyUltroid.dB.greetings_db import get_goodbye, get_welcome, must_thank
from pyUltroid.dB.nsfw_db import is_profan
from pyUltroid.fns.helper import check_reply_to, inline_mention
from pyUltroid.fns.tools import (
    async_searcher,
    create_tl_btn,
    get_chatbot_reply,
    get_oracle_reply,
)

try:
    from ProfanityDetector import detector
except ImportError:
    detector = None
from . import LOG_CHANNEL, LOGS, asst, get_string, types, udB, ultroid_bot
from ._inline import something

# ------------------------- UFoP Bans -------------------------#


class UFoPBan:
    def __init__(self, api_key: str = None):
        self.api_key = api_key

    def _make_request(
        self, method: str, url: str, params: dict = None, json_data: dict = None
    ):
        headers = {"accept": "application/json", "api-key": self.api_key}
        try:
            response = requests.request(
                method, url, headers=headers, params=params, json=json_data
            )
            return response.json()
        except requests.RequestException:
            pass

    def get_ufop_ban(
        self, user_id: int = None, banlist: bool = False
    ) -> Union[dict, str]:
        if banlist:
            url = "https://ufoptg-ufop-api.hf.space/UFoP/bans"
            payload = {"user_id": user_id}
            return self._make_request("GET", url, params=payload)
        else:
            raise ValueError("Error: banlist must be True")


# ------------------------- Huge Thanks to @xtdevs -------------------------#


@ultroid_bot.on(events.ChatAction())
async def Function(event):
    try:
        await DummyHandler(event)
    except Exception as er:
        LOGS.exception(er)


async def DummyHandler(ult):
    # clean chat actions
    key = udB.get_key("CLEANCHAT") or []
    if ult.chat_id in key:
        try:
            await ult.delete()
        except BaseException:
            pass

    # thank members
    if must_thank(ult.chat_id):
        chat_count = (await ult.client.get_participants(ult.chat_id, limit=0)).total
        if chat_count % 100 == 0:
            stik_id = chat_count / 100 - 1
            sticker = stickers[stik_id]
            await ult.respond(file=sticker)
    # force subscribe
    if (
        udB.get_key("FORCESUB")
        and ((ult.user_joined or ult.user_added))
        and get_forcesetting(ult.chat_id)
    ):
        user = await ult.get_user()
        if not user.bot:
            joinchat = get_forcesetting(ult.chat_id)
            try:
                await ultroid_bot(GetParticipantRequest(int(joinchat), user.id))
            except UserNotParticipantError:
                await ultroid_bot.edit_permissions(
                    ult.chat_id, user.id, send_messages=False
                )
                res = await ultroid_bot.inline_query(
                    asst.me.username, f"fsub {user.id}_{joinchat}"
                )
                await res[0].click(ult.chat_id, reply_to=ult.action_message.id)

    if ult.user_joined or ult.added_by:
        user = await ult.get_user()
        chat = await ult.get_chat()
        # gbans and @UltroidBans checks
        if udB.get_key("ULTROID_BANS"):
            try:
                is_banned = await async_searcher(
                    "https://bans.ultroid.tech/api/status",
                    json={"userId": user.id},
                    post=True,
                    re_json=True,
                )
                if is_banned["is_banned"]:
                    await ult.client.edit_permissions(
                        chat.id,
                        user.id,
                        view_messages=False,
                    )
                    await ult.respond(
                        f'**@UltroidBans:** Banned user detected and banned!\n`{str(is_banned)}`.\nBan reason: {is_banned["reason"]}',
                    )

            except BaseException:
                pass

        if udB.get_key("UFoP_BANS"):
            ufop_api_key = udB.get_key("UFOPAPI")
            clients = UFoPBan(ufop_api_key)
            try:
                UFoP_banned = clients.get_ufop_ban(user_id=user.id, banlist=True)

                if UFoP_banned and UFoP_banned.get("sukuna", {}).get(
                    "is_banned", False
                ):
                    await ult.client.edit_permissions(
                        chat.id,
                        user.id,
                        view_messages=False,
                    )
                    await ult.respond(
                        f"**🌀ʊʄ⊕ք🌀:** Banned user detected and banned!\n"
                        f'Sibyl User ID: {UFoP_banned["sukuna"]["sibyl_user_id"]}\n'
                        f'Ban Reason: {UFoP_banned["sukuna"]["reason"]}',
                    )

            except Exception as e:
                LOGS.exception(f"Error checking UFoP: {e}")

        reason = is_gbanned(user.id)
        if reason and chat.admin_rights:
            try:
                await ult.client.edit_permissions(
                    chat.id,
                    user.id,
                    view_messages=False,
                )
                gban_watch = get_string("can_1").format(inline_mention(user), reason)
                await ult.reply(gban_watch)
            except Exception as er:
                LOGS.exception(er)

        # greetings
        elif get_welcome(ult.chat_id):
            user = await ult.get_user()
            chat = await ult.get_chat()
            title = chat.title or "this chat"
            count = (
                chat.participants_count
                or (await ult.client.get_participants(chat, limit=0)).total
            )
            mention = inline_mention(user)
            name = user.first_name
            fullname = get_display_name(user)
            uu = user.username
            username = f"@{uu}" if uu else mention
            wel = get_welcome(ult.chat_id)
            msgg = wel["welcome"]
            med = wel["media"] or None
            userid = user.id
            msg = None
            if msgg:
                msg = msgg.format(
                    mention=mention,
                    group=title,
                    count=count,
                    name=name,
                    fullname=fullname,
                    username=username,
                    userid=userid,
                )
            if wel.get("button"):
                btn = create_tl_btn(wel["button"])
                await something(ult, msg, med, btn)
            elif msg:
                send = await ult.reply(
                    msg,
                    file=med,
                )
                await asyncio.sleep(150)
                await send.delete()
            else:
                await ult.reply(file=med)
    elif (ult.user_left or ult.user_kicked) and get_goodbye(ult.chat_id):
        user = await ult.get_user()
        chat = await ult.get_chat()
        title = chat.title or "this chat"
        count = (
            chat.participants_count
            or (await ult.client.get_participants(chat, limit=0)).total
        )
        mention = inline_mention(user)
        name = user.first_name
        fullname = get_display_name(user)
        uu = user.username
        username = f"@{uu}" if uu else mention
        wel = get_goodbye(ult.chat_id)
        msgg = wel["goodbye"]
        med = wel["media"]
        userid = user.id
        msg = None
        if msgg:
            msg = msgg.format(
                mention=mention,
                group=title,
                count=count,
                name=name,
                fullname=fullname,
                username=username,
                userid=userid,
            )
        if wel.get("button"):
            btn = create_tl_btn(wel["button"])
            await something(ult, msg, med, btn)
        elif msg:
            send = await ult.reply(
                msg,
                file=med,
            )
            await asyncio.sleep(150)
            await send.delete()
        else:
            await ult.reply(file=med)


@ultroid_bot.on(events.NewMessage(incoming=True))
async def chatBot_replies(e):
    xxrep = await check_reply_to(e)

    if xxrep:
        sender = await e.get_sender()
        if not isinstance(sender, types.User) or sender.bot:
            return
        if check_echo(e.chat_id, e.sender_id):
            try:
                await e.respond(e.message)
            except Exception as er:
                LOGS.exception(er)
        key = udB.get_key("CHATBOT_USERS") or {}
        if e.text and key.get(e.chat_id) and sender.id in key[e.chat_id]:
            # Simulate typing indicator
            async with e.client.action(e.chat_id, "typing"):
                msg = await get_chatbot_reply(e.message.message)
                if msg:
                    sleep = udB.get_key("CHATBOT_SLEEP") or 1.5
                    await asyncio.sleep(sleep)

                    # Check if the message length exceeds a certain threshold
                    if len(msg) > 4096:
                        # Create a temporary text file
                        with tempfile.NamedTemporaryFile(
                            mode="w+", delete=False
                        ) as temp_file:
                            temp_file.write(msg)

                        # Send the text file with a caption
                        await e.client.send_file(
                            e.chat_id,
                            temp_file.name,
                            caption="Here is the response in a text file.",
                        )

                        # Delete the temporary text file
                        os.remove(temp_file.name)
                    else:
                        # Send the message directly
                        await e.reply(msg)

        chat = await e.get_chat()
        if e.is_group and sender.username:
            await uname_stuff(e.sender_id, sender.username, sender.first_name)
        elif e.is_private and chat.username:
            await uname_stuff(e.sender_id, chat.username, chat.first_name)
        if detector and is_profan(e.chat_id) and e.text:
            x, y = detector(e.text)
            if y:
                await e.delete()


@ultroid_bot.on(events.NewMessage(incoming=True))
async def oracleBot_replies(e):
    xxxrep = await check_reply_to(e)

    if xxxrep:
        sender = await e.get_sender()
        if not isinstance(sender, types.User) or sender.bot:
            return
        if check_echo(e.chat_id, e.sender_id):
            try:
                await e.respond(e.message)
            except Exception as er:
                LOGS.exception(er)
        key = udB.get_key("ORACLE_USERS") or {}
        if e.text and key.get(e.chat_id) and sender.id in key[e.chat_id]:
            # Simulate typing indicator
            async with e.client.action(e.chat_id, "typing"):
                msg = await get_oracle_reply(
                    e.message.message, user_id=sender.id, mongo_url=MONGO_URI
                )
                if msg:
                    sleep = udB.get_key("ORACLE_SLEEP") or 1.5
                    await asyncio.sleep(sleep)

                    # Check if the message length exceeds a certain threshold
                    if len(msg) > 4096:
                        # Create a temporary text file
                        with tempfile.NamedTemporaryFile(
                            mode="w+", delete=False
                        ) as temp_file:
                            temp_file.write(msg)

                        # Send the text file with a caption
                        await e.client.send_file(
                            e.chat_id,
                            temp_file.name,
                            caption="Here is the response in a text file",
                        )

                        # Delete the temporary text file
                        os.remove(temp_file.name)
                    else:
                        # Send the message directly
                        await e.reply(msg)

        chat = await e.get_chat()
        if e.is_group and sender.username:
            await uname_stuff(e.sender_id, sender.username, sender.first_name)
        elif e.is_private and chat.username:
            await uname_stuff(e.sender_id, chat.username, chat.first_name)
        if detector and is_profan(e.chat_id) and e.text:
            x, y = detector(e.text)
            if y:
                await e.delete()


@ultroid_bot.on(events.Raw(types.UpdateUserName))
async def uname_change(e):
    await uname_stuff(e.user_id, e.usernames[0] if e.usernames else None, e.first_name)


async def uname_stuff(id, uname, name):
    if udB.get_key("USERNAME_LOG"):
        old_ = udB.get_key("USERNAME_DB") or {}
        old = old_.get(id)
        # Ignore Name Logs
        if old and old == uname:
            return
        if old and uname:
            await asst.send_message(
                LOG_CHANNEL,
                get_string("can_2").format(old, uname),
            )
        elif old:
            await asst.send_message(
                LOG_CHANNEL,
                get_string("can_3").format(f"[{name}](tg://user?id={id})", old),
            )
        elif uname:
            await asst.send_message(
                LOG_CHANNEL,
                get_string("can_4").format(f"[{name}](tg://user?id={id})", uname),
            )

        old_[id] = uname
        udB.set_key("USERNAME_DB", old_)
