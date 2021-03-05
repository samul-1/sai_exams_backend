from rest_framework.throttling import UserRateThrottle


class UserSubmissionThrottle(UserRateThrottle):
    scope = "burst"

    def parse_rate(self, rate):
        """
        returns a tuple:  <allowed number of requests>, <period of time in seconds>
        which is fixed to allow 1 request every 30 seconds
        """
        return (1, 30)
