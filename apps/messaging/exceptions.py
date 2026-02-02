"""
Messaging exceptions.
"""


class MessageError(Exception):
    """Base messaging error."""
    pass


class ChannelError(MessageError):
    """Unknown or unsupported channel."""
    pass


class ProviderError(MessageError):
    """Provider-specific error."""
    pass


class RateLimitError(MessageError):
    """Rate limit exceeded."""
    pass


class QuietHoursError(MessageError):
    """Message blocked due to quiet hours."""
    pass


class RuleViolationError(MessageError):
    """Messaging rule violation."""
    pass


class TemplateError(MessageError):
    """Template-related error."""
    pass


class RecipientError(MessageError):
    """Invalid recipient."""
    pass
