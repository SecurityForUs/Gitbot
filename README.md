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

# Labels (label: can also be used)
# If searching more than 1 label at the same time, must be comma-separated list
!search api labels:ach,approved
```
GitBot also allows sending GitHub links to someone:
```python
!send <nick> <repo> [subdirectory]

# To send someone to balanced-api
!send someone api

# To send someone to balanced-python's issues
!send someone python issues
```
This will send <nick> a PM with the full GitHub link.
