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


# This plugin is the result of starting with an initial idea, followed
# by a bunch of other ones, and then put together into one. If there's any
# plugin that needs to be rewritten, it's this huge mess right here.

"""Balancing plugin based on ratings set manually or from QLRanks.

There's quite a bit going on here. Since we don't want any blocking HTTP requests
to QLRanks, we'll be using multithreading here. At the same time, we don't want to
give QLRanks more load than needed, so we're also caching the results. We also want
to be able to assign ratings manually, and finally we also want it to take registered
aliases into account by fetching the ratings from the real names instead when using QLRanks.
All this combined inevitably makes the code somewhat complex.

When !teams or !balance is called, the plugin will check if we have all the players
cached. If they are, just go ahead and execute the commands. If not, we'll add an entry
to a list of pending actions (the !teams or !balance), and call the function to fetch the
ratings of the players we don't have cached. This function will first check any manually
assigned ratings if the config is set to. If we still don't have what we need, we start a
thread and let it fetch ratings from QLRanks, taking into account aliases if set to do so
in the config. The thread will then make sure the players are cached and finally execute
pending tasks. To avoid accessing a shared resource on multiple threads, we use a re-entrant
lock. This makes it safe to add additional tasks, such as alternative shuffling algorithms
and whatnot without having to deal with that.
"""

from threading import RLock
import plugins.qlranks as qlranks
import minqlbot
import random
import re
import threading
import datetime

FAILS_ALLOWED = 2
QLRANKS_GAMETYPES = ("ca", "ffa", "ctf", "duel", "tdm")
ALPHANUMERICAL = re.compile(r"^[a-zA-Z0-9_]*$", flags=0)
# Time window in seconds after round_countdown where players could switch right away with !a.
AGREE_WINDOW = 7

class balance(minqlbot.Plugin):
    def __init__(self):
        super().__init__()
        self.add_hook("vote_called", self.handle_vote_called, priority=minqlbot.PRI_HIGH)
        self.add_hook("vote_ended", self.handle_vote_ended)
        self.add_hook("player_connect", self.handle_player_connect)
        self.add_hook("team_switch", self.handle_team_switch)
        self.add_hook("round_countdown", self.handle_round_countdown)
        self.add_hook("game_end", self.handle_game_end)
        self.add_command(("teams", "teens"), self.cmd_teams)
        self.add_command("balance", self.cmd_balance, 1)
        self.add_command("do", self.cmd_do, 1)
        self.add_command(("agree", "a"), self.cmd_agree)
        self.add_command(("setrating", "setelo"), self.cmd_setrating, 3, usage="<full_name> <rating>")
        self.add_command(("getrating", "getelo", "elo"), self.cmd_getrating, usage="<full_name>")
        self.add_command(("remrating", "remelo"), self.cmd_remrating, 3, usage="<full_name>")

        self.suggested_pair = None
        self.suggested_agree = [False, False]

        self.rlock = RLock()

        # Keys: QlRanks().uid - Items: (QlRanks(), names, channel)
        self.lookups = {}
        # Keys: player_name - Items: {"ffa": {"elo": 123, rank: 321}, ...}
        self.cache = {}
        # Pending balancing, teams info, and so on. Format: (type, channel)
        self.pending = []
        # How many times we've failed a request in a row so we don't loop forever.
        self.fails = 0

        # We flag players who ought to be kickbanned, but since we delay it, we keep
        # a list of players who are flagged and prevent them from starting votes or joining.
        self.ban_flagged = []
        self.ban_flagged_lock = threading.RLock()

        # A datetime.datetime instance of the point in time of the last round countdown.
        self.countdown = None

    def handle_vote_called(self, caller, vote, args):
        if self.is_flagged(caller):
            self.vote_no()
            return

        config = minqlbot.get_config()
        if vote == "shuffle" and "Balance" in config:
            auto_reject = config["Balance"].getboolean("VetoUnevenShuffleVote", fallback=False)
            if auto_reject:
                teams = self.teams()
                if len(teams["red"] + teams["blue"]) % 2 == 1:
                    self.vote_no()
                    self.msg("^7Only call shuffle votes when the total number of players is an even number.")

    def handle_vote_ended(self, vote, args, vote_count, passed):
        config = minqlbot.get_config()
        if "Balance" not in config:
            return

        if passed == True and vote == "shuffle":
            auto = config["Balance"].getboolean("AutoBalance", fallback=False)
            if not auto:
                return
            else:
                teams = self.teams()
                total = len(teams["red"]) + len(teams["blue"])
                if total % 2 == 0:
                    self.delay(5, self.average_balance, args=(minqlbot.CHAT_CHANNEL, self.game().short_type))
                else:
                    self.msg("^7I can't balance when the total number of players is not an even number.")

    def handle_player_connect(self, player):
        gametype = self.game().short_type
        if not self.is_cached(player.clean_name, gametype):
            self.fetch_player_ratings([player.clean_name.lower()], None, gametype)
        self.check_rating_requirements([player.clean_name.lower()], None, gametype)

    def handle_team_switch(self, player, old_team, new_team):
        if new_team != "spectator":
            if self.is_flagged(player):
                player.put("spectator")
                return
            else:
                gametype = self.game().short_type
                self.check_rating_requirements([player.clean_name.lower()], None, gametype)

    def handle_round_countdown(self, round):
        if self.suggested_agree[0] and self.suggested_agree[1]:
            self.execute_suggestion()
        
        self.countdown = datetime.datetime.now()

    def handle_game_end(self, game, score, winner):
        # Clear suggestion when the game ends to avoid weird behavior if a pending switch
        # is present and the players decide to do a rematch without doing !teams in-between.
        self.suggested_pair = None
        self.suggested_agree = [False, False]

    def cmd_teams(self, player, msg, channel):
        """Displays the average ratings of each team, the difference between those values,
        as well as a switch suggestion that the bot determined would improve balance."""
        teams = self.teams()
        diff = len(teams["red"]) - len(teams["blue"])
        if not diff:
            self.teams_info(channel, self.game().short_type)
        else:
            channel.reply("^7Both teams should have the same number of players.")

    def cmd_balance(self, player, msg, channel):
        """Makes the bot switch players around in an attempt to create balanced teams based
        on ratings."""
        teams = self.teams()
        total = len(teams["red"]) + len(teams["blue"])
        if total % 2 == 0:
            self.average_balance(channel, self.game().short_type)
        else:
            channel.reply("^7I can't balance when the total number of players is not an even number.")

    def cmd_do(self, player, msg, channel):
        """Forces a suggested switch to be done."""
        if self.suggested_pair:
            self.execute_suggestion()

    def cmd_agree(self, player, msg, channel):
        """After the bot suggests a switch, players in question can use this to agree to the switch."""
        if self.suggested_pair:
            if self.suggested_pair[0] == player:
                self.suggested_agree[0] = True
            elif self.suggested_pair[1] == player:
                self.suggested_agree[1] = True

            if self.suggested_agree[0] and self.suggested_agree[1]:
                # If the game's in progress and we're not in the round_countdown time window, wait for next round.
                if self.game().state == "in_progress" and self.countdown:
                    td = datetime.datetime.now() - self.countdown
                    if td.seconds > AGREE_WINDOW:
                        self.msg("^7The switch will be executed at the start of next round.")
                        return

                # Otherwise, switch right away.
                self.execute_suggestion()

    def cmd_setrating(self, player, msg, channel):
        """Set a player's rating locally, in the game mode the bot is currently in."""
        if len(msg) < 3:
            return minqlbot.RET_USAGE

        try:
            rating = int(msg[2])
        except ValueError:
            channel.reply("Unintelligible rating. Only use numbers.")
            return

        game = self.game()
        short_game_type = game.short_type
        name = self.clean_text(msg[1]).lower()
        # Look up if player is in DB. If not, add.
        c = self.db_query("SELECT name FROM Players WHERE name=?", name)
        if not c.fetchone():
            self.db_query("INSERT INTO Players VALUES(?, 0, '', 0, 0)", name)
            self.db_query("INSERT INTO Ratings VALUES(?, ?, ?)", name, short_game_type, rating)
            self.db_commit()
            channel.reply("^6{}^7 was added as a player with a ^6{}^7 {} rating.".format(msg[1], rating, game.type))
            if name in self.cache and short_game_type in self.cache[name]:
                del self.cache[name][short_game_type]
            return

        c = self.db_query("SELECT game_type FROM Ratings WHERE name=?", name)
        rows = c.fetchall()
        for row in rows: # Already set rating?
            if row["game_type"] == short_game_type:
                self.db_query("UPDATE Ratings SET rating=? WHERE name=? AND game_type=?", rating, name, short_game_type)
                self.db_commit()
                channel.reply("^6{}^7's {} rating has been updated to ^6{}^7.".format(msg[1], game.type, rating))
                if name in self.cache and short_game_type in self.cache[name]:
                    del self.cache[name][short_game_type]
                return

        # We have the player, but the rating isn't set.
        self.db_query("INSERT INTO Ratings VALUES(?, ?, ?)", name, short_game_type, rating)
        self.db_commit()
        channel.reply("^6{}^7's {} rating was set to ^6{}^7.".format(msg[1], game.type, rating))
        if name in self.cache and short_game_type in self.cache[name]:
            del self.cache[name][short_game_type]
        return

    def cmd_getrating(self, player, msg, channel):
        """Get someone's rating. Be it locally set or from QLRanks."""
        if len(msg) < 2:
            name = player.clean_name.lower()
        else:
            name = self.clean_text(msg[1]).lower()

        if not self.is_sane([name]):
            return
        
        game = self.game()
        short_game_type = game.short_type
        c = self.db_query("SELECT rating FROM Ratings WHERE name=? AND game_type=?", name, short_game_type)
        row = c.fetchone()
        if not row:
            self.individual_rating(name, channel, short_game_type)
            return
        else:
            channel.reply("^6{}^7's {} rating is set to ^6{}^7 on this server specifically."
                .format(name, game.type, row["rating"]))

    def cmd_remrating(self, player, msg, channel):
        """Remove a locally set rating in the game mode the bot is currently in."""
        if len(msg) < 2:
            return minqlbot.RET_USAGE

        game = self.game()
        short_game_type = game.short_type
        name = self.clean_text(msg[1]).lower()
        c = self.db_query("DELETE FROM Ratings WHERE name=? AND game_type=?", name, short_game_type)
        if not c.rowcount:
            channel.reply("^7I have no {} rating data on ^6{}^7.".format(game.type, msg[1]))
            return
        else:
            self.db_commit()
            channel.reply("^6{}^7's {} rating data has been removed.".format(msg[1], game.type))
            if name in self.cache and short_game_type in self.cache[name]:
                del self.cache[name][short_game_type]
            return

    def fetch_player_ratings(self, names, channel, game_type, use_local=True, use_aliases=True):
        """Fetch ratings from the database and fall back to QLRanks.

        Takes into account ongoing lookups to avoid sending multiple requests for a player.

        """
        config = minqlbot.get_config()
        # Fetch players from the database first if the config is set to do so.
        if use_local and "Balance" in config and config["Balance"].getboolean("UseLocalRatings", fallback=False):
            ratings = {"players": []}  # We follow QLRanks' JSON format.
            for name in names.copy():
                c = self.db_query("SELECT game_type, rating FROM ratings WHERE name=?", name)
                res = c.fetchall()
                if res:
                    d = {"nick": name}
                    for row in res:
                        d[row["game_type"]] = {"elo": row["rating"], "rank": -1} # QLRanks' format.
                        if game_type == row["game_type"]:
                            names.remove(name)  # Got the one we need locally.
                    ratings["players"].append(d)
            if ratings["players"]:
                self.cache_players(ratings, None)

        # If we've covered everyone, we execute whatever pending tasks we have.
        if not names:
            self.execute_pending()
            return

        # Remove players we're already waiting a response for.
        with self.rlock:
            for lookup in self.lookups:
                for n in self.lookups[lookup][1]:
                    if n in names:
                        names.remove(n)

        # We fall back to QLRanks for players we don't have, but stop if we want a gametype it doesn't provide.
        if names and game_type in QLRANKS_GAMETYPES:
            if use_aliases and "Balance" in config:
                conf_alias = config["Balance"].getboolean("UseAliases", fallback=True)
            else:
                conf_alias = False
            lookup = qlranks.QlRanks(self, names, check_alias=conf_alias)
            with self.rlock:
                self.lookups[lookup.uid] = (lookup, names, channel)
            lookup.start()
            return True
        else:
            return False

    def cache_players(self, ratings, lookup):
        """Save the ratings of a player to the cache.

        """
        config = minqlbot.get_config()

        if ratings == None:
            self.lookup_failed(lookup)
            return
        else:
            floor = 0
            ceiling = 0
            if "Balance" in config:
                if "FloorRating" in config["Balance"]:
                    floor = int(config["Balance"]["FloorRating"])
                if "CeilingRating" in config["Balance"]:
                    ceiling = int(config["Balance"]["CeilingRating"])

            with self.rlock:
                self.fails = 0 # Reset fail counter.
            for player in ratings["players"]:
                name = player["nick"]
                del player["nick"]

                for game_type in player:
                    if game_type == "alias_of": # Not a game type.
                        continue
                    # Enforce floor and ceiling values if we have them.
                    if floor and player[game_type]["elo"] < floor:
                        player[game_type]["real_elo"] = player[game_type]["elo"]
                        player[game_type]["elo"] = floor
                    elif ceiling and player[game_type]["elo"] > ceiling:
                        player[game_type]["real_elo"] = player[game_type]["elo"]
                        player[game_type]["elo"] = ceiling

                with self.rlock:
                    # If it's an alias, go ahead and cache the real one as well.
                    if "alias_of" in player:
                        real_name = player["alias_of"]
                        self.cache[real_name] = player.copy()
                        # Make sure real name isn't treated as alias.
                        del self.cache[real_name]["alias_of"]

                    if name not in self.cache: # Already in our cache?
                        self.cache[name] = player
                    else:
                        if "alias_of" in player:
                            self.cache[name]["alias_of"] = player["alias_of"]
                        # Gotta be careful not to overwrite game types we've manually set ratings for.
                        for game_type in player:
                            if game_type not in self.cache[name] and game_type != "alias_of":
                                self.cache[name][game_type] = player[game_type]
        
            # The lookup's been dealt with, so we get rid of it.
            if lookup:
                with self.rlock:
                    del self.lookups[lookup.uid]

    def is_cached(self, name, game_type):
        """Checks if a player is cached or not.

        """
        with self.rlock:
            if name in self.cache and game_type in self.cache[name]:
                return True
            else:
                return False

    def not_cached(self, game_type, player_list=None):
        """Get a list of players that are not cached.

        """
        not_cached = []
        teams = self.teams()
        if player_list == None:
            players = teams["red"] + teams["blue"] + teams["spectator"]
        else:
            players = player_list

        for player in players:
            if isinstance(player, str):
                if not self.is_cached(player, game_type):
                    not_cached.append(player)
            elif not self.is_cached(player.clean_name.lower(), game_type):
                not_cached.append(player.clean_name.lower())
        return not_cached
    
    def lookup_failed(self, lookup):
        """Handle lookups that failed due to timeouts and such

        """
        with self.rlock:
            self.fails += 1
            if self.fails < FAILS_ALLOWED or self.lookups[lookup.uid][2] == None:
                del self.lookups[lookup.uid]
                return
            elif lookup.status == -2:
                err_msg = "^7The connection to QLRanks timed out."
            else:
                err_msg = "^7The connection to QLRanks failed with error code: ^6{}".format(lookup.status)
            channel = self.lookups[lookup.uid][2]
            channel.reply(err_msg)
            del self.lookups[lookup.uid]

    def execute_pending(self):
        """Checks for pending tasks and execute them.

        """
        # If limit is hit, clear pending requests and fail counter, then do nothing.
        # We don't want to keep requesting if something's wrong, but rather let a player
        # or an event trigger it again.
        with self.rlock:
            if self.fails >= FAILS_ALLOWED:
                self.fails = 0
                self.pending.clear()
                return

        with self.rlock:
            for task in self.pending.copy():
                if task[0](*task[1]):
                    self.pending.remove(task)

    def check_rating_requirements(self, names, channel, game_type):
        """Checks if someone meets the rating requirements to play on the server."""
        config = minqlbot.get_config()
        min_rating = 0
        max_rating = 0
        if "Balance" in config:
            if "MinimumRating" in config["Balance"]:
                min_rating = int(config["Balance"]["MinimumRating"])
            if "MaximumRating" in config["Balance"]:
                max_rating = int(config["Balance"]["MaximumRating"])
        else:
            return True

        if not min_rating and not max_rating:
            return True

        not_cached = self.not_cached(game_type, names)
        if not_cached:
            with self.rlock:
                for lookup in self.lookups:
                    for n in self.lookups[lookup][1]:
                        if n in not_cached:
                            not_cached.remove(n)
                if not_cached:
                    self.fetch_player_ratings(not_cached, channel, game_type)
                if (self.check_rating_requirements, (names, channel, game_type)) not in self.pending:
                    self.pending.append((self.check_rating_requirements, (names, channel, game_type)))
                return False

        for name in names:
            if "real_elo" in self.cache[name][game_type]:
                rating = self.cache[name][game_type]["real_elo"]
            else:
                rating = self.cache[name][game_type]["elo"]

            if (rating > max_rating and max_rating != 0) or (rating < min_rating and min_rating != 0):
                allow_spec = config["Balance"].getboolean("AllowSpectators", fallback=True)
                if allow_spec:
                    player = self.player(name)
                    if not player:
                        return True
                    if player.team != "spectator":
                        self.put(name, "spectator")
                        if rating > max_rating and max_rating != 0:
                            self.tell("^7Sorry, but you can have at most ^6{}^7 rating to play here and you have ^6{}^7."
                                .format(max_rating, rating), name)
                        elif rating < min_rating and min_rating != 0:
                            self.tell("^7Sorry, but you need at least ^6{}^7 rating to play here and you have ^6{}^7."
                                .format(min_rating, rating), name)
                else:
                    player = self.player(name)
                    if not player:
                        return True
                    elif player.team != "spectator":
                        self.put(player, "spectator")
                    self.flag_player(player)
                    player.mute()
                    self.delay(25, lambda: player.tell("^7You do not meet the rating requirements on this server. You will be kicked shortly."))
                    self.delay(40, player.kickban)

        return True

    def individual_rating(self, name, channel, game_type):
        not_cached = self.not_cached(game_type, (name,))
        if not_cached:
            with self.rlock:
                for lookup in self.lookups:
                    for n in self.lookups[lookup][1]:
                        if n in not_cached:
                            not_cached.remove(n)
                if not_cached:
                    self.fetch_player_ratings(not_cached, channel, game_type, use_local=False, use_aliases=True)
                if (self.individual_rating, (name, channel, game_type)) not in self.pending:
                    self.pending.append((self.individual_rating, (name, channel, game_type)))
                return False

        # NO DATA?
        short_game_type = game_type.upper()
        if self.cache[name][game_type]["rank"] == 0:
            channel.reply("^7QLRanks has no data on ^6{}^7 for {}.".format(name, short_game_type))
            return True
        # ALIAS?
        elif "alias_of" in self.cache[name]:
            if "real_elo" in self.cache[name][game_type]: # Ceiling/floor clipped rating?
                real = self.cache[name][game_type]["real_elo"]
                clipped = self.cache[name][game_type]["elo"]
                channel.reply("^6{}^7 is an alias of ^6{}^7, who is ranked #^6{}^7 in {} with a rating of ^6{}^7, but treated as ^6{}^7."
                    .format(name, self.cache[name]["alias_of"], self.cache[name][game_type]["rank"],
                            short_game_type, real, clipped))
            else:
                channel.reply("^6{}^7 is an alias of ^6{}^7, who is ranked #^6{}^7 in {} with a rating of ^6{}^7."
                    .format(name, self.cache[name]["alias_of"], self.cache[name][game_type]["rank"],
                            short_game_type, self.cache[name][game_type]["elo"]))
            return True
        # NORMAL
        else:
            if "real_elo" in self.cache[name][game_type]: # Ceiling/floor clipped rating?
                real = self.cache[name][game_type]["real_elo"]
                clipped = self.cache[name][game_type]["elo"]
                channel.reply("^6{}^7 is ranked #^6{}^7 in {} with a rating of ^6{}^7, but treated as ^6{}^7."
                    .format(name, self.cache[name][game_type]["rank"], short_game_type, real, clipped))
            else:
                channel.reply("^6{}^7 is ranked #^6{}^7 in {} with a rating of ^6{}^7."
                    .format(name, self.cache[name][game_type]["rank"], short_game_type, self.cache[name][game_type]["elo"]))
            return True

    def teams_info(self, channel, game_type):
        """Send average team ratings and an improvement suggestion to whoever asked for it.

        """
        teams = self.teams()
        diff = len(teams["red"]) - len(teams["blue"])
        if diff:
            channel.reply("^7Both teams should have the same number of players.")
            return True
        
        players = teams["red"] + teams["blue"]
        not_cached = self.not_cached(game_type, players)
        
        if not_cached:
            with self.rlock:
                for lookup in self.lookups:
                    for n in self.lookups[lookup][1]:
                        if n in not_cached:
                            not_cached.remove(n)
                if not_cached:
                    self.fetch_player_ratings(not_cached, channel, game_type)
                if (self.teams_info, (channel, game_type)) not in self.pending:
                    self.pending.append((self.teams_info, (channel, game_type)))
                # Let a later call to execute_pending come back to us.
                return False

        avg_red = self.team_average(teams["red"], game_type)
        avg_blue = self.team_average(teams["blue"], game_type)
        switch = self.suggest_switch(teams, game_type)
        diff = len(teams["red"]) - len(teams["blue"])
        diff_rounded = abs(round(avg_red) - round(avg_blue)) # Round individual averages.
        if round(avg_red) > round(avg_blue):
            channel.reply("^1{} ^7vs ^4{}^7 - DIFFERENCE: ^1{}"
                .format(round(avg_red), round(avg_blue), diff_rounded))
        elif round(avg_red) < round(avg_blue):
            channel.reply("^1{} ^7vs ^4{}^7 - DIFFERENCE: ^4{}"
                .format(round(avg_red), round(avg_blue), diff_rounded))
        else:
            channel.reply("^1{} ^7vs ^4{}^7 - Holy shit!"
                .format(round(avg_red), round(avg_blue)))

        config = minqlbot.get_config()
        if "Balance" in config:
            minimum_suggestion_diff = int(config["Balance"].get("MinimumSuggestionDifference", fallback="25"))
        else:
            minimum_suggestion_diff = 25

        if switch and switch[1] >= minimum_suggestion_diff:
            channel.reply("^7SUGGESTION: switch ^6{}^7 with ^6{}^7. Type !a to agree."
                .format(switch[0][0].clean_name, switch[0][1].clean_name))
            if not self.suggested_pair or self.suggested_pair[0] != switch[0][0] or self.suggested_pair[1] != switch[0][1]:
                self.suggested_pair = (switch[0][0], switch[0][1])
                self.suggested_agree = [False, False]
        else:
            i = random.randint(0, 99)
            if not i:
                channel.reply("^7Teens look ^6good!")
            else:
                channel.reply("^7Teams look good!")
            self.suggested_pair = None

        return True

    def average_balance(self, channel, game_type):
        """Balance teams based on average team ratings.

        """
        teams = self.teams()
        total = len(teams["red"]) + len(teams["blue"])
        if total % 2 == 1:
            channel.reply("^7I can't balance when the total number of players isn't an even number.")
            return True

        players = teams["red"] + teams["blue"]
        not_cached = self.not_cached(game_type, players)

        if not_cached:
            with self.rlock:
                for lookup in self.lookups:
                    for n in self.lookups[lookup][1]:
                        if n in not_cached:
                            not_cached.remove(n)
                if not_cached:
                    self.fetch_player_ratings(not_cached, channel, game_type)
                if (self.average_balance, (channel, game_type)) not in self.pending:
                    self.pending.append((self.average_balance, (channel, game_type)))
                # Let a later call to execute_pending come back to us.
                return False
        else:
            # Start out by evening out the number of players on each team.
            diff = len(teams["red"]) - len(teams["blue"])
            if abs(diff) > 1:
                channel.reply("^7Evening teams...")
                if diff > 0:
                    for i in range(diff - 1):
                        p = teams["red"].pop()
                        self.put(p, "blue")
                        teams["blue"].append(p)
                elif diff < 0:
                    for i in range(abs(diff) - 1):
                        p = teams["blue"].pop()
                        self.put(p, "red")
                        teams["red"].append(p)

            # Start shuffling by looping through our suggestion function until
            # there are no more switches that can be done to improve teams.
            switch = self.suggest_switch(teams, game_type)
            if switch:
                self.msg("^7Balancing teams...")
                self.lock()
                while switch:
                    p1 = switch[0][0]
                    p2 = switch[0][1]
                    self.msg("^7{} ^6<=> ^7{}".format(p1, p2))
                    self.switch(p1, p2)
                    teams["blue"].append(p1)
                    teams["red"].append(p2)
                    teams["blue"].remove(p2)
                    teams["red"].remove(p1)
                    switch = self.suggest_switch(teams, game_type)
                self.unlock()
                avg_red = self.team_average(teams["red"], game_type)
                avg_blue = self.team_average(teams["blue"], game_type)
                diff_rounded = abs(round(avg_red) - round(avg_blue)) # Round individual averages.
                if round(avg_red) > round(avg_blue):
                    self.msg("^7Done! ^1{} ^7vs ^4{}^7 - DIFFERENCE: ^1{}"
                        .format(round(avg_red), round(avg_blue), diff_rounded))
                elif round(avg_red) < round(avg_blue):
                    self.msg("^7Done! ^1{} ^7vs ^4{}^7 - DIFFERENCE: ^4{}"
                        .format(round(avg_red), round(avg_blue), diff_rounded))
                else:
                    self.msg("^7Done! ^1{} ^7vs ^4{}^7 - Holy shit!"
                        .format(round(avg_red), round(avg_blue)))
            else:
                channel.reply("^7Teams are good! Nothing to balance.")
            return True

    def suggest_switch(self, teams, game_type):
        """Suggest a switch based on average team ratings.

        """
        avg_red = self.team_average(teams["red"], game_type)
        avg_blue = self.team_average(teams["blue"], game_type)
        cur_diff = abs(avg_red - avg_blue)
        min_diff = 999999
        best_pair = None

        for red_p in teams["red"]:
            for blue_p in teams["blue"]:
                r = teams["red"].copy()
                b = teams["blue"].copy()
                b.append(red_p)
                r.remove(red_p)
                r.append(blue_p)
                b.remove(blue_p)
                avg_red = self.team_average(r, game_type)
                avg_blue = self.team_average(b, game_type)
                diff = abs(avg_red - avg_blue)
                if diff < min_diff:
                    min_diff = diff
                    best_pair = (red_p, blue_p)

        if min_diff < cur_diff:
            return (best_pair, cur_diff - min_diff)
        else:
            return None

    def team_average(self, team, game_type):
        """Calculates the average rating of a team.

        """
        avg = 0

        if team:
            with self.rlock:
                for p in team:
                    avg += self.cache[p.clean_name.lower()][game_type]["elo"]
                avg /= len(team)

        return avg

    def is_sane(self, names):
        for name in names:
            if not ALPHANUMERICAL.match(name):
                return False

            return True

    def execute_suggestion(self):
        self.switch(self.suggested_pair[0], self.suggested_pair[1])
        self.suggested_pair = None
        self.suggested_agree = [False, False]

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

