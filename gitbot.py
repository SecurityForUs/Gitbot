#!/usr/bin/env python

import socket
import requests
import urllib
import json

class GitBot(object):
    def __init__(self, host="irc.freenode.net", port=6667, chan="someweirdchan", nick="gitbot", cmd_start = "gitbot", acct = "github_username"):
        self.chan = chan
        
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((host, port))
        self.send("USER %s %s %s :GitHub IRC bot" % (nick, nick, nick), pm=False)
        self.send("NICK %s" % (nick),pm=False)
        self.send("JOIN #%s" % (chan),pm=False)
        
        self.cmd = cmd_start
        self.acct = acct
        
    def close(self):
        self.sock.close()
        
    def github(self, type, call, repo = None, get_args = {}):
        if get_args and isinstance(get_args, dict):
            get_args = urllib.urlencode(get_args)
        
        url = "https://api.github.com/%s/%s/%s/%s/%s" % (type, self.acct, repo, call, get_args)
        print "Sending GitHub request:",url
        
        r = requests.get(url)
        return json.loads(r.content)
    
    def legacy_github(self, type, action, repo, terms, state = "open"):
        url = "https://api.github.com/legacy/%s/%s/%s/%s/%s/%s" % (type, action, self.acct, repo, state, terms)
        print "Sending legacy GitHub request:",url
        
        r = requests.get(url)
        return json.loads(r.content)
        
    def getcmd(self, msg):
        repo_lookup = ['python', 'ach-python', 'api', 'php', 'ach-php', 'ach-ruby', 'ruby', 'js', 'django']
        
        parts = msg.split(":", 2)[2]
        parts = parts.split(" ", 2)
        
        cmd = str(parts[1]).lower()
        args = parts[2]
        
        if cmd == "issue":
            parts = args.split(" ", 1)
            
            try:
                repo = parts[0]
            except:
                self.send("No repo was provided.  Command format: %s issue <repo> <issue # or terms>" % (self.cmd))
                return False
            
            try:
                terms = parts[1]
            except:
                self.send("No search criteria was provided.  Command format: %s issue <repo> <issue # or terms>" % (self.cmd))
                return False
            
            if repo in repo_lookup:
                repo = "balanced-%s" % (repo)
                
                try:
                    terms = int(terms)
                    self.issue_lookup(repo, "i", terms)
                except ValueError:
                    self.issue_lookup(repo, "boob", terms)
            elif cmd == "acct":
                self.acct = args
            else:
                self.send("Balanced does not have GitHub repo named balanced-%s" % (repo))
        else:
            self.send("I'm sorry but I do not recognize the command \"%s\" with args \"%s\"" % (cmd, args))
            
    def send(self, msg, to=None, pm = True):
        if not to:
            to = self.chan
        
        if pm:
            self.sock.send("PRIVMSG #%s :%s\n" % (to, msg))
        else:
            self.sock.send("%s\n" % (msg))
            
    def issue_lookup(self, repo, stype, search):
        print "Browsing %s of %s for %s" % (repo, stype, search)
        
        if stype is "i":
            issue = self.github("repos", "issues", repo, search)
            
            try:
                issue['user'] = issue['user']['login']
            except:
                pass
        else:
            call = self.legacy_github("issues", "search", repo, search)
            
            try:
                issue = call['issues'][0]
            except:
                pass
            
        try:
            self.send("%s created an issue titled \"%s\" that is %s at %s" % (issue['user'], issue['title'], issue['state'], issue['html_url']))
        except:
            self.send("Unable to find any open issues with the provided search criteria")
            
    def recv(self):
        msg = str(self.sock.recv(2048)).strip()
            
        if msg.find("PING") != -1:
            self.send("PONG :back",pm=False)
        elif msg.find(":%s" % (self.cmd)) != -1:
            self.getcmd(msg)
            
        return True
        
bot = GitBot()
stat = True

try:
    while stat:
        stat = bot.recv()
except:
    pass

print "Shutting down Gitbot..."
bot.close()