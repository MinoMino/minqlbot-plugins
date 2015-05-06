# minqlbot - A Quake Live server administrator bot.
# Copyright (C) Mino <mino@minomino.org>

# This file is part of minqlbot.

# minqlbot is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# minqlbot is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with minqlbot. If not, see <http://www.gnu.org/licenses/>.

import datetime
import re
import minqlbot

LENGTH_REGEX = re.compile(r"(?P<number>[0-9]+) (?P<scale>seconds?|minutes?|hours?|days?|weeks?|months?|years?)")
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_REASON = "Reason not specified."

class silence(minqlbot.Plugin):
    def __init__(self):
        super().__init__()
        self.add_hook("player_connect", self.handle_player_connect)
        self.add_hook("bot_connect", self.handle_bot_connect)
        self.add_command("silence", self.cmd_silence, 1, usage="<full_name> <length> seconds|minutes|hours|days|... [reason]")
        self.add_command("unsilence", self.cmd_unsilence, 1, usage="<full_name>")
        self.add_command("checksilence", self.cmd_checksilence, usage="<full_name>")
    
    def handle_player_connect(self, player):
        res = self.is_silenced(player.name)
        if res:
            player.mute()

            if res and res[1] == DEFAULT_REASON:
                self.delay(30, lambda: player.tell("^7You've been silenced until ^6{}^7.".format(res[0])))
            elif res:
                self.delay(30, lambda: player.tell("^7You've been silenced until ^6{}^7 for the following reason: ^6{}.".format(*res)))

    def handle_bot_connect(self):
        for player in self.players():
            if self.is_silenced(player.name):
                player.mute()

    def cmd_silence(self, player, msg, channel):
        if len(msg) < 4:
            return minqlbot.RET_USAGE

        name = self.clean_text(msg[1])
        if self.has_permission(name, 1):
            channel.reply("^6{}^7 has elevated permissions and cannot be silenced.".format(name))
            return

        if len(msg) > 4:
            reason = " ".join(msg[4:])
        else:
            reason = DEFAULT_REASON

        c = self.db_query("SELECT * FROM Players WHERE name=?", name.lower())
        if not c.fetchone():
            self.db_query("INSERT INTO Players VALUES(?, 0, '', 0, 0)", name.lower())
            self.db_commit()
        
        r = LENGTH_REGEX.match(" ".join(msg[2:4]).lower())
        if r:
            number = float(r.group("number"))
            if number <= 0: return
            scale = r.group("scale").rstrip("s")
            td = None
            
            if scale == "second":
                td = datetime.timedelta(seconds=number)
            elif scale == "minute":
                td = datetime.timedelta(minutes=number)
            elif scale == "hour":
                td = datetime.timedelta(hours=number)
            elif scale == "day":
                td = datetime.timedelta(days=number)
            elif scale == "week":
                td = datetime.timedelta(weeks=number)
            elif scale == "month":
                td = datetime.timedelta(days=number * 30)
            elif scale == "year":
                td = datetime.timedelta(weeks=number * 52)
            
            now = datetime.datetime.now().strftime(TIME_FORMAT)
            expires = (datetime.datetime.now() + td).strftime(TIME_FORMAT)
            self.db_query("INSERT INTO Silences VALUES(?, ?, ?, 1, ?)", name.lower(), now, expires, reason)
            self.db_commit()
            self.mute(name)
            channel.reply("^6{} ^7has been silenced. The silence expires on ^6{}^7.".format(name, expires))
            return

    def cmd_unsilence(self, player, msg, channel):
        if len(msg) < 2:
            return minqlbot.RET_USAGE

        name = self.clean_text(msg[1])
        c = self.db_query("SELECT * FROM Silences WHERE name=?", name.lower())
        unsilenced = False
        for row in c:
            if row[3]: # if active silence
                self.db_query("UPDATE Silences SET active=0 WHERE name=? AND issued=?", row[0], row[1])
                self.db_commit()
                unsilenced = True
        
        if unsilenced:
            channel.reply("^6{}^7 has been unsilenced.".format(name))
        else:
            channel.reply("^7There is no active silence on ^6{}^7.".format(name))

    def cmd_checksilence(self, player, msg, channel):
        if len(msg) < 2:
            return minqlbot.RET_USAGE

        res = self.is_silenced(msg[1])
        if res and res[1] == DEFAULT_REASON:
            channel.reply("^6{}^7 is silenced until ^6{}^7.".format(msg[1], res[0]))
        elif res:
            channel.reply("^6{}^7 is silenced until ^6{}^7 for the follow reason:^6 {}".format(msg[1], *res))
        else:
            channel.reply("^6{} ^7is not silenced.".format(msg[1]))


    # ====================================================================
    #                               HELPERS
    # ====================================================================

    def is_silenced(self, name):
        clean = self.clean_name(name).lower()
        c = self.db_query("SELECT * FROM Silences WHERE name=?", clean)
        for row in c:
            if clean == row["name"] and row["active"]:
                expires = datetime.datetime.strptime(row["expires"], TIME_FORMAT)
                if (expires - datetime.datetime.now()).total_seconds() > 0:
                    return row["expires"], row["reason"]
        return None

