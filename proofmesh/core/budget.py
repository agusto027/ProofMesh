class BudgetExceeded(RuntimeError):
    pass


class TokenBudget:
    def __init__(self, limit: int):
        self.limit = limit
        self.used = 0

    def charge(self, amount: int):
        if self.used + amount > self.limit:
            raise BudgetExceeded(f"Run token budget exhausted ({self.used}/{self.limit}).")
        self.used += amount
