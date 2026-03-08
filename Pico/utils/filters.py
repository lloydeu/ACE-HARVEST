# filters.py

class MovingAverage:
    def __init__(self, size=10):
        """size: Number of samples to keep in the buffer."""
        self.size = size
        self.buffer = []

    def update(self, new_value):
        """Adds a sample and returns the new average."""
        self.buffer.append(new_value)
        
        # Keep the window at the fixed size
        if len(self.buffer) > self.size:
            self.buffer.pop(0)
            
        # Return the Mean
        return sum(self.buffer) / len(self.buffer)

    def clear(self):
        """Reset the filter (Used during a 'Tare' event)."""
        self.buffer = []

    def get_latest(self):
        """Returns the current average without adding a new value."""
        if not self.buffer:
            return 0.0
        return sum(self.buffer) / len(self.buffer)