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
import plugins.qlprofile as qlprofile
import minqlbot
import threading
import traceback

LENGTH_REGEX = re.compile(r"(?P<number>[0-9]+) (?P<scale>seconds?|minutes?|hours?|days?|weeks?|months?|years?)")
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_REASON = "Reason not specified."

class ban(minqlbot.Plugin):
    def __init__(self):
        super().__init__()
        self.add_hook("player_connect", self.handle_player_connect, minqlbot.PRI_HIGH)
        self.add_hook("player_disconnect", self.handle_player_disconnect)
        self.add_hook("game_countdown", self.handle_game_countdown)
        self.add_hook("bot_connect", self.handle_bot_connect)
        self.add_hook("game_start", self.handle_game_start)
        self.add_hook("game_end", self.handle_game_end)
        self.add_hook("team_switch", self.handle_team_switch)
        self.add_hook("vote_called", self.handle_vote_called)
        self.add_command("ban", self.cmd_ban, 2, usage="<full_name> <length> seconds|minutes|hours|days|... [reason]")
        self.add_command("unban", self.cmd_unban, 2, usage="<full_name>")
        self.add_command("checkban", self.cmd_checkban, usage="<full_name>")
        self.add_command("forgive", self.cmd_forgive, 2, usage="<full_name> [leaves_to_forgive]")

        # List of players playing that could potentially be considered leavers.
        self.players_start = []

        # We flag players who ought to be kickbanned, but since we delay it, we keep
        # a list of players who are flagged and prevent them from starting votes or joining.
        self.ban_flagged = []
        self.ban_flagged_lock = threading.RLock()
    
    def handle_player_connect(self, player):
        status = self.leave_status(player.name)
        # Check if a player has been banned for leaving, if we're doing that.
        if status and status[0] == "ban":
            self.flag_player(player)
            player.mute()
            self.delay(20, lambda: player.tell("^7You have been banned from this server for leaving too many games."))
            self.delay(60, player.kickban)
            # Stop plugins on lowest priority from triggering this event since we're kicking.
            return minqlbot.RET_STOP
        # Check if player needs to be warned.
        elif status and status[0] == "warn":
            self.delay(12, self.warn_player, args=(player, status[1]))
        # Check if a player has been banned manually.
        elif self.is_banned(player.name):
            self.flag_player(player)
            self.delay(5, player.kickban)
            # Stop plugins on lower priority from triggering this event since we're kicking.
            return minqlbot.RET_STOP

        config = minqlbot.get_config()
        if "Ban" in config and "MinimumDaysRegistered" in config["Ban"]:
            days = int(config["Ban"]["MinimumDaysRegistered"])
            if days > 0:
                threading.Thread(target=self.get_profile_thread, args=(player, days)).start()

    def handle_player_disconnect(self, player, reason):
        # Allow people to disconnect without getting a leave if teams are uneven.
        teams = self.teams()
        if len(teams["red"] + teams["blue"]) % 2 == 0 and player in self.players_start:
            self.players_start.remove(player)
        
        if player in self.ban_flagged:
            self.unflag_player(player)

    def handle_game_countdown(self):
        if self.is_leaver_banning():
            self.msg("^7Leavers are being kept track of. Repeat offenders ^6will^7 be banned.")

    def handle_bot_connect(self):
        if self.game().state == "in_progress":
            self.players_start = []
            teams = self.teams()
            self.players_start = teams["red"] + teams["blue"]

    def handle_game_start(self, game):
        self.players_start = []
        teams = self.teams()
        self.players_start = teams["red"] + teams["blue"]

    def handle_game_end(self, game, score, winner):
        teams = self.teams()
        players_end = teams["red"] + teams["blue"]
        leavers = []

        for player in self.players_start.copy():
            if player not in players_end:
                # Populate player list.
                leavers.append(player)
                # Remove leavers from initial list so we can use it to award games completed.
                self.players_start.remove(player)

        self.db_querymany("UPDATE players SET games_completed=games_completed+1 WHERE name=?",
            *[(p.clean_name.lower(),) for p in self.players_start])
        self.db_querymany("UPDATE players SET games_left=games_left+1 WHERE name=?",
            *[(p.clean_name.lower(),) for p in leavers])
        self.db_commit()

        if leavers:
            self.msg("^7Leavers: ^6{}".format(" ".join([p.clean_name for p in leavers])))
            self.players_start = []

    def handle_team_switch(self, player, old_team, new_team):
        # Prevent flagged players from joining.
        if self.is_flagged(player) and old_team == "spectator":
            player.put("spectator")

        # Allow people to spectate without getting a leave if teams are uneven.
        if (old_team == "red" or old_team == "blue") and new_team == "spectator":
            teams = self.teams()
            if len(teams["red"] + teams["blue"]) % 2 == 0 and player in self.players_start:
                self.players_start.remove(player)
        # Add people to the list of participating players if they join mid-game.
        if (old_team == "spectator" and (new_team == "red" or new_team == "blue") and
         self.game().state == "in_progress" and player not in self.players_start):
            self.players_start.append(player)

    def handle_vote_called(self, caller, vote, args):
        if self.is_flagged(caller):
            self.vote_no()

    def cmd_ban(self, player, msg, channel):
        """Bans a player temporarily. A very long period works for all intents and
        purposes as a permanent ban, so there's no separate command for that.

        Example #1: !ban Mino 1 day Very rude!

        Example #2: !ban sponge 50 years"""
        if len(msg) < 4:
            return minqlbot.RET_USAGE

        name = self.clean_text(msg[1])
        # Permission level 5 players not bannable.
        if self.has_permission(name, 5):
            channel.reply("^6{}^7 has permission level 5 and cannot be banned.".format(name))
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
            self.db_query("INSERT INTO Bans VALUES(?, ?, ?, 1, ?)", name.lower(), now, expires, reason)
            self.db_commit()
            self.kickban(name)
            channel.reply("^6{} ^7has been banned. Ban expires on ^6{}^7.".format(name, expires))
            return

    def cmd_unban(self, player, msg, channel):
        """Unbans a player if banned."""
        if len(msg) < 2:
            return minqlbot.RET_USAGE

        name = self.clean_text(msg[1])
        c = self.db_query("SELECT * FROM Bans WHERE name=?", name.lower())
        unbanned = False
        for row in c:
            if row[3]: # if active ban
                self.db_query("UPDATE Bans SET active=0 WHERE name=? AND issued=?", row[0], row[1])
                self.db_commit()
                unbanned = True
        
        if unbanned:
            channel.reply("^6{}^7 has been unbanned.".format(name))
        else:
            channel.reply("^7 No active bans on ^6{}^7 found.".format(name))

    def cmd_checkban(self, player, msg, channel):
        """Checks whether a player has been banned, and if so, why."""
        if len(msg) < 2:
            return minqlbot.RET_USAGE

        # Check manual bans first.
        res = self.is_banned(msg[1])
        if res and res[1] == DEFAULT_REASON:
            channel.reply("^6{}^7 is banned until ^6{}^7.".format(msg[1], res[0]))
            return
        elif res:
            channel.reply("^6{}^7 is banned until ^6{}^7 for the follow reason:^6 {}".format(msg[1], *res))
            return
        elif self.is_leaver_banning():
            status = self.leave_status(msg[1])
            if status and status[0] == "ban":
                channel.reply("^6{} ^7is banned for having left too many games.".format(msg[1]))
                return
        
        channel.reply("^6{} ^7is not banned.".format(msg[1]))

    def cmd_forgive(self, player, msg, channel):
        """Removes a leave from a player. Optional integer can be provided to remove multiple leaves."""
        if len(msg) < 2:
            return minqlbot.RET_USAGE

        c = self.db_query("SELECT games_left FROM Players WHERE name=?", msg[1])
        row = c.fetchone()
        if not row:
            channel.reply("^7I do not know^6 {}^7.".format(msg[1]))
            return
        elif row["games_left"] <= 0:
            channel.reply("^6{}^7's leaves are already at ^6{}^7.".format(msg[1], row["games_left"]))
            return

        if len(msg) == 2:
            leaves_to_forgive = 1
        else:
            try:
                leaves_to_forgive = int(msg[2])
            except ValueError:
                channel.reply("^7Unintelligible number of leaves to forgive. Please use numbers.")
                return

        new_leaves = row["games_left"] - leaves_to_forgive
        if new_leaves < 0:
            forgiven = row["games_left"]
        else:
            forgiven = leaves_to_forgive

        self.db_query("UPDATE Players SET games_left=games_left-? WHERE name=?", forgiven, msg[1])
        self.db_commit()
        channel.reply("^7^6{}^7 games have been forgiven, putting ^6{}^7 at ^6{}^7 leaves."
            .format(forgiven, msg[1], row["games_left"] - forgiven))


    # ====================================================================
    #                               HELPERS
    # ====================================================================

    def is_banned(self, name):
        clean = self.clean_name(name).lower()
        c = self.db_query("SELECT * FROM Bans WHERE name=?", clean)
        for row in c:
            if clean == row["name"] and row["active"]:
                expires = datetime.datetime.strptime(row["expires"], TIME_FORMAT)
                if (expires - datetime.datetime.now()).total_seconds() > 0:
                    return row["expires"], row["reason"]
        return None
    
    def get_profile_thread(self, player, days):
        try:
            pro = qlprofile.get_profile(player.clean_name)
            if not pro.is_eligible(days):
                self.flag_player(player)
                player.mute()
                self.delay(20, lambda: player.tell("^7Sorry, but your account is too new to play here. You will be kicked shortly."))
                self.delay(60, player.kickban)
        except:
            e = traceback.format_exc().rstrip("\n")
            self.debug("========== ERROR: {}@get_profile_thread ==========".format(self.__class__.__name__))
            for line in e.split("\n"):
                self.debug(line)

    def is_leaver_banning(self):
        config = minqlbot.get_config()

        if ("Ban" in config and
            "AutomaticLeaveBan" in config["Ban"] and
            config["Ban"].getboolean("AutomaticLeaveBan") and
            "MinimumGamesPlayedBeforeBan" in config["Ban"] and
            "WarnThreshold" in config["Ban"] and
            "BanThreshold" in config["Ban"]):
            return True
        else:
            return False

    def leave_status(self, name):
        """Get a player's status when it comes to leaving, given automatic leaver ban is on.

        """
        if not self.is_leaver_banning():
            return None

        c = self.db_query("SELECT * FROM Players WHERE name=?", self.clean_name(name).lower())
        row = c.fetchone()
        if not row:
            return None

        config = minqlbot.get_config()
        
        min_games_completed = int(config["Ban"]["MinimumGamesPlayedBeforeBan"])
        warn_threshold = float(config["Ban"]["WarnThreshold"])
        ban_threshold = float(config["Ban"]["BanThreshold"])

        # Check their games completed to total games ratio.
        total = row["games_completed"] + row["games_left"]
        if not total:
            return None
        elif total < min_games_completed:
            # If they have played less than the minimum, check if they can possibly recover by the time
            # they have played the minimum amount of games.
            ratio = (row["games_completed"] + (min_games_completed - total)) / min_games_completed
        else:
            ratio = row["games_completed"] / total
            
        if ratio <= warn_threshold and (ratio > ban_threshold or total < min_games_completed):
            action = "warn"
        elif ratio <= ban_threshold and total >= min_games_completed:
            action = "ban"
        else:
            action = None

        return (action, ratio)

    def warn_player(self, player, ratio):
        player.tell("^7You have only completed ^6{}^7 percent of your games.".format(round(ratio * 100, 1)))
        player.tell("^7If you keep leaving you ^6will^7 be banned.")

    def flag_player(self, player):
        with self.ban_flagged_lock:
            if player not in self.ban_flagged:
                self.ban_flagged.append(player)
    
    def unflag_player(self, player):
        with self.ban_flagged_lock:
            if player in self.ban_flagged:
                self.ban_flagged.remove(player)

    def is_flagged(self, player):
        with self.ban_flagged_lock:
            return player in self.ban_flagged
