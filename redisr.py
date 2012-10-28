try:
    import redis
except:
    import sys
    print "Redis-py is not installed."
    sys.exit(1)

class rcheck(object):
    def __init__(self, re):
        self.f = re
    
    def __get__(self, instance, owner):
        def wrapper(*args, **kwargs):
            if instance.r is not None:
                return self.f(instance, *args, **kwargs)
            else:
                return False
        return wrapper

class Redisr(object):
    """
    Initializes Redisr() helper class by establishing a connection to redis.
    """
    def __init__(self, host="localhost", port=6379):
        self.r = redis.StrictRedis(host=host,port=port,db=0)
        
        """
        If the connection wasn't made, ping() will raise this exception:
        
        redis.exceptions.ConnectionError: Error 111 connecting <host>:<port>. Connection refused.
        """
        try:
            self.r.ping()
        except:
            self.r = None
    
    """
    Checks if the connection is valid.
    """
    @rcheck
    def is_valid(self):
        return True
    
    """
    Saves 'name' containing 'val' into the redis server.
    """
    @rcheck
    def save(self, name, val):
        return self.r.set(name,val)
    
    """
    Fetches the value of 'name' from redis
    """
    @rcheck
    def load(self, name):
        return self.r.get(name)
    
    @rcheck
    def write(self, name, val):
        return self.save(name, val)
    
    @rcheck
    def read(self, name):
        return self.load(name)
    
    @rcheck
    def __getitem__(self, index):
        return self.load(index)