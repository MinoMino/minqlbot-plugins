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

class fun(minqlbot.Plugin):
	def __init__(self):
		self.add_command("cookies", self.cmd_cookies)
		self.add_command("<3", self.cmd_heart)

	def cmd_cookies(self, player, msg, channel):
		channel.reply("^7For me? Thank you, {}!".format(player))

	def cmd_heart(self, player, msg, channel):
		s = ("^1\r oo   oo"
             "\no  o o  o"
             "\no   o   o"
             "\n o     o"
             "\n  o   o"
             "\n   o o"
             "\n    o")
		self.msg(s.replace("o", "\x08"))