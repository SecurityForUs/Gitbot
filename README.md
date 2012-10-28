Gitbot
======

IRC bot to interface with GitHub

Requirements
======
Python 2.7 (not tested with any others)
- see requirements.txt for more -

Installation
============

    pip install -r requirements.txt

How-To
======
By default, Gitbot connects to Freenode's networks.  To specify different portions:

```python
# Connect to #git on irc.freenode.net
Client(chan="git")

# To have the bot be a different name
Client(nick="SomeNickBot")

# If the nick has a nickserv password
Client(nick="SomeNickBot", nick_pass="p$ass")

# To have Gitbot listen for a different event
Client(trigger="pulled")
```

Gitbot now allows searching by issue #, keywords or labels:
```python
# Issue number
!search python 6

# Keywords
!search api ach international

# Labels
!search api labels:ach,approved
```
