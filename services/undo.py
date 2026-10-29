from copy import deepcopy

class History:
    def __init__(self):
        self.past, self.future = [], []
    def push(self, project):
        self.past.append(deepcopy(project))
        self.past = self.past[-100:]
        self.future.clear()
    def undo(self, project):
        if not self.past:
            return project
        self.future.append(deepcopy(project))
        return self.past.pop()
    def redo(self, project):
        if not self.future:
            return project
        self.past.append(deepcopy(project))
        return self.future.pop()
