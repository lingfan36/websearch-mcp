"""Custom exceptions for WebSearch Agent."""


class WebSearchError(Exception):
    """Base exception."""
    pass


class RewriterError(WebSearchError):
    """Rewriter failed."""
    def __init__(self, msg: str, recoverable: bool = True):
        super().__init__(msg)
        self.recoverable = recoverable


class SearchAPIError(WebSearchError):
    """Search API error."""
    def __init__(self, msg: str, status_code: int = 0, recoverable: bool = True):
        super().__init__(msg)
        self.status_code = status_code
        self.recoverable = recoverable


class ExtractorError(WebSearchError):
    """Extractor failed."""
    def __init__(self, msg: str, recoverable: bool = True):
        super().__init__(msg)
        self.recoverable = recoverable


class EvaluatorError(WebSearchError):
    """Evaluator failed."""
    pass


class SynthesizerError(WebSearchError):
    """Synthesizer failed."""
    def __init__(self, msg: str, recoverable: bool = True):
        super().__init__(msg)
        self.recoverable = recoverable


class LLMRateLimitError(WebSearchError):
    """LLM rate limit exceeded."""
    pass


class FetchError(WebSearchError):
    """Fetch failed."""
    pass


class MaxIterationsError(WebSearchError):
    """Max iterations reached."""
    pass
