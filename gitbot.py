#!/usr/bin/env python

import socket
import requests
import urllib
import json
import time
import twitter
from apscheduler.scheduler import Scheduler

class BalancedStatusTwitter(object):
    def __init__(self, bot):
        fp = open('balance.sfu', 'r')
        data = json.loads(fp.read())
        fp.close()
        
        self.api = twitter.Api(
                          consumer_key='U7mDscdgAz927V333rkbA',
                          consumer_secret=data['twitter']['consumer'],
                          access_token_key='369887502-DxaJqgKNjhISaGKMFsiJE52y1OEeVOQzm9e1rD3i',
                          access_token_secret=data['twitter']['access_token'])
        
        self.bot = bot
        
        self.load()
        
    def status(self):
        statuses = self.api.GetUserTimeline(screen_name="balancedstatus", since_id=self.minid, count=1)
        
        if statuses[0].id > self.minid:
            self.minid = statuses[0].id
            #self.save()
                
        for s in statuses:
            self.bot.send("@balancedstatus at %s: %s" % (s.created_at, s.text))
    
    """
    Figure out why this won't store, or use Redis instead of flat file for saving.
    """
    def save(self):
        try:
            fp = open('twitter.stats', 'w')
            fp.write(str(self.minid))
            fp.close()
        except:
            pass
        
    def load(self):
        try:
            fp = open('twitter.stats', 'r')
            self.minid = fp.read()
            fp.close()
            
            if not self.minid:
                self.minid = 0
        except:
            self.minid = 0
            
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
    def __init__(self, host="irc.freenode.net", port=6667, chan="balanced", nick="balanced-git", nick_pass=None, cmd_start = "gitbot", acct = "balanced"):
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
            return self.repos.keys()
        
        # Get a list of 'user''s repos
        r = self.github("users/:acct:/repos", get_args={'type' : type})
        
        # Turning the repo list into a dictionary, and adding a prefix to the value
        # This makes it possible to work with non-prefixed repos
        repos = {}
        prefix = "balanced-"
        name = ""
        
        # Gitbot was originally written for #balanced
        for repo in r:
            if repo['name'].find(prefix) != -1:
                name = repo['name'].replace(prefix, "")
                repos[name] = prefix
            else:
                name = repo['name']
                repos[name] = ""
                
        self.repos = repos
        
        return repos.keys()
    
    """
    Returns a properly formatted repo name.
    """
    def repo_name(self, id):
        pref = self.repos[id]
        
        return "%s%s" % (pref, id)
    
    """
    Simply checks to see if the user is an admin
    """
    def check_admin(self):
        if not self.admins:
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
        
        # Original way for bot to send GitHub requests (looked down upon now but here for rememberance)
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
                repo = self.repo_name(repo)
                
                try:
                    terms = int(terms)
                    self.issue_lookup(repo, "i", terms)
                except ValueError:
                    self.issue_lookup(repo, "s", terms)
            else:
                self.send("Balanced does not have GitHub repo named balanced-%s" % (repo))
        elif cmd == "tell":
            """
            This command makes Gitbot PM a particular user all the useful links it finds on GitHub.
            """
            
            # Parse who to send it to, the command (non-used), what repo and the search phrase
            who,_,repo,phrase = args.split(" ", 3)
            repo = self.repo_name(repo)
            
            try:
                phrase = int(phrase)
                self.issue_lookup(repo, "i", phrase, to_who=who)
            except ValueError:
                self.issue_lookup(repo, "s",  phrase, to_who=who)
        elif cmd == "hub" and self.check_admin():
            # Changes the GitHub account to work with
            self.setacct(args)
        elif cmd == "list":
            if args == "repo":
                self.send(json.dumps(self.get_repos()))
            elif args == "admins":
                self.send("The following admins are: %s" % (', '.join(self.admins.keys())))
        elif cmd == "help":
            self.send("Balanced Payments IRC bot.  Connects to the balanced GitHub to assist Balanced team.")
            self.send("Commands: list <repo> <issue # or search term>, tell <user> about <repo> <criteria>, list <admins|repo>, help.  To search for issues by label, append criteria with \"labels:\"")
            self.send("Want to improve this bot?  Want to use it for your own channel?  Fork it at https://github.com/SecurityForUs/Gitbot")
        elif cmd == "make":
            if args == "me a sandwich":
                self.send("No")
        elif cmd == "sudo":
            if args == "make me a sandwich":
                self.send("Okay")
        else:
            self.send("I'm sorry but I do not recognize the command \"%s\" with args \"%s\"" % (cmd, args))
    
    """
    Sends 'msg' to the person marked as 'to'.  If 'pm' is true, send it to the channel, otherwise to the server itself.
    """
    def send(self, msg, to=None, pm = True, prefix=None, chan=True):
        # Prefix the message?
        if prefix:
            msg = "%s %s" % (prefix, msg)
        
        # If sending to the channel, make sure we do so, otherwise we're sending it to a user
        # Suggested by zealoushacker
        if chan:
            recip = "#%s" % (self.chan)
        else:
            recip = to
        
        # PM is for everything but server (i.e.: PONG) requests
        if pm:
            self.sock.send("PRIVMSG %s :%s\n" % (recip, msg))
        else:
            self.sock.send("%s\n" % (msg))
    
    # Gets the username of the person who sent the last known message
    def getsender(self):
        return self.msg.split(":", 3)[1].split("!")[0]
        
    """
    Wrote into it's own function to make things simpler for myself.
    
    Also handles label searching (thanks joonas for the idea)
    """
    def issue_lookup(self, repo, stype, search, to_who=None):
        issues = []
            
        if stype is "i":
            tmp = self.github("repos/:acct:/%s/issues/%d" % (repo, search))
            try:
                tmp['user'] = tmp['user']['login']
            except:
                pass
            
            issues.append(tmp)
        else:
            # By default we won't search based on labels
            label_search = False
            
            # However, if such keywords are found, then so be it
            if search.find("label:") != -1 or search.find("labels:") != -1:
                labels = search.split("label:")
                
                # 'label:" wasn't found, so we got 'labels:' instead
                if labels[0] == search:
                    labels = search.split("labels:")[1].split(" ")
                    labels = ','.join(labels)
                else:
                    labels = labels[1]
                    
            label_search = True
            
            if not label_search:
                call = self.legacy_github(repo, search)
                
                try:
                    issues = call['issues']
                except:
                    pass
            else:
                call = self.github("repos/:acct:/%s/issues" % (repo), get_args={'labels' : labels})
                
                try:
                    issues = call['issues']
                except:
                    issues = call
        
        # Get the total amount of issues found by whatever method of searching we used
        res = len(issues)
        
        try:
            if to_who:
                self.send("%s, I'm letting %s know about %d results." % (self.getsender(), to_who, res))
            else:
                to_who = self.getsender()
                self.send("%s, found %d criteria that match your request." % (to_who, res))
                
            i = 1
            
            for issue in issues:
                if label_search:
                    issue['user'] = issue['user']['login']
                    
                self.send("%s created an issue titled \"%s\" that is %s at %s" % (issue['user'], issue['title'], issue['state'], issue['html_url']), to=to_who, prefix="[%d/%d]" % (i, res), chan=False)
                i += 1
                
                # sleep() is used to help control flooding the channel
                time.sleep(2)
        except:
            self.send("%s, unable to find any open issues with the provided search criteria" % (self.getsender()))
    
    """
    Receives data from the IRC server, and then we can parse it!
    """
    def recv(self,debug=False):
        msg = str(self.sock.recv(2048)).strip()
        
        self.msg = msg
        
        lines = msg.split("\n")
        
        for msg in lines:
            if debug:
                print "msg =",msg
            
            if msg.find("PING :") != -1:
                host = msg.split(":")[1]
                self.send("PONG :%s" % (host), pm=False)
            elif msg.find("PRIVMSG #%s :%s" % (self.chan, self.cmd)) != -1:
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
        
bot = GitBot(chan="secforus", nick="sfu%d" % (time.time()))
#bot = GitBot()

tweet = BalancedStatusTwitter(bot)

config = {'apscheduler.jobstores.file.class': 'apscheduler.jobstores.shelve_store:ShelveJobStore',
          'apscheduler.jobstores.file.path': '/tmp/dbfile'}
sched = Scheduler(config)
sched.start()

sched.add_cron_job(tweet.status, month='*', day='*', year='*', hour='*', minute='*', second='*/30')

try:
    while True:
        bot.recv()
except:
    pass

print "Shutting down Gitbot..."
bot.close()
sched.shutdown()