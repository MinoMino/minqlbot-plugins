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

"""Lists all the players in the game and their ratings. Needs the "balance" plugin to work. """

import minqlbot

class serverratings(minqlbot.Plugin):
    def __init__(self):
        super().__init__()
        self.add_command(("ratings", "elos", "selo"), self.cmd_ratings)

    def cmd_ratings(self, player, msg, channel):
        """Lists every player in the game's rating in the current game mode."""
        if "balance" not in self.plugins:
            return

        teams = self.teams()
        teams = teams["red"] + teams["blue"]
        self.print_ratings(teams, channel, self.game().short_type)

    def print_ratings(self, names, channel, game_type):
        balance = self.plugins["balance"]

        not_cached = balance.not_cached(game_type, names)
        if not_cached:
            with balance.rlock:
                for lookup in balance.lookups:
                    for n in balance.lookups[lookup][1]:
                        if n in not_cached:
                            not_cached.remove(n)
                if not_cached:
                    balance.fetch_player_ratings(not_cached, channel, game_type)
                if (self.print_ratings, (names, channel, game_type)) not in balance.pending:
                    balance.pending.append((self.print_ratings, (names, channel, game_type)))
                return False

        teams = self.teams()
        red_sorted = sorted(teams["red"], key=lambda x: balance.cache[x.clean_name.lower()][game_type]["elo"], reverse=True)
        blue_sorted = sorted(teams["blue"], key=lambda x: balance.cache[x.clean_name.lower()][game_type]["elo"], reverse=True)
        red = "^7" + ", ".join(["{}: ^1{}^7".format(p, balance.cache[p.clean_name.lower()][game_type]["elo"]) for p in red_sorted])
        blue = "^7" + ", ".join(["{}: ^4{}^7".format(p, balance.cache[p.clean_name.lower()][game_type]["elo"]) for p in blue_sorted])

        channel.reply(red)
        channel.reply(blue)
        return True
