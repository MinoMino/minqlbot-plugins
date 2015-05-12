# minqlbot - A Quake Live server administrator bot.
# Copyright (C) 2015 Mino <mino@minomino.org>

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

class plugin_manager(minqlbot.Plugin):
    def __init__(self):
        self.add_command("load", self.cmd_load, 5, usage="<plugin>")
        self.add_command("unload", self.cmd_unload, 5, usage="<plugin>")
        self.add_command("reload", self.cmd_reload, 5, usage="<plugin>")
        self.add_command(("reload_config", "reloadconfig"), self.cmd_reload_config, 5)
    
    def cmd_load(self, player, msg, channel):
        if len(msg) < 2:
            channel.reply("^7Usage: ^6!load <plugin>")
        else:
            try:
                minqlbot.load_plugin(msg[1])
                channel.reply("^7Plugin ^6{} ^7has been successfully loaded."
                    .format(msg[1]))
            except:
                channel.reply("^7Plugin ^6{} ^7has failed to load."
                    .format(msg[1]))
                raise
    
    def cmd_unload(self, player, msg, channel):
        if len(msg) < 2:
            channel.reply("^7Usage: ^6!unload <plugin>")
        else:
            try:
                minqlbot.unload_plugin(msg[1])
                channel.reply("^7Plugin ^6{} ^7has been successfully unloaded."
                    .format(msg[1]))
            except:
                channel.reply("^7Plugin ^6{} ^7has failed to unload."
                    .format(msg[1]))
                raise
    
    def cmd_reload(self, player, msg, channel):
        if len(msg) < 2:
            channel.reply("^7Usage: ^6!reload <plugin>")
        else:
            try:
                minqlbot.reload_plugin(msg[1])
                channel.reply("^7Plugin ^6{} ^7has been successfully reloaded."
                    .format(msg[1]))
            except:
                channel.reply("^7Plugin ^6{} ^7has failed to reload."
                    .format(msg[1]))
                raise
    
    def cmd_reload_config(self, player, msg, channel):
        try:
            minqlbot.reload_config()
            channel.reply("^7The config file was reloaded successfully.")
        except:
            channel.reply("^7The config file has failed to reload.")
            raise
    
