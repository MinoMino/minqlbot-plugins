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

class permission(minqlbot.Plugin):
    def __init__(self):
        self.add_command("setperm", self.cmd_setperm, 5, usage="<name> <level>")
        self.add_command("getperm", self.cmd_getperm, 5, usage="<name>")
        self.add_command("myperm", self.cmd_myperm, 0, channels=("chat", "team_chat", "tell"))

    def cmd_setperm(self, player, msg, channel):
        if len(msg) < 3:
            return minqlbot.RET_USAGE
        else:
            self.set_permissions(msg[1].lower(), msg[2], channel)

    def cmd_getperm(self, player, msg, channel):
        if len(msg) < 2:
            return minqlbot.RET_USAGE
        
        perm = self.get_permission(msg[1].lower())
        if perm == None:
            channel.reply("^7I do not know ^6{}^7.".format(msg[1]))
        else:
            channel.reply("^6{}^7 has permission level ^6{}^7.".format(msg[1], perm))

    def cmd_myperm(self, player, msg, channel):
        name = player.clean_name.lower()
        perm = self.get_permission(name)
        if perm == None:
            channel.reply("^7I do not know you.")
        else:
            channel.reply("^7You have permission level ^6{}^7.".format(perm))
        
    def set_permissions(self, name, level, channel):
        lvl = 0
        try:
            lvl = int(level)
        except:
            channel.reply("^7Unintelligible permission level.")
            return
        
        c = self.db_query("SELECT * FROM Players WHERE name=?", name)
        if not c.fetchone():
            self.db_query("INSERT INTO Players VALUES(?, ?, '', 0, 0)", name, lvl)
            self.db_commit()
            channel.reply("^6{}^7 has been added as a player with permission level ^6{}^7."
                .format(name, lvl))
        else:
            self.db_query("UPDATE Players SET permission=? WHERE name=?", lvl, name)
            self.db_commit()
            channel.reply("^6{}^7's permission level has been set to ^6{}^7."
                .format(name, lvl))

        
