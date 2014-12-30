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

class raw(minqlbot.Plugin):
    def __init__(self):
        self.add_hook("raw", self.handle_raw)
        self.add_command("exec", self.cmd_exec, 5, usage="<command>")
        self.add_command("raw", self.cmd_raw, 5, usage="<command>")
        self.add_command("rawdbg", self.cmd_rawdbg, 5)

        self.is_log_raw = minqlbot.IS_DEBUG

    def handle_raw(self, cmd):
        if self.is_log_raw and not cmd.startswith("tinfo"):
            self.debug(cmd)

    def cmd_exec(self, player, msg, channel):
        if len(msg) < 2:
            return minqlbot.RET_USAGE
        else:
            try:
                exec(" ".join(msg[1:]))
            except Exception as e:
                channel.reply("^1{}^7: {}".format(e.__class__.__name__, e))
                raise

    def cmd_raw(self, player, msg, channel):
        if len(msg) < 2:
            return minqlbot.RET_USAGE
        else:
            self.send_command(" ".join(msg[1:]))

    def cmd_rawdbg(self, player, msg, channel):
        if self.is_log_raw:
            self.is_log_raw = False
            channel.reply("^7Raw debugging is off!")
        else:
            self.is_log_raw = True
            channel.reply("^7Raw debugging is on!")
