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

import minqlbot
import time

class motd(minqlbot.Plugin):
    def __init__(self):
        super().__init__()
        self.add_hook("player_connect", self.handle_player_connect, minqlbot.PRI_LOWEST)
        self.add_command("motd", self.cmd_motd, 4, usage="(set <motd> | add <motd> | clear | get)")

    def handle_player_connect(self, player):
        """Send the message of the day to the player in a tell.

        This should be set to lowest priority so that we don't execute anything if "ban" or
        a similar plugin determines the player should be kicked.
        """
        c = self.db_query("SELECT message FROM Motd ORDER BY time DESC LIMIT 1")
        row = c.fetchone()
        if row and row["message"]:
            self.delay(15, self.tell_motd, args=(player, row["message"]))

    def cmd_motd(self, player, msg, channel):
        if len(msg) < 2:
            return minqlbot.RET_USAGE
        # NEW
        elif msg[1].lower() == "set" or msg[1].lower() == "new":
            new_motd = " ".join(msg[2:])
            self.db_query("INSERT INTO Motd VALUES(?, ?, ?)", int(time.time()), player.clean_name.lower(), new_motd)
            self.db_commit()
            channel.reply("^7You have successfully set a new MOTD.")
        # ADD
        elif msg[1].lower() == "add":
            c = self.db_query("SELECT message FROM Motd ORDER BY time DESC LIMIT 1")
            row = c.fetchone()
            if row and row["message"]:
                add_motd = "{} {}".format(row["message"], " ".join(msg[2:]))
                self.db_query("INSERT INTO Motd VALUES(?, ?, ?)", int(time.time()), player.clean_name.lower(), add_motd)
                self.db_commit()
                channel.reply("^7The current MOTD has been successfully updated.")
            else:
                channel.reply("^7There is no active MOTD.")
        # CLEAR
        elif msg[1].lower() == "clear":
            self.db_query("INSERT INTO Motd VALUES(?, ?, ?)", int(time.time()), player.clean_name.lower(), "")
            self.db_commit()
            channel.reply("^7You have successfully cleared the MOTD.")
        # GET
        elif msg[1].lower() == "get":
            c = self.db_query("SELECT message FROM Motd ORDER BY time DESC LIMIT 1")
            row = c.fetchone()
            if row and row["message"]:
                channel.reply("^7The current MOTD: ^2{}".format(row["message"]))
            else:
                channel.reply("^7There is no active MOTD.")
    
    def tell_motd(self, player, msg):
        self.tell("^6*** ^7Message of the Day ^6***", player)
        self.tell(msg, player)

