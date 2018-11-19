import threading
from abc import abstractmethod

class application:
    def __init__(self):
        pass


    def notify(self, user=None):
        t = threading.Thread(target=self.process_data, args=[user])
        t.start()

    @abstractmethod
    def process_data(self, user):
        pass

    def notify_next_move(self, user=None):
        t = threading.Thread(target=self.next, args=[user])
        t.start()

    @abstractmethod
    def next(self, user):
        pass

