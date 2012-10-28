"""
GitHub interface to their APIs (v2 & v3).
"""
import json
import requests
import urllib
import time

class GitHub(object):
    def __init__(self, owner="balanced", gbot=None):
        self.acct = owner
        self.repos = None
        self.get_repos(user=owner)
        self.bot = gbot
        
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
        
        #print "github url =",url
        
        r = requests.get(url)
        return json.loads(r.content)
        
    """
    Handles GitHub v2 API (legacy).  Only service for this is searching by keyword for issues by default.
    """
    def legacy_github(self, repo, terms, state = "open"):
        return self.github("legacy/issues/search/:acct:/%s/%s/%s" % (repo, state, terms))
    
    """
    Returns a properly formatted repo name.
    """
    def repo_name(self, id):
        pref = self.repos[id]
        
        return "%s%s" % (pref, id)
    
    """
    Wrote into it's own function to make things simpler for myself.
    
    Also handles label searching (thanks joonas for the idea)
    """
    def issue_lookup(self, repo, stype, search, from_who = None, to_who=None):
        issues = []
        
        # By default we won't search based on labels
        label_search = False
        
        repo = self.repo_name(repo)
        
        if stype is "i":
            tmp = self.github("repos/:acct:/%s/issues/%d" % (repo, search))
            try:
                tmp['user'] = tmp['user']['login']
            except:
                pass
            
            issues.append(tmp)
        else:
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
            i = 1
                
            for issue in issues:
                if label_search:
                    issue['user'] = issue['user']['login']
                        
                self.send("%s created an issue titled \"%s\" that is %s at %s" % (issue['user'], issue['title'], issue['state'], issue['html_url']), to_who)
                i += 1
                    
                    # sleep() is used to help control flooding the channel
                time.sleep(2)
        except:
            self.send("%s, unable to find any open issues with the provided search criteria" % (from_who), to_who)
        
    def send(self, msg, to):
        self.bot.out_msgs.append((2, "PRIVMSG", to, msg))