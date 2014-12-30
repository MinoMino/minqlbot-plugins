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

class alias(minqlbot.Plugin):
    def __init__(self):
        super().__init__()
        self.add_command(("add_alias", "addalias", "set_alias", "setalias"), self.cmd_add_alias, 3, usage="<full_name> <full_alias>")
        self.add_command(("remove_alias", "remalias"), self.cmd_remove_alias, 3, usage="<full_name> <full_alias>")
        self.add_command(("get_alias", "getalias", "check_alias", "checkalias"), self.cmd_get_alias, 3, usage="<full_name>")
        
    def cmd_add_alias(self, player, msg, channel):
        if len(msg) < 3:
            return minqlbot.RET_USAGE
        
        real = self.clean_text(msg[1]).lower()
        fake = self.clean_text(msg[2]).lower()
        
        c = self.db_query("SELECT * FROM Players WHERE name=?", real)
        if not c.fetchone():
            self.db_query("INSERT INTO Players VALUES(?, 0, '', 0, 0)", real)
            self.db_commit()
        
        c = self.db_query("SELECT * FROM Aliases WHERE name=? AND other_name=?", real, fake)
        if not c.fetchone():
            self.db_query("INSERT INTO Aliases VALUES(?, ?)", real, fake)
            self.db_commit()
            channel.reply("^6{}^7 will now be treated as ^6{}^7 in the context of balance."
                .format(msg[2], msg[1]))
            self.remove_name_from_balance_cache(fake)
        else:
            channel.reply("^7I already know that.")
    
    def cmd_remove_alias(self, player, msg, channel):
        if len(msg) < 3:
            return minqlbot.RET_USAGE
        
        real = self.clean_text(msg[1]).lower()
        fake = self.clean_text(msg[2]).lower()
        
        c = self.db_query("DELETE FROM Aliases WHERE name=? AND other_name=?", real, fake)
        if c.rowcount:
            self.db_commit()
            channel.reply("^7Alias has been deleted.")
            self.remove_name_from_balance_cache(fake)
        else:
            channel.reply("^7There are no aliases matching your arguments.")

    def cmd_get_alias(self, player, msg, channel):
        if len(msg) < 2:
            return minqlbot.RET_USAGE
        
        who = self.clean_text(msg[1]).lower()
        
        c = self.db_query("SELECT other_name FROM Aliases WHERE name=?", who)
        res = c.fetchmany(10)
        if res:
            aliases = ", ".join([row["other_name"] for row in res])
            channel.reply("^6{}^7 is also known as: ^6{}".format(who, aliases))
        else:
            c = self.db_query("SELECT name FROM Aliases WHERE other_name=?", who)
            row = c.fetchone()
            if row:
                channel.reply("^6{}^7 is an alias of ^6{}^7.".format(msg[1], row["name"]))
            else:
                channel.reply("^7Sorry, I don't know of any.")

    def remove_name_from_balance_cache(self, name):
        if "balance" in self.plugins:
            self.debug(name)
            self.debug([key for key in self.plugins["balance"].cache])
            if name in self.plugins["balance"].cache:
                with self.plugins["balance"].lock: # Gotta use the lock!
                    self.debug("Removed {} from balance's rating cache!".format(name))
                    del self.plugins["balance"].cache[name]
    