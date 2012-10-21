#!/usr/bin/env python

import socket
import requests
import urllib
import json

class GitBot(object):
    """
    @param host: The IRC server to connect to
    @param port: Port the host is listening on
    @param chan: The channel on the server to join
    @param nick: Name of the bot on the channel
    @param nick_pass: Password for nick (if registered via NickServ)
    @param cmd_start: Message trigger for bot
    @param acct: The GitHub account to service
    """
    def __init__(self, host="irc.freenode.net", port=6667, chan="someweirdchan", nick="bgitbot", nick_pass=None, cmd_start = "gitbot", acct = "balanced"):
        self.chan = chan
        self.nick = nick
        
        print "Connecting %s to %s:%d#%s for GitHub %s with event trigger %s" % (nick, host, port, chan, acct, cmd_start)
        
        # Initiate the socket connection and send some generic IRC stuff
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((host, port))
        self.send("USER %s %s %s :GitHub IRC bot" % (nick, nick, nick), pm=False)
        self.send("NICK %s" % (nick),pm=False)
        
        # If the nick is reserved, authenticate it
        if nick_pass:
            print "NickServ pass provided: \"%s\"" % (nick_pass)
            self.send("PRIVMSG NickServ identify %s" % (nick_pass))
        
        # Join the channel
        self.send("JOIN #%s" % (chan),pm=False)
        
        self.cmd = cmd_start
        self.acct = acct
        self.repos = None
        
    """
    Closes the socket.
    """
    def close(self):
        self.sock.close()
    
    """
    Change the hub to perform actions/API calls on
    """
    def setacct(self, acct):
        # Only allow change if the account is different
        if (acct is not self.acct):
            self.acct = acct
            self.send("Now checking the hub of %s" % (acct))
            return True
        else:
            self.send("Already checking the hub of %s" % (acct))
            return False
    
    """
    Wrapper to interface with GitHub API.
    
    @param api_url: The full URL (minus params) to handle.
    @param get_args: Any query arguments to pass
    
    api_url filters the following:
    :acct: - The account (set either on init or via setacct()) to perform the action on
    
    """
    def github(self, api_url, get_args = {}):
        # Dictionary of criteria to filter, and what to replace it with
        filters = {":acct:" : self.acct}
        
        for crit,val in filters.iteritems():
            api_url = api_url.replace(crit, val)
        
        url = "https://api.github.com/%s" % (api_url)
        
        if get_args:
            url = "%s?%s" % (url, urllib.urlencode(get_args))
        
        r = requests.get(url)
        return json.loads(r.content)
        
    """
    Handles GitHub v2 API (legacy).  Only service for this is searching by keyword for issues by default.
    """
    def legacy_github(self, repo, terms, state = "open"):
        return self.github("legacy/issues/search/:acct:/%s/%s/%s" % (repo, state, terms))
    
    """
    Gets the repos of 'user' (def.: self.acct).  Returns cached results when possible.
    
    @param user: The GitHub username to fetch repos of
    @param type: Type of repos to get (owner - user created, member - forked, all - both owner & member)
    @param force: When true, force getting new repos instead of returning cache
    """
    def get_repos(self, user=None, type="owner", force=False):
        # If no force of cache is asked, and the user is the same, return the cache if possible
        if not force and (user is self.acct or user is None) and self.repos:
            return self.repos
        
        # Get a list of 'user''s repos
        r = self.github("users/:acct:/repos", get_args={'type' : type})
        
        repos = []
        
        # Gitbot was originally written for #balanced
        for repo in r:
            repos.append(str(repo['name']).replace("balanced-", ""))
        
        self.repos = repos
        
        return repos
    
    def check_admin(self):
        if not self.admins:
            self.send("Sorry, but you are not an admin to the channel, so you cannot do that.")
            return False
        
        user = self.msg.split(":", 3)[1].split("!")[0]
        
        return user in self.admins.keys()
        
    """
    Parses message sent with the command trigger
    """
    def getcmd(self, msg):
        # Fetches the actual message from what IRC sends out
        parts = msg.split(":", 2)[2]
        
        # Splits the message into parts
        parts = parts.split(" ", 2)
        
        # Get the command requested
        cmd = str(parts[1]).lower()
    
        # Try to get arguments, otherwise just continue    
        try:
            args = parts[2]
        except:
            pass
        
        if cmd == "issue":
            repo_lookup = self.get_repos()
            
            try:
                parts = args.split(" ", 1)
            except:
                self.send("No arguments were provided.")
                return False
            
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
                    self.issue_lookup(repo, "s", terms)
            else:
                self.send("Balanced does not have GitHub repo named balanced-%s" % (repo))
        elif cmd == "hub" and self.check_admin():
            self.setacct(args)
        elif cmd == "list":
            if args == "repo":
                self.send(json.dumps(self.get_repos()))
            elif args == "admins":
                self.send("The following admins are: %s" % (', '.join(self.admins.keys())))
        else:
            self.send("I'm sorry but I do not recognize the command \"%s\" with args \"%s\"" % (cmd, args))
    
    """
    Sends 'msg' to the person marked as 'to'.  If 'pm' is true, send it to the channel, otherwise to the server itself.
    """
    def send(self, msg, to=None, pm = True):
        if not to:
            to = self.chan
        
        if pm:
            self.sock.send("PRIVMSG #%s :%s\n" % (to, msg))
        else:
            self.sock.send("%s\n" % (msg))
    
    """
    Wrote into it's own function to make things simpler for myself.
    """
    def issue_lookup(self, repo, stype, search):
        if stype is "i":
            issue = self.github("repos/:acct:/%s/issues/%d" % (repo, search))
            
            try:
                issue['user'] = issue['user']['login']
            except:
                pass
        else:
            call = self.legacy_github(repo, search)
            
            try:
                issue = call['issues'][0]
            except:
                pass
            
        try:
            self.send("%s created an issue titled \"%s\" that is %s at %s" % (issue['user'], issue['title'], issue['state'], issue['html_url']))
        except:
            self.send("Unable to find any open issues with the provided search criteria")
            
    def recv(self,debug=False):
        msg = str(self.sock.recv(2048)).strip()
        
        self.msg = msg
        
        if debug:
            print "msg =",msg
            
        if msg.find("PING") != -1:
            self.send("PONG :back",pm=False)
        elif msg.find(":%s" % (self.cmd)) != -1:
            self.getcmd(msg)
        elif msg.find("353 %s @ #%s :" % (self.nick, self.chan)) != -1:
            self.admins = {}
            
            users = msg.split(":", 3)[2].strip().split(" ")
            
            for name in users:
                if name.startswith(("@", "~", "&", "%")):
                    self.admins[name[1:]] = name[0]
        elif msg.find("MODE #%s" % (self.chan)) != -1 and msg.find("PRIVMSG") == -1:
            _,perm,name = msg.split("MODE")[1].strip().split(" ")
            
            if perm[0] == "-":
                del self.admins[name]
            elif perm[0] == "+":
                self.admins[name] = "*"
            
bot = GitBot()

try:
    while True:
        bot.recv(False)
except:
    pass

print "Shutting down Gitbot..."
bot.close()