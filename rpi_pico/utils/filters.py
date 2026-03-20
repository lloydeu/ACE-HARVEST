class MovingAverage:
    def __init__(self, window_size=10):
        self.window_size = window_size
        self.values = []
    
    def update(self, new_value):
        self.values.append(new_value)
        if len(self.values) > self.window_size:
            self.values.pop(0)
        return sum(self.values) / len(self.values)
    
    def clear(self):
        self.values = []
