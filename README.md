Gitbot
======

IRC bot to interface with GitHub

Requirements
======
Python 2.7 (not tested with any others)
Requests (to send/receive GitHub API calls)

How-To
======
By default, Gitbot connects to Freenode's networks.  To specify different portions:

```python
# Connect to #git on irc.freenode.net
GitBot(chan="git")

# To have the bot be a different name
GitBot(nick="SomeNickBot")

# To have Gitbot listen for a different event
GitBot(cmd_start="mesg_trigger_text here")

# Have Gitbot service a GitHub
GitBot(acct="github_username")
```

By default, if you want to have Gitbot search for issues, there's two choices:

```python
# Issue number
gitbot issue 6

# Topic/subject
gitbot issue flying geese are not turtles
```

To assist against flood control, Gitbot only returns the first result on success.
