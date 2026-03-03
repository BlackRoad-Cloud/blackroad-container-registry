"""Tests for the Ollama router."""
import pytest
from unittest.mock import MagicMock, patch

from ollama_router import (
    OLLAMA_ALIASES,
    DEFAULT_MODEL,
    handle_message,
    parse_mentions,
    route_to_ollama,
    should_route_to_ollama,
    strip_mentions,
)


class TestParseMentions:
    def test_single_alias(self):
        assert parse_mentions("@ollama what is Python?") == ["ollama"]

    def test_multiple_aliases(self):
        result = parse_mentions("@copilot and @ollama help")
        assert result == ["copilot", "ollama"]

    def test_case_insensitive(self):
        assert parse_mentions("@Copilot help") == ["copilot"]

    def test_no_mentions(self):
        assert parse_mentions("plain text with no at-sign") == []

    def test_unrecognised_mention_returned(self):
        result = parse_mentions("@someoneelse do something")
        assert result == ["someoneelse"]


class TestShouldRouteToOllama:
    @pytest.mark.parametrize("alias", list(OLLAMA_ALIASES))
    def test_all_aliases_route(self, alias):
        assert should_route_to_ollama(f"@{alias} tell me a joke") is True

    def test_uppercase_alias_routes(self):
        assert should_route_to_ollama("@Copilot explain recursion") is True

    def test_blackboxprogramming_alias_routes(self):
        assert should_route_to_ollama("@blackboxprogramming help") is True

    def test_lucidia_alias_routes(self):
        assert should_route_to_ollama("@lucidia what's the weather?") is True

    def test_unrecognised_alias_does_not_route(self):
        assert should_route_to_ollama("@openai answer this") is False

    def test_no_alias_does_not_route(self):
        assert should_route_to_ollama("just a normal message") is False


class TestStripMentions:
    def test_strips_single_mention(self):
        assert strip_mentions("@ollama tell me about containers") == "tell me about containers"

    def test_strips_multiple_mentions(self):
        assert strip_mentions("@copilot @lucidia explain this") == "explain this"

    def test_no_mentions_unchanged(self):
        assert strip_mentions("plain text") == "plain text"


class TestRouteToOllama:
    def _mock_response(self, status_code=200, json_data=None):
        mock = MagicMock()
        mock.status_code = status_code
        mock.json.return_value = json_data or {"response": "hello"}
        mock.text = str(json_data)
        return mock

    def test_successful_request(self):
        expected = {"response": "hello from ollama", "done": True}
        with patch("ollama_router.requests.post") as mock_post:
            mock_post.return_value = self._mock_response(200, expected)
            result = route_to_ollama("hello", model="llama3", host="http://localhost:11434")
        assert result == expected
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs[0][0] == "http://localhost:11434/api/generate"
        assert call_kwargs[1]["json"]["prompt"] == "hello"
        assert call_kwargs[1]["json"]["model"] == "llama3"
        assert call_kwargs[1]["json"]["stream"] is False

    def test_non_200_raises_value_error(self):
        with patch("ollama_router.requests.post") as mock_post:
            mock_post.return_value = self._mock_response(500)
            with pytest.raises(ValueError, match="HTTP 500"):
                route_to_ollama("hello")

    def test_host_trailing_slash_normalised(self):
        with patch("ollama_router.requests.post") as mock_post:
            mock_post.return_value = self._mock_response(200, {"response": "ok"})
            route_to_ollama("hi", host="http://localhost:11434/")
        url = mock_post.call_args[0][0]
        assert url == "http://localhost:11434/api/generate"

    def test_network_error_propagates(self):
        import requests as req_lib
        with patch("ollama_router.requests.post", side_effect=req_lib.ConnectionError("refused")):
            with pytest.raises(req_lib.ConnectionError):
                route_to_ollama("hello")


class TestHandleMessage:
    def _mock_ollama(self, response_text="ok"):
        mock = MagicMock()
        mock.status_code = 200
        mock.json.return_value = {"response": response_text, "done": True}
        return mock

    def test_recognised_alias_calls_ollama(self):
        with patch("ollama_router.requests.post") as mock_post:
            mock_post.return_value = self._mock_ollama("container info")
            result = handle_message("@ollama what is a container?")
        assert result is not None
        assert result["response"] == "container info"
        prompt_sent = mock_post.call_args[1]["json"]["prompt"]
        assert prompt_sent == "what is a container?"

    def test_unrecognised_alias_returns_none(self):
        result = handle_message("@openai answer this")
        assert result is None

    def test_no_alias_returns_none(self):
        result = handle_message("plain message")
        assert result is None

    def test_default_model_used(self):
        with patch("ollama_router.requests.post") as mock_post:
            mock_post.return_value = self._mock_ollama()
            handle_message("@copilot explain async/await")
        assert mock_post.call_args[1]["json"]["model"] == DEFAULT_MODEL

    def test_custom_model_forwarded(self):
        with patch("ollama_router.requests.post") as mock_post:
            mock_post.return_value = self._mock_ollama()
            handle_message("@ollama explain Python", model="mistral")
        assert mock_post.call_args[1]["json"]["model"] == "mistral"

    def test_custom_host_forwarded(self):
        with patch("ollama_router.requests.post") as mock_post:
            mock_post.return_value = self._mock_ollama()
            handle_message("@ollama hi", host="http://192.168.1.10:11434")
        url = mock_post.call_args[0][0]
        assert url.startswith("http://192.168.1.10:11434")

    @pytest.mark.parametrize("alias", list(OLLAMA_ALIASES))
    def test_every_alias_routed(self, alias):
        with patch("ollama_router.requests.post") as mock_post:
            mock_post.return_value = self._mock_ollama()
            result = handle_message(f"@{alias} hello")
        assert result is not None
