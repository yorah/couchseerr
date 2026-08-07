LOGDEBUG, LOGINFO, LOGWARNING, LOGERROR = 0, 1, 2, 3

_log_calls = []


def log(msg, level=LOGDEBUG):
    _log_calls.append((msg, level))


ENGLISH_NAME, ISO_639_1, ISO_639_2 = 0, 1, 2


def getLanguage(fmt=ENGLISH_NAME, region=False):
    # Honours fmt on purpose: a stub that returns "en" whatever it is asked cannot tell
    # a correct ISO_639_1 call from an ENGLISH_NAME one, which is how "French" reached
    # TMDb unnoticed.
    return {ENGLISH_NAME: "English", ISO_639_1: "en", ISO_639_2: "eng"}.get(fmt, "English")


_builtins = []


def executebuiltin(function, wait=False):
    _builtins.append(function)


#: Window/visibility conditions a test wants getCondVisibility to answer True for.
_cond_visibility = set()


def getCondVisibility(condition):
    return condition in _cond_visibility


_jsonrpc_calls = []
_jsonrpc_responses = {}
_jsonrpc_raw = {}


def executeJSONRPC(request):
    import json as _json

    parsed = _json.loads(request)
    _jsonrpc_calls.append(parsed)
    method = parsed.get("method")
    if method in _jsonrpc_raw:
        # A literal, unencoded string: lets a test hand back a malformed reply that
        # json.dumps could never produce, to exercise the caller's parse-failure path.
        return _jsonrpc_raw[method]
    return _json.dumps(
        {"id": parsed.get("id"), "jsonrpc": "2.0",
         "result": _jsonrpc_responses.get(method, {})}
    )
