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

#Some essential functions.

import minqlbot
import datetime
import re

DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
TIME_FORMAT = "%H:%M:%S"

class essentials(minqlbot.Plugin):
    def __init__(self):
        super().__init__()
        self.add_hook("player_connect", self.handle_player_connect)
        self.add_hook("player_disconnect", self.handle_player_disconnect)
        self.add_hook("bot_connect", self.handle_bot_connect)
        self.add_hook("vote_called", self.handle_vote_called)
        self.add_hook("vote_ended", self.handle_vote_ended)
        self.add_command("kick", self.cmd_kick, 2, usage="<name>")
        self.add_command("kickban", self.cmd_kickban, 2, usage="<name>")
        self.add_command("yes", self.cmd_yes, 2)
        self.add_command("no", self.cmd_no, 2)
        self.add_command("switch", self.cmd_switch, 1, usage="<name> <name>")
        self.add_command("red", self.cmd_red, 1, usage="<name>")
        self.add_command("blue", self.cmd_blue, 1, usage="<name>")
        self.add_command(("spectate", "spec", "spectator"), self.cmd_spectate, 1, usage="<name>")
        self.add_command("opme", self.cmd_opme, 3, channels=("chat", "team_chat", "tell"))
        self.add_command("deopme", self.cmd_deopme, channels=("chat", "team_chat", "tell"))
        self.add_command("op", self.cmd_op, 3, usage="<name>")
        self.add_command("deop", self.cmd_deop, 3, usage="<name>")
        self.add_command("mute", self.cmd_mute, 1, usage="<name>")
        self.add_command("unmute", self.cmd_unmute, 1, usage="<name>")
        self.add_command("allready", self.cmd_allready, 2)
        self.add_command("abort", self.cmd_abort, 2)
        self.add_command("shuffle", self.cmd_shuffle, 1)
        self.add_command("cointoss", self.cmd_cointoss, 1)
        self.add_command("ruleset", self.cmd_ruleset, 3, usage="<ruleset>")
        self.add_command("map", self.cmd_map, 2, usage="<mapname>")
        self.add_command("opsay", self.cmd_opsay, 3, usage="<message>")
        self.add_command(("help", "about", "commands"), self.cmd_help)
        self.add_command("db", self.cmd_db, 5, usage="<query>")
        self.add_command("seen", self.cmd_seen, usage="<full_name>")
        self.add_command("time", self.cmd_time, usage="[timezone_offset]")
        self.add_command(("teamsize", "ts"), self.cmd_teamsize, 2, usage="<size>")
        self.add_command("exit", self.cmd_exit, 5)

        self.vote_resolve_timer = None

    def handle_player_connect(self, player):
        self.update_player(player)

    def handle_player_disconnect(self, player, reason):
        self.update_player(player)

    def handle_bot_connect(self):
        """When we connect to a server with players, update 'last_seen' of all players.

        """
        for player in self.players():
            self.update_player(player)

    def handle_vote_called(self, caller, vote, args):
        config = minqlbot.get_config()
        if "Essentials" in config and "AutoPassMajorityVote" in config["Essentials"]:
            auto_pass = config["Essentials"].getboolean("AutoPassMajorityVote")
            if auto_pass:
                self.vote_resolve_timer = self.delay(27.5, self.resolve_vote)

        # Enforce teamsizes.
        if vote == "teamsize":
            args = int(args)
            if "Essentials" in config and "MaximumTeamsize" in config["Essentials"]:
                max_teamsize = int(config["Essentials"]["MaximumTeamsize"])
                if args > max_teamsize:
                    self.vote_no()

            if "Essentials" in config and "MinimumTeamsize" in config["Essentials"]:
                min_teamsize = int(config["Essentials"]["MinimumTeamsize"])
                if args < min_teamsize:
                    self.vote_no()
        elif vote == "kick":
            if args == minqlbot.NAME.lower():
                self.vote_no()

    def handle_vote_ended(self, vote, args, vote_count, passed):
        if self.vote_resolve_timer and self.vote_resolve_timer.is_alive():
            self.vote_resolve_timer.cancel()

        if passed == None: # Vote was cancelled.
            self.msg("^7RIP vote.")

    def cmd_kick(self, player, msg, channel):
        if len(msg) < 2:
            return minqlbot.RET_USAGE

        n = self.find_player(msg[1])
        if n:
            if not self.kick(n):
                channel.reply("^7Try again after the current vote.")
        else:
            channel.reply("^7I do not know '{}'.".format(msg[1]))

    def cmd_kickban(self, player, msg, channel):
        if len(msg) < 2:
            return minqlbot.RET_USAGE

        n = self.find_player(msg[1])
        if n:
            self.kickban(n)
        else:
            channel.reply("^7I do not know '{}'.".format(msg[1]))

    def cmd_yes(self, player, msg, channel):
        if self.is_vote_active():
            self.vote_yes()
        else:
            channel.reply("^7There's no active vote!")

    def cmd_no(self, player, msg, channel):
        if self.is_vote_active():
            self.vote_no()
        else:
            channel.reply("^7There's no active vote!")

    def cmd_switch(self, player, msg, channel):
        if len(msg) < 3:
            return minqlbot.RET_USAGE

        n1 = self.find_player(msg[1])
        n2 = self.find_player(msg[2])
        if n1 and n2:
            if not self.switch(n1, n2):
                channel.reply("^7I can't switch those players.")
        elif n1 and not n2:
            channel.reply("^7I do not know '{}'.".format(msg[1]))
        elif n2 and not n1:
            channel.reply("^7I do not know '{}'.".format(msg[2]))
        else:
            channel.reply("^7I do not know '{}' nor '{}'.".format(msg[1], msg[2]))
            
    def cmd_red(self, player, msg, channel):
        if len(msg) < 2:
            return minqlbot.RET_USAGE

        n = self.find_player(msg[1])
        if n:
            self.put(n, "red")
        else:
            channel.reply("^7I do not know '{}'.".format(msg[1]))

    def cmd_blue(self, player, msg, channel):
        if len(msg) < 2:
            return minqlbot.RET_USAGE

        n = self.find_player(msg[1])
        if n:
            self.put(n, "blue")
        else:
            channel.reply("^7I do not know '{}'.".format(msg[1]))

    def cmd_spectate(self, player, msg, channel):
        if len(msg) < 2:
            return minqlbot.RET_USAGE

        n = self.find_player(msg[1])
        if n:
            self.put(n, "spectator")
        else:
            channel.reply("^7I do not know '{}'.".format(msg[1]))
        
    def cmd_opme(self, player, msg, channel):
        self.op(player)

    def cmd_deopme(self, player, msg, channel):
        self.deop(player)

    def cmd_op(self, player, msg, channel):
        if len(msg) < 2:
            return minqlbot.RET_USAGE

        n = self.find_player(msg[1])
        if n:
            self.op(n)
        else:
            channel.reply("^7I do not know '{}'.".format(msg[1]))

    def cmd_deop(self, player, msg, channel):
        if len(msg) < 2:
            return minqlbot.RET_USAGE

        n = self.find_player(msg[1])
        if n:
            self.deop(n)
        else:
            channel.reply("^7I do not know '{}'.".format(msg[1]))

    def cmd_mute(self, player, msg, channel):
        if len(msg) < 2:
            return minqlbot.RET_USAGE

        n = self.find_player(msg[1])
        if n:
            self.mute(n)
        else:
            channel.reply("^7I do not know '{}'.".format(msg[1]))

    def cmd_unmute(self, player, msg, channel):
        if len(msg) < 2:
            return minqlbot.RET_USAGE

        n = self.find_player(msg[1])
        if n:
            self.unmute(n)
        else:
            channel.reply("^7I do not know '{}'.".format(msg[1]))
    
    def cmd_allready(self, player, msg, channel):
        if self.game().state == "warmup":
            self.allready()
        else:
            channel.reply("^7But the game's already on!")
        
    def cmd_abort(self, player, msg, channel):
        if self.game().state == "in_progress":
            self.abort()
        else:
            channel.reply("^7But the game isn't even on!")
    
    def cmd_shuffle(self, player, msg, channel):
        if not self.shuffle():
            channel.reply("^7Try again after the current vote.")
    
    def cmd_cointoss(self, player, msg, channel):
        if not self.cointoss():
            channel.reply("^7Try again after the current vote.")

    def cmd_ruleset(self, player, msg, channel):
        if len(msg) < 2:
            return minqlbot.RET_USAGE
        elif not self.ruleset(msg[1]):
            channel.reply("^7Try again after the current vote.")
    
    def cmd_map(self, player, msg, channel):
        if len(msg) < 2:
            return minqlbot.RET_USAGE
        elif not self.changemap(msg[1]):
            channel.reply("^7Try again after the current vote.")

    def cmd_opsay(self, player, msg, channel):
        if len(msg) < 2:
            return minqlbot.RET_USAGE

        self.opsay(" ".join(msg[1:]))
        
    def cmd_help(self, player, msg, channel):
        channel.reply("^7minqlbot {} - See ^6http://github.com/MinoMino/minqlbot ^7for more info."
            .format(minqlbot.__version__))
    
    def cmd_db(self, player, msg, channel):
        if len(msg) == 1:
            return minqlbot.RET_USAGE
        
        try:
            query = " ".join(msg[1:])
            c = self.db_query(query)
            self.db_commit()
            columns_printed = False
            for row in c:
                if not columns_printed:
                    channel.reply("^7{}".format(row.keys()))
                    columns_printed = True
                channel.reply("^7{}".format(tuple(row)))

            if not columns_printed and query.lower().startswith("select"):
                channel.reply("^7Your query yielded no results.")
        except Exception as e:
            channel.reply("^1{}^7: {}".format(e.__class__.__name__, e))
            raise

    def cmd_seen(self, player, msg, channel):
        if len(msg) < 2:
            return minqlbot.RET_USAGE
            
        name = self.clean_text(msg[1]).lower()
        if name == minqlbot.NAME.lower():
            channel.reply("^7Does taking a selfie count?")
        elif name == player.clean_name.lower():
            channel.reply("^7Depends. Are you ^6hot^7?")
        elif self.player(name):
            channel.reply("^7But that player's already here, you ^6dummy^7!")
        else:
            c = self.db_query("SELECT last_seen FROM Players WHERE name=?", name)
            row = c.fetchone()
            if row and row["last_seen"]:
                then = datetime.datetime.strptime(row["last_seen"], DATETIME_FORMAT)
                td = datetime.datetime.now() - then
                r = re.match(r'((?P<d>.*) days*, )?(?P<h>..?):(?P<m>..?):.+', str(td))
                if r.group("d"):
                    channel.reply("^7I saw {} ^6{}^7 day(s), ^6{}^7 hour(s) and ^6{}^7 minute(s) ago."
                        .format(name, r.group("d"), r.group("h"), r.group("m")))
                else:
                    channel.reply("^7I saw {} ^6{}^7 hour(s) and ^6{}^7 minute(s) ago."
                        .format(name, r.group("h"), r.group("m")))
            else:
                channel.reply("^7I have never seen ^6{}^7 before.".format(name))

    def cmd_time(self, player, msg, channel):
        tz_offset = 0
        if len(msg) > 1:
            try:
                tz_offset = int(msg[1])
            except ValueError:
                channel.reply("^7Unintelligible time zone offset.")
                return
        tz = datetime.timezone(offset=datetime.timedelta(hours=tz_offset))
        now = datetime.datetime.now(tz)
        if tz_offset > 0:
            channel.reply("^7The current time is: ^6{} UTC+{}"
                .format(now.strftime(TIME_FORMAT), tz_offset))
        elif tz_offset < 0:
            channel.reply("^7The current time is: ^6{} UTC{}"
                .format(now.strftime(TIME_FORMAT), tz_offset))
        else:
            channel.reply("^7The current time is: ^6{} UTC"
                .format(now.strftime(TIME_FORMAT)))

    def cmd_teamsize(self, player, msg, channel):
        if len(msg) < 2:
            return minqlbot.RET_USAGE
        
        try:
            n = int(msg[1])
        except ValueError:
            channel.reply("^7Unintelligible size.")
        
        if not self.teamsize(n):
            channel.reply("^7Try again after the current vote.")

    def cmd_exit(self, player, msg, channel):
        #TODO: IMPLEMENT
        pass

    # ====================================================================
    #                               HELPERS
    # ====================================================================

    def update_player(self, player):
        """Updates the 'last_seen' entry in the database or add to database if it's a new player.

        """
        name = player.clean_name.lower()
        c = self.db_query("SELECT * FROM Players WHERE name=?", name)
        row = c.fetchone()
        now = datetime.datetime.now().strftime(DATETIME_FORMAT)
        if not row:
            self.db_query("INSERT INTO Players VALUES(?, 0, ?, 0, 0)", name, now)
            self.db_commit()
            return
        else:
            self.db_query("UPDATE Players SET last_seen=? WHERE name=?", now, name)
            self.db_commit()

    def resolve_vote(self):
        self.debug("RESOLVE")
        votes = self.current_vote_count()
        if not votes:
            self.debug("resolve_votes: Where'd the votes go?")
        elif votes[0] > votes[1]:
            self.vote_yes()
            self.msg("^7Result: ^6{}^7 - {}".format(votes[0], votes[1]))
