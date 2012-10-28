"""
Checks @balancedstatus for new updates.
"""
import json
import twitter
import redisr

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
        self.minid = 0
        
        self.r = redisr.Redisr()
        self.load()
        
    def status(self):
        # if() statement in place to circumvent some issues regarding race conditions
        # (non-thread threatening...just annoying)
        if self.bot.joined:
            statuses = self.api.GetUserTimeline(screen_name="balancedstatus", since_id=self.minid, count=1)
            
            if statuses[0].id > self.minid:
                self.minid = statuses[0].id
                self.save()
                    
            for s in statuses:
                self.bot.chan_msg("@balancedstatus at %s: %s" % (s.created_at, s.text))
        
    def save(self):
        self.r.save('bst_minid', self.minid)
        
    def load(self):
        try:
            self.minid = int(self.r['bst_minid'])
        except:
            pass