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
import threading

class maxping(minqlbot.Plugin):
    def __init__(self):
        super().__init__()
        config = minqlbot.get_config()
        if ( "MaxPing" not in config or
             "Samples" not in config["MaxPing"] or
             "SampleInterval" not in config["MaxPing"] or
             "MaximumPing" not in config["MaxPing"] ):
            raise AttributeError('maxping needs a "MaxPing" section with the fields "Samples", "SampleInterval", and "MaximumPing" in the config.')

        self.add_hook("scores", self.handle_scores)
        self.add_hook("unload", self.handle_unload)

        self.pings = {}
        self.expecting = False # Set to True when we're expecting to receive scores.
        self.requester = ScoresRequester(self)
        self.requester.start()

    def handle_scores(self, scores):
        if not self.expecting:
            return

        self.expecting = False
        config = minqlbot.get_config()
        
        for score in scores:
            name = score.player.clean_name.lower()
            if name not in self.pings:
                self.pings[name] = [score.ping]
            else:
                self.pings[name].append(score.ping)

                # Delete samples until we have "Samples" number of samples.
                # We use a while loop since the config could update and become more than just 1 lower than previously.
                samples = int(config["MaxPing"]["Samples"])
                while len(self.pings[name]) > samples:
                    del self.pings[name][0]

        self.check_pings(config)

    def handle_unload(self):
        self.requester.stop()

    def check_pings(self, config):
        players = [p.clean_name.lower() for p in self.players()]
        for name in players:
            if name not in self.pings or len(self.pings[name]) < int(config["MaxPing"]["Samples"]):
                continue

            average = sum(self.pings[name]) / len(self.pings[name])
            max_ping = float(config["MaxPing"]["MaximumPing"])
            if max_ping != 0 and average > max_ping:
                player = self.player(name)
                player.tell("^7Sorry, but your ping is too high to play on this server. You will be kicked shortly.")
                self.delay(8, player.kickban)



class ScoresRequester(threading.Thread):
    def __init__(self, plugin):
        super().__init__()
        self.plugin = plugin
        self.__stop = threading.Event()

    def run(self):
        while True:
            timeout = float(minqlbot.get_config()["MaxPing"]["SampleInterval"])
            if minqlbot.connection_status() == 8:
                self.plugin.expecting = True
                minqlbot.Plugin.scores()
            
            if self.__stop.wait(timeout=timeout):
                break

    def stop(self):
        self.__stop.set()
