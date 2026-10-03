"""A keyword/value command grammar providing validation and tab completion."""

from __future__ import annotations

from enum import Enum

from slice_and_dice.command_param import CommandParam
from slice_and_dice.constants import EXPRESSION_CHARS
from slice_and_dice.parsed_command import ParamValue, ParamValues, ParsedCommand


class _State(Enum):
    """States of the parser while scanning tokens left to right."""

    INIT = "init"  # nothing parsed yet
    KEYWORD_PENDING = "keyword-pending"  # a prefix of a keyword was typed
    KEYWORD_DONE = "keyword-done"  # a keyword was typed, its value is expected
    OPTION_PENDING = "option-pending"  # a prefix of a value was typed
    OPTION_DONE = "option-done"  # a value was typed; a value or keyword may follow


class CommandGrammar:
    """Grammar of a command made of ``keyword value [value ...]`` groups.

    For example, ``select`` is declared with one parameter per aggregate
    function, each taking up to five numeric dimensions, so that
    ``select median fbu dcu perc95 speed`` parses into
    ``{"median": ["fbu", "dcu"], "perc95": "speed"}``.

    The same parser drives both validation (when the command runs) and
    completion (when the user presses Tab), so the two never disagree.

    Args:
        name: The command's name, as typed by the user.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self.params: dict[str, CommandParam] = {}

    def add_param(self, param: CommandParam) -> None:
        """Declare a keyword parameter."""
        self.params[param.keyword] = param

    def get_param(self, keyword: str) -> CommandParam:
        """Return the declaration of ``keyword``.

        Raises:
            KeyError: If the keyword was never declared.
        """
        return self.params[keyword]

    def keywords(self) -> list[str]:
        """Return the active keywords, in declaration order."""
        return [keyword for keyword, param in self.params.items() if param.is_active]

    @staticmethod
    def tokenize(line: str, skip_first: bool = True) -> list[str]:
        """Split a line into tokens, optionally dropping the command name."""
        tokens = line.split()
        return tokens[1:] if skip_first else tokens

    # ------------------------------------------------------------------ #
    # Parsing
    # ------------------------------------------------------------------ #

    def parse(self, line: str, skip_first: bool) -> ParsedCommand:
        """Parse ``line`` and work out what may follow it.

        Args:
            line: The text typed so far.
            skip_first: Whether ``line`` starts with the command name.

        Returns:
            The parsed parameters, any errors, and the completions for the
            last (possibly partial) token.
        """
        out = ParsedCommand()
        keywords = self.keywords()
        trailing_space = line.endswith(" ")
        tokens = self.tokenize(line, skip_first)
        if not tokens:
            out.completions = keywords if trailing_space else []
            self._check_required_keywords(keywords, out)
            return out

        state = _State.INIT
        param: CommandParam | None = None
        options: list[str] = []
        value_count = 0
        last = ""
        for token in tokens:
            if state in (_State.KEYWORD_PENDING, _State.OPTION_PENDING):
                # A partial word is only acceptable as the very last token.
                kind = "keyword" if state is _State.KEYWORD_PENDING else "parameter"
                out.append_error(f"error found in command {kind}: {last}")
                return out
            last = token

            if state in (_State.INIT, _State.OPTION_DONE):
                if token in keywords:
                    out.params[token] = None
                    keywords.remove(token)
                    param = self.get_param(token)
                    options = list(param.options)
                    value_count = 0
                    state = _State.KEYWORD_DONE if param.max_vals > 0 else _State.OPTION_DONE
                    continue
                if any(keyword.startswith(token) for keyword in keywords):
                    state = _State.KEYWORD_PENDING
                    continue
                if param is not None and (
                    not param.options or any(option.startswith(token) for option in options)
                ):
                    # Another value for the keyword that is still open.
                    state = _State.KEYWORD_DONE
                else:
                    out.append_error(f"error found in command keyword: {token}")
                    return out

            if state is _State.KEYWORD_DONE:
                assert param is not None
                if token in options or not param.options or _is_expression(token):
                    out.append_value(param.keyword, _convert(token))
                    if token in options:
                        options.remove(token)
                    state = _State.OPTION_DONE
                    value_count += 1
                    if value_count >= param.max_vals:
                        param, options, value_count = None, [], 0
                elif any(option.startswith(token) for option in param.options):
                    state = _State.OPTION_PENDING
                else:
                    out.append_error(f"error found in command parameter: {token}")
                    return out

        self._check_required_keywords(keywords, out)
        self._check_required_values(out)

        if state in (_State.KEYWORD_DONE, _State.OPTION_DONE) and not trailing_space:
            # The last word is complete; the user has to type a space first.
            return out

        if state in (_State.INIT, _State.OPTION_DONE):
            leftover = options if param is not None and value_count < param.max_vals else []
            out.completions = keywords + leftover
        elif state is _State.KEYWORD_PENDING:
            out.completions = [keyword for keyword in keywords if keyword.startswith(last)]
        elif state is _State.KEYWORD_DONE:
            out.completions = list(options)
        elif state is _State.OPTION_PENDING:
            out.completions = [option for option in options if option.startswith(last)]
        return out

    def complete(self, line: str) -> list[str]:
        """Return completions for a line that starts with the command name."""
        return self.parse(line, skip_first=True).completions

    def validate(self, args: str) -> tuple[dict[str, ParamValues], str]:
        """Parse the arguments of a command about to run.

        Args:
            args: The command line without the command name.

        Returns:
            The parsed parameters and an error message (empty when valid).
        """
        parsed = self.parse(args, skip_first=False)
        return parsed.params, parsed.error

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _check_required_keywords(self, missing: list[str], out: ParsedCommand) -> None:
        for keyword in missing:
            if self.get_param(keyword).required:
                out.append_error(f"missing a required parameter: {keyword}")

    def _check_required_values(self, out: ParsedCommand) -> None:
        for keyword in out.params:
            if out.value_count(keyword) < self.get_param(keyword).min_vals:
                out.append_error(f"missing a value for keyword: {keyword}")


def _is_expression(token: str) -> bool:
    """Whether a token is an arithmetic expression, which bypasses the option list."""
    return any(char in token for char in EXPRESSION_CHARS)


def _convert(token: str) -> ParamValue:
    """Convert purely numeric tokens to integers."""
    return int(token) if token.isdigit() else token
