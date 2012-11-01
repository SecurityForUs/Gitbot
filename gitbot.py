#!/usr/bin/env python

# Typical stuff for multithreaded regex-using bots
import socket
import threading
import time
import re

# Custom classes to aide in development
import github
import bst

# Used for scheduling fetching new Twitter updates
from apscheduler.scheduler import Scheduler

# Used for doing some logging
import logging

class Client(object):
    def __init__(self, chan="balanced", nick="balanced_man", nickpass=None, trigger="gitbot"):
        # Store some stuff and get an instance of the GitHub class
        self.chan = chan
        self.nick = nick
        self.git = github.GitHub(gbot=self)
        self.trigger = trigger
        
        self.send_nickserv_identify = False
        
        if nickpass:
            self.send_nickserv_identify = True
            self.nick_password = nickpass
            
        # Establish a connection to Freenode
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        #self.sock.connect(("irc.freenode.net",6667))
        self.sock.connect(("localhost", 6667))
        
        # Makes reading the socket a lot easier
        self.f = self.sock.makefile()
        
        # Create some locks so we acquire/release thread-unsafe data
        self.in_lock = threading.RLock()
        self.out_lock = threading.RLock()
        
        # Different regexes to test the received line from
        self.regex_numeric = re.compile('^:[\w\.]* (\d*) \w* :')
        self.regex_cmd_no_param = re.compile(':([^!]*)!([^@]*)@([^@ ]*) PRIVMSG (#?[\w\d]*) :!([\w\d]*)\r\n')
        self.regex_trigger_param = re.compile(':([^!]*)!([^@]*)@([^@ ]*) PRIVMSG (#?[\w\d]*) :%s ([\w\d]*) (.*)\r\n' % (self.trigger))
        self.regex_cmd_param = re.compile(':([^!]*)!([^@]*)@([^@ ]*) PRIVMSG (#?[\w\d]*) :!([\w\d]*) (.*)\r\n')
        self.regex_ping = re.compile('^PING ([\w\d:\.]+)\r\n')
        self.regex_notice = re.compile(':([^!]*)!([^@]*)@([^@ ]*) NOTICE ([\w\d]*) :(.*)\r\n')
        self.regex_kick = re.compile(':([^!]*)!([^@]*)@([^@ ]*) KICK (#?[\w\d]*) ([^ ]*) :(.*)\r\n')
        self.regex_join = re.compile(':([^!]*)!([^@]*)@([^@ ]*) JOIN :(#?[\w\d]*)\r\n')
        
        # Buffer holding in/outgoing messages and any commands to be processed
        self.in_msgs = []
        self.out_msgs = []
        self.cmd_msgs = []
        
        # Tuple of "command,function" to handle
        self.cmds = []
        
        # Anything that should be done when a specific nick is seen from server
        self.nick_callbacks = []
        self.event_callbacks = []
        
        # Tells when the bot's running, and when it's joined a channel
        self.running = True
        self.joined = False
        
    def start(self):
        # Debugging information that I should turn into a log
        #self.log.info("Found the following command hooks: %s" % (self.cmds))
        
        # Initalize thread references
        self.incoming_thread = threading.Thread(target=self.incoming_thread, args=(self.f, self.in_lock))
        self.outgoing_thread = threading.Thread(target=self.outgoing_thread, args=(self.sock, self.out_lock))
        self.processing_thread = threading.Thread(target=self.process_messages, args=(self.in_lock, self.out_lock))
        self.command_thread = threading.Thread(target=self.process_commands, args=(self.in_lock,))
        
        #Put the first two message to send into the outgoing queue
        self.out_msgs.append((0, "USER"))
        self.out_msgs.append((0, "NICK"))
        
        # Start all of the threads so they can run
        self.incoming_thread.start()
        self.outgoing_thread.start()
        self.processing_thread.start()
        self.command_thread.start()
        
        # Join the threads to their pool (swim men, swim!)
        self.incoming_thread.join()
        self.outgoing_thread.join()
        self.processing_thread.join()
        self.command_thread.join()
    
    """
    Sends 'msg' to the whole channel
    """
    def chan_msg(self, msg):
        self.sock.send("PRIVMSG #%s :%s\r\n" % (self.chan, msg))
    
    """
    Sends 'msg' to user specified as 'to'
    """
    def user_msg(self, to, msg):
        self.sock.send("PRIVMSG %s :%s\r\n" % (to, msg))
    
    """
    Wrapper to handle the above two methods in one
    """
    def msg(self, msg, to=None):
        if to:
            self.user_msg(to, msg)
        else:
            self.chan_msg(msg)
    
    """
    Send server-speicifc messages to the server
    """
    def server_msg(self, msg):
        self.sock.send("%s\r\n" % (msg))
    
    """
    PONG the ping'ed 'ball' back to the server
    """
    def irc_pong(self, ball):
        self.server_msg("PONG %s" % (ball))
    
    """
    Tell the server the bot wants to join a specific channel
    """
    def irc_join(self):
        #self.log.info("Joining channel %s" % (self.chan))
        self.server_msg("JOIN #%s" % (self.chan))
        self.chan_msg("Hey everyone.  If you're not sure how to use me, just say !help")
        self.joined = True
    
    """
    Set the nick of the bot
    """
    def irc_nick(self):
        self.server_msg("NICK %s" % (self.nick))
    
    """
    Send an annoying USER identifying string.
    """
    def irc_user(self):
        self.server_msg("USER %s %s %s :%s" % (self.nick, self.nick, self.nick, self.nick))
    
    """
    When 'nick' is seen in the server messages, call 'callback'
    """
    def irc_callback_nick(self, nick, callback):
        self.nick_callbacks.append((nick, callback))
    
    """
    Remove the 'callback' from 'nick' (untested)
    """
    def irc_nickcallback_remove(self, nick, callback):
        self.nick_callbacks.remove((nick, callback))
    
    """
    When 'cmd' is sent to the channel, call 'func'
    """
    def register_command(self, cmd, func):
        self.cmds.append((cmd, func))
    
    """
    Processes the command queue
    """
    def process_commands(self, lock):
        # Only process commands while running
        while self.running:
            # Acquire a lock on command messages (temp. freeze of messages being added to queue)
            lock.acquire()
            length = len(self.cmd_msgs)
            lock.release()
            
            # We have messages, so we pass through each one
            while length > 0:
                # Without a lock, possible to cause race condition
                lock.acquire()
                
                # Get the message string itself ([0] - priority)
                m = self.cmd_msgs.pop()[1]
                
                # Update the length
                length = len(self.cmd_msgs)
                lock.release()
                
                # Get the command name
                c = m[4]
                
                for cmd in self.cmds:
                    if cmd[0] == c:
                        #self.log.debug("Running command \"%s\"" % (c))
                        
                        cmd[1](self, m)
                        break
            
            # Always nice to allow workers a little bit of sleep
            time.sleep(0.01)
    
    """
    Stores messages coming in from the server into a buffer to be parsed
    """
    def incoming_thread(self, f, lock):
        while self.running:
            line = f.readline()
            lock.acquire()
            self.in_msgs.append(self.parse_line(line))
            lock.release()
            
            time.sleep(0.01)
    
    """
    Handles messages set to be delievered from bot to server
    """
    def outgoing_thread(self, sock, lock):
        while self.running:
            # Used to give a bit of slack in processing (slight breaks)
            processing_time = 0
            increasing = True
            
            length = 0
            
            lock.acquire()
            
            # Get how many messages are waiting to be handled
            length = len(self.out_msgs)
            
            lock.release()
            
            while length > 0:
                # Sorts outgoing messages based on priority (key = [0] of out_msgs)
                lock.acquire()
                t = sorted(self.out_msgs[::-1], key=lambda k:k[0], reverse=True)
                
                # Get the highest priority first, then reset the list back to the normal method
                # This could possibly be re-written as m = t.pop()[1:] (see below)
                m = t.pop()
                self.out_msgs = t[::-1]
                length = len(self.out_msgs)
                lock.release()
                
                # m[0] - priority of message, m[1...] is where the goodies are at
                m = m[1:]
                
                # Sending a join request, so make it happen
                if m[0] == "JOIN":
                    self.irc_join()
                elif m[0] == "PRIVMSG":
                    # Sending a message to someone/thing
                    m = m[1:]
                    self.msg(m[1], m[0])
                elif m[0] == "NICK":
                    # Setting the nick
                    self.irc_nick()
                elif m[0] == "USER":
                    self.irc_user()
                elif m[0] == "PING":
                    self.irc_pong(m[1])
                elif m[0] == "ALL":
                    # Catchall, basically an echo test (not used)
                    self.msg(m[1])
                
                # If time is increasing, add half a second, otherwise subtract half a second
                # 0 >= processing_time <= 2
                if increasing:
                    processing_time += 0.5
                else:
                    processing_time -= 0.5
                
                if processing_time > 2:
                    increasing = False
                elif processing_time < 0:
                    increasing = True
                    processing_time = 0
                
                time.sleep(processing_time)
            time.sleep(0.01)
    
    """
    Processes incoming messages and handles them accordingly
    """
    def process_messages(self, inlock, outlock):
        while self.running:
            # While we still have messages to handle
            while len(self.in_msgs) > 0:
                inlock.acquire()
                msg = self.in_msgs.pop()
                inlock.release()
                
                # Acquire a outbound lock so data isn't threashed
                outlock.acquire()
                
                # msg = (numeric_value <priority|id>, relevant information (see parse_line()))
                msg = msg[1:]
                
                # Cycle through each nickname in the callbacks array and act on any if need be
                for nick in self.nick_callbacks:
                    if msg[0] != "SKIP" and msg[0] != "NUMERIC" and nick[0] == msg[0].lower():
                        nick[1](self, msg[1])
                
                # Dealing with server-sent messages...
                if msg[0] == "NUMERIC":
                    # It's time to attempt to join the server
                    if msg[1] == "376" or msg[1] == "422":
                        self.out_msgs.append((0, "NICK", self.nick, None))
                        
                        """
                        Used to connect when 'nick' has a password to it.
                        """
                        if self.send_nickserv_identify:
                            self.out_msgs.append((2, "PRIVMSG", "nickserv", "identify %s" % (self.nick_password)))
                        
                        # Join the channel now
                        self.out_msgs.append((0, "JOIN"))
                elif msg[0] == "CMD":
                    self.cmd_msgs.append((0, msg[1:]))
                elif msg[0] == "PING":
                    self.out_msgs.append((0, "PING", msg[1]))
                
                outlock.release()
            time.sleep(0.01)
    
    """
    Wrapper for adding an outbound message to the queue (not used...clean up?)
    """
    def add_outmsg(self, action, params, priority=0):
        self.out_msgs.append(priority, action, params)
    
    """
    Checks the line received against a bunch of regex.
    """
    def parse_line(self, line):
        m = self.regex_ping.match(line)
        if m:
            return (0, "PING", m.group(1))
        
        m = self.regex_numeric.match(line)
        
        if m:
            return (2, "NUMERIC", m.group(1))
        
        m = self.regex_cmd_no_param.match(line)
        
        if m:
            return (2, "CMD", m.group(1), m.group(2), m.group(3), m.group(4), m.group(5), None )
            
        m = self.regex_cmd_param.match(line)
        
        if m:
            return (2, "CMD", m.group(1), m.group(2), m.group(3), m.group(4), m.group(5), m.group(6))
        
        m = self.regex_trigger_param.match(line)
        
        if m:
            return (2, "CMD", m.group(1), m.group(2), m.group(3), m.group(4), m.group(5), m.group(6))
            
        m = self.regex_notice.match(line)
        
        if m:
            return (1, "NOTICE", m.group(1), m.group(2), m.group(3), m.group(4), m.group(5))
            
        return (9999, "SKIP")
    
    """
    Disconnect from the server (the print line is required or else the bot won't disconnect)
    """
    def quit(self):
        print "Quitting"
        self.running = False
        self.sock.close()

"""
Sends some helpful information to whoever requested it
"""
def bot_help(irc, msg):
    irc.user_msg(msg[0], "GitHub Assistant Bot for Balanced Payments")
    irc.user_msg(msg[0], "Written by secforus_ehansen of Security For Us, LLC.  Fork this bot at https://github.com/SecurityForUs/Gitbot")
    irc.user_msg(msg[0], "Issue searching:")
    irc.user_msg(msg[0], "!search <repo> <issue number or keywords>")
    irc.user_msg(msg[0], "!inform <nick> about <repo> <issue number or keywords>")
    irc.user_msg(msg[0], "Label searching:")
    irc.user_msg(msg[0], "Replace search keywords with label:<comma separated list>")
    irc.user_msg(msg[0], "To search by label(s) instead, prepend labels with \"label:\" or \"labels:\"")
    irc.user_msg(msg[0], "Send someone a GitHub link from balanced: !send <user> <repo> [subdirectory (i.e.: issues)]")
    irc.user_msg(msg[0], "List repos: !repos")

def bot_kill(irc, msg):
    print "Called bot_kill"
    irc.quit()

def bot_sendlink(irc, msg):
    args = str(msg[5]).split(" ")
    
    try:
        to = args[0]
        repo = args[1]
        
        if repo in irc.git.get_repos():
            url = "https://www.github.com/balanced/%s" % (irc.git[repo])
        elif repo == "balanced":
            url = "https://www.balancedpayments.com"
            
        try:
            url = "%s/%s" % (url, args[2])
        except IndexError:
            pass
        
        irc.user_msg(to, "%s wants you to check out the following link: %s" % (msg[0], url))
    except:
        irc.user_msg(msg[0], "To send a link to someone: !send <nick> <repo> [subdirectory (i.e.: issues)]")
        
def bot_list_repos(irc, msg):
    irc.user_msg(msg[0], "Repos for https://www.github.com/%s: %s" % (irc.git.acct, ', '.join(irc.git.get_repos())))

def bot_gitlook(irc, msg):
    try:
        args = msg[5]
        
        stype = "s"
        
        if msg[4] == "inform":
            params = str(args).split(" ", 3)
            to = params[0]
            repo = params[2]
            terms = params[3]
        elif msg[4] == "search":
            params = str(args).split(" ", 1)
            to = msg[0]
            repo = params[0]
            terms = params[1]
        
        try:
            terms = int(terms)
            stype = "i"
        except:
            pass
        
        irc.git.issue_lookup(repo=repo, stype=stype, search=terms, from_who=msg[0], to_who=to)
    except IndexError:
        irc.user_msg(msg[0], "If you need help on how to use %s, please say !help" % (irc.nick))
    except KeyError:
        irc.user_msg(msg[0], "For one reason or another one or more arguments went missing.  Please try again.")

def bot_sendapirst(irc, msg):
    args = str(msg[5]).split(" ")

    to = args[0]
    rst = args[1]

    url = "https://github.com/balanced/balanced-api"

    if rst == "errors":
        url = "%s/errors.rst" % (url)
    else:
        url = "%s/resources/%s.rst" % (url, rst)

    irc.user_msg(to, "%s wants you to view an API resource: %s" % (msg[0], url))

irc = Client(chan="test")

irc.register_command("help", bot_help)
# For safety reasons not using this....
#irc.register_command("kill", bot_kill)
irc.register_command("repos", bot_list_repos)
irc.register_command("search", bot_gitlook)
irc.register_command("inform", bot_gitlook)
irc.register_command("send", bot_sendlink)
irc.register_command("rst", bot_sendapirst)

twitter = bst.BalancedStatusTwitter(irc)

config = {'apscheduler.jobstores.file.class': 'apscheduler.jobstores.shelve_store:ShelveJobStore',
          'apscheduler.jobstores.file.path': '/tmp/dbfile'}
sched = Scheduler(config)
sched.start()

# Twitter feed is checked for updates every 30 seconds
"""
Twitter's GetUserTimeline call is rate-limited to 180 calls/hour.  This essentially amounts to:

2x calls in 1 minute = 120 calls/hour (2*60)

To max out the calls/hour, set second to */20 (3x calls/minute = 180 calls/hour)
"""
sched.add_cron_job(twitter.status, month='*', day='*', year='*', hour='*', minute='*', second='*/30')
"""
Nothing more than debugging info being left in case of usefulness in logging...

a = str(sched.get_jobs()[0]).split(":", 2)[2][:-1]
print a.strip()
"""
irc.start()
