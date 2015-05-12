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

import urllib.parse
import urllib.request
import urllib.error
import http.cookiejar
import datetime

from html.parser import HTMLParser

QL_URL = "http://quakelive.com/"

class QlProfileParser(HTMLParser):
    def __init__(self, strict=False):
        HTMLParser.__init__(self, strict=strict)
        self.profile = QlProfile()
        self.capture = ""
    
    def handle_starttag(self, tag, attrs):
        if tag == "div" and ("id", "prf_player_name") in attrs:
            self.capture = "name"
        elif tag == "img" and ("class", "playerflag") in attrs:
            for attr in attrs:
                if attr[0] == "title":
                    self.profile.country = attr[1]
        #print("Encountered a start tag:", tag, "   ", attrs)
    def handle_endtag(self, tag):
        pass
        #print("Encountered an end tag :", tag)
    def handle_data(self, data):
        # Set up to grab the data the next time this is called.
        if data == "Member Since:":
            self.capture = "created"
        elif data == "Time Played:":
            self.capture = "played"
        elif data == "Last Game:":
            self.capture = "last_game"
        elif data == "Wins:":
            self.capture = "wins"
        elif data == "Losses / Quits:":
            self.capture = "losses_quits"
        elif data == "Frags / Deaths:":
            self.capture = "frags_deaths"
        elif data == "Hits / Shots:":
            self.capture = "hits_shots"
        elif data == "Accuracy:":
            self.capture = "accuracy"
        # Grab the data.
        elif self.capture and data.strip():
            if self.capture == "name":
                self.profile.name = data.strip()
                self.capture = ""
            elif self.capture == "created":
                self.profile.created = data.strip()
                self.capture = ""
            elif self.capture == "played":
                self.profile.played = data.strip()
                self.capture = ""
            elif self.capture == "last_game":
                self.profile.last_game = data.strip()
                self.capture = ""
            elif self.capture == "wins":
                self.profile.wins = data.strip()
                self.capture = ""
            elif self.capture == "losses_quits":
                split = data.split("/")
                self.profile.losses = split[0].strip()
                self.profile.quits = split[1].strip()
                self.capture = ""
            elif self.capture == "frags_deaths":
                split = data.split("/")
                self.profile.frags = split[0].strip()
                self.profile.deaths = split[1].strip()
                self.capture = ""
            elif self.capture == "hits_shots":
                split = data.split("/")
                self.profile.hits = split[0].strip()
                self.profile.shots = split[1].strip()
                self.capture = ""
            elif self.capture == "accuracy":
                self.profile.accuracy = data.strip()
                self.capture = ""
            

class QlProfile():
    def __init__(self, name="N/A", country="N/A", created="N/A", played="N/A", last_game="N/A",
                 wins=0, losses=0, quits=0, frags=0, deaths=0, hits=0, shots=0, accuracy=0):
        self.name = name
        self.country = country
        self.created = created
        self.played = played
        self.last_game = last_game
        self.wins = wins
        self.losses = losses
        self.quits = quits
        self.frags = frags
        self.deaths = deaths
        self.hits = hits
        self.shots = shots
        self.accuracy = accuracy
    
    def get_day(self):
        return int(self.created.split()[1].rstrip(","))
    
    def get_month(self):
        month = self.created.split()[0]
        if month == "Jan.": return 1
        elif month == "Feb.": return 2
        elif month == "Mar.": return 3
        elif month == "Apr.": return 4
        elif month == "May.": return 5
        elif month == "Jun.": return 6
        elif month == "Jul.": return 7
        elif month == "Aug.": return 8
        elif month == "Sep.": return 9
        elif month == "Oct.": return 10
        elif month == "Nov.": return 11
        elif month == "Dec.": return 12
    
    def get_year(self):
        return int(self.created.split()[2])
    
    def get_date(self):
        return datetime.date(self.get_year(), self.get_month(), self.get_day())
    
    def is_eligible(self, days):
        td = datetime.timedelta(days=days)
        min = datetime.date.today() - td
        return (self.get_date() < min)

def get_profile(name):
    cookies = http.cookiejar.CookieJar(http.cookiejar.DefaultCookiePolicy())
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
    url = QL_URL + "profile/summary/" + name.lower()
    request = urllib.request.Request(url, 
        headers={"User-Agent": "Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; WOW64; Trident/5.0)"})
    res = opener.open(request)
    data = res.read()
    parser = QlProfileParser()
    parser.feed(data.decode())
    return parser.profile

if __name__ == "__main__":
    profile = get_profile("Mino")
    
    print("Name: {}".format(profile.name))
    print("Country: {}".format(profile.country))
    print("Member Since: {}".format(profile.created))
    print("Time Played: {}".format(profile.played))
    print("Last Game: {}".format(profile.last_game))
    print("Wins: {}".format(profile.wins))
    print("Losses: {}".format(profile.losses))
    print("Quits: {}".format(profile.quits))
    print("Frags: {}".format(profile.frags))
    print("Deaths: {}".format(profile.deaths))
    print("Hits: {}".format(profile.hits))
    print("Shots: {}".format(profile.shots))
    print("Accuracy: {}".format(profile.accuracy))
    
    print("\nIs eligible: {}".format(profile.is_eligible(14)))
    