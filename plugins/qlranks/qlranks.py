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

import http.client
import json
import threading
import minqlbot
import traceback

class QlRanks(threading.Thread):
    instances = 0

    def __init__(self, plugin, players, check_alias=True):
        threading.Thread.__init__(self)
        self.uid = self.instances
        self.plugin = plugin
        self.players = players
        self.status = 0
        self.check_alias = check_alias
        self.aliases = {}
        QlRanks.instances += 1
    
    def run(self):
        try:
            self.plugin.debug("QLRanks thread #{} started!".format(self.uid))
            if self.check_alias:
                for i in range(len(self.players)):
                    c = self.plugin.db_query("SELECT name FROM Aliases WHERE other_name=?", self.players[i])
                    res = c.fetchone()
                    if res:
                        self.aliases[res["name"]] = self.players[i]
                        self.players[i] = res["name"]
                self.plugin.db_close()
            
            try:
                player_list = "+".join(self.players)
                data = self.get_data("www.qlranks.com", "/api.aspx?nick={}".format(player_list))
            except:
                self.status = -2
                self.plugin.cache_players(None, self)
                self.plugin.execute_pending() # execute_pending has endless loop prevention.
                return

            if "players" not in data:
                raise Exception("QLRanks returned a valid, but unexpected JSON response.")


            if self.check_alias:
                # Replace alias nicknames with real names.
                for player in data["players"]:
                    name = player["nick"].lower()
                    if name in self.aliases:
                        player["nick"] = self.aliases[name]
                        player["alias_of"] = name
                        del self.aliases[name]

            self.plugin.cache_players(data, self)
            # Check for pending teams info/balancing needed. Execute if so.
            self.plugin.execute_pending()
        except:
            self.status = -3
            e = traceback.format_exc().rstrip("\n")
            minqlbot.debug("========== ERROR: QLRanks Fetcher #{} ==========".format(self.uid))
            for line in e.split("\n"):
                minqlbot.debug(line)
            self.plugin.cache_players(None, self)
            self.plugin.execute_pending()
    
    def get_data(self, url, path, post_data=None, headers={}):
        c = http.client.HTTPConnection(url, timeout=10)
        if post_data:
            c.request("POST", path, post_data, headers)
        else:
            c.request("GET", path, headers=headers)
        response = c.getresponse()
        self.status = response.status
        
        if response.status == http.client.OK: # 200
            try:
                data = json.loads(response.read().decode())
                return data
            except:
                self.status = -1
                return None
        else:
            return None

if __name__ == "__main__":
    qlr = QlRanks(["minomino", "minobot", "mino"], lambda x: print(x))
    qlr.run()