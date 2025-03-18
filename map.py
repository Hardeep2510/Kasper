class ConfinedMap:
    
    def __init__(self,maxsize=100):
        super().__init__()
        self.maxsize=maxsize

    def __setitem__(self,key,value):
        if len(self)==self._maxsize:
            raise RuntimeError('This map is currently full.')
        super().__setitem__(key,value)

    def qsize(self):
        return len(self)
    
    @property
    def maxsize(self):
        return self._maxsize
    
    def is_full(self):
        return len(self)>=self._maxsize
    
    

