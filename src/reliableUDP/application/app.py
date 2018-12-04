import threading
from abc import abstractmethod

class app:
    def __init__(self):
        pass


    def notify_process_data(self, user=None):
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

    @abstractmethod
    def remove_user(self, user):
        pass

    @abstractmethod
    def notify_close(self):
        pass
