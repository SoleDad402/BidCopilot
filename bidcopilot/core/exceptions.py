"""Exception hierarchy."""


class BidCopilotError(Exception):
    pass


class ConfigError(BidCopilotError):
    pass


class AdapterError(BidCopilotError):
    pass


class AuthenticationError(AdapterError):
    pass


class CaptchaError(AdapterError):
    pass


class RateLimitError(AdapterError):
    pass


class FormFillError(BidCopilotError):
    pass


class ResumeUnavailableError(BidCopilotError):
    pass


class LLMError(BidCopilotError):
    pass
