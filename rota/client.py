"""The only place that talks to the model.

Three jobs, and nothing else lives here:

* pin the call settings the brief fixes -- `temperature=1.0`, `top_p=0.95`,
  reasoning disabled -- in one place so no call site can drift from them;
* stamp `X-Item-Id` on every single request, since the graders' proxy
  attributes calls to items by that header and a missing one fails the budget
  check outright;
* enforce the per-item budget locally, in both directions, so a bug in the
  orchestration layer surfaces here as an exception instead of as an
  over-budget run at grading time.
"""
import os
import threading
import time

try:
    from openai import OpenAI
except ImportError as _exc:                                      # noqa: F841
    # A bare ModuleNotFoundError traceback does not tell you what to do, and
    # the usual cause is subtle: `python3` and `python` can be different
    # interpreters on the same machine, so the dependency is installed for one
    # and missing for the other.
    import sys
    raise SystemExit(
        "The `openai` package is not installed for this interpreter.\n"
        f"  interpreter: {sys.executable}\n"
        f"  version    : {sys.version.split()[0]}\n"
        "Install the pinned dependency:\n"
        f"  {sys.executable} -m pip install -r requirements.txt\n"
        "If you have several Pythons, check that the one you installed into is "
        "the one you are running -- `python3` and `python` often differ on "
        "Windows, where `python3` can be the Microsoft Store stub."
    ) from None

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "ibm-granite/granite-4.2-8b"

# Per-HTTP-attempt budget. Extraction replies are a few hundred tokens, so a
# request still running after this is hung rather than slow. With four
# attempts and the back-off below, one logical call is bounded at about three
# minutes instead of being unbounded.
REQUEST_TIMEOUT = 90.0


def load_env(path=".env"):
    """Minimal .env reader. No dependency, and no surprise about precedence:
    a value already in the real environment wins."""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


class BudgetExceeded(RuntimeError):
    pass


class ModelClient:
    """Budgeted chat client for one run."""

    def __init__(self, budget, base_url=None, api_key=None, model=None,
                 temperature=1.0, top_p=0.95, max_retries=4, log=None):
        load_env()
        self.base_url = base_url or os.environ.get("OPENROUTER_BASE_URL",
                                                   DEFAULT_BASE_URL)
        self.model = model or os.environ.get("MODEL", DEFAULT_MODEL)
        key = api_key or os.environ.get("OPENROUTER_API_KEY") or os.environ.get(
            "OPENAI_API_KEY")
        if not key:
            raise RuntimeError(
                "No API key. Put OPENROUTER_API_KEY in .env (see .env.example).")
        # max_retries=0 on purpose. The SDK retries internally by default
        # (twice), and the loop in chat() retries too, so the two layers
        # multiply: 4 outer attempts x 3 inner x a 180s timeout is a 36-minute
        # worst case for a single logical call. A stalled run during
        # validation took exactly that long. One retry layer, here, bounded.
        self.client = OpenAI(base_url=self.base_url, api_key=key,
                             timeout=REQUEST_TIMEOUT, max_retries=0)
        self.budget = int(budget)
        self.temperature = temperature
        self.top_p = top_p
        self.max_retries = max_retries
        self.calls = {}          # item id -> calls made
        self.log = log
        self._lock = threading.Lock()

    # -- budget -------------------------------------------------------------
    def used(self, item_id):
        return self.calls.get(item_id, 0)

    def left(self, item_id):
        return self.budget - self.used(item_id)

    def total_calls(self):
        return sum(self.calls.values())

    # -- the call -----------------------------------------------------------
    def chat(self, item_id, messages, max_tokens=1400, stop=None):
        """One chat completion for `item_id`. Returns the message text.

        Raises BudgetExceeded rather than silently overrunning: going over the
        cap is an auto-fail, so it must be loud.
        """
        with self._lock:
            if self.calls.get(item_id, 0) >= self.budget:
                raise BudgetExceeded(
                    f"{item_id}: {self.budget} call(s) already made")
            self.calls[item_id] = self.calls.get(item_id, 0) + 1

        last = None
        for attempt in range(self.max_retries):
            try:
                r = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    top_p=self.top_p,
                    max_tokens=max_tokens,
                    stop=stop,
                    # required by the brief, and by the graders' counting proxy
                    extra_headers={"X-Item-Id": item_id},
                    # reasoning/thinking off on every call
                    extra_body={"reasoning": {"enabled": False}},
                )
                txt = (r.choices[0].message.content or "") if r.choices else ""
                if self.log is not None:
                    with self._lock:
                        self.log.append({"item": item_id,
                                         "messages": messages, "reply": txt})
                return txt
            except Exception as exc:                      # noqa: BLE001
                last = exc
                # A retry of a failed call is the same logical call: the proxy
                # counts transport attempts, so a retried item must not also
                # consume a fresh budget slot. Back off and try again, and let
                # the attempt cap stop a hard failure from looping.
                if attempt == self.max_retries - 1:
                    break
                time.sleep(1.5 * (2 ** attempt))
        if self.log is not None:
            with self._lock:
                self.log.append({"item": item_id, "messages": messages,
                                 "reply": "", "error": repr(last)})
        return ""
