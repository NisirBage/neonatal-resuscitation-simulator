/**
 * Deterministic SpeechRecognition mock for Playwright E2E tests.
 *
 * Injected via page.addInitScript() before the page loads. The mock
 * replaces window.SpeechRecognition / webkitSpeechRecognition so that
 * the real SR API is never invoked. Tests control recognised speech
 * by calling methods on window.__speechMock from page.evaluate().
 *
 * Export: the raw JS string to inject, so it can be used as:
 *   await page.addInitScript({ content: SPEECH_RECOGNITION_MOCK });
 */

export const SPEECH_RECOGNITION_MOCK = `
(function () {
  var __queue = [];
  var __active = null;

  function makeResults(items) {
    var arr = items.map(function (item) {
      var r = { isFinal: item.isFinal, length: 1 };
      r[0] = { transcript: item.transcript, confidence: item.confidence };
      return r;
    });
    arr.length = items.length;
    return arr;
  }

  function MockSpeechRecognition() {
    this.continuous = false;
    this.interimResults = false;
    this.lang = 'en-US';
    this.maxAlternatives = 1;
    this.onstart = null;
    this.onend = null;
    this.onerror = null;
    this.onresult = null;
    this.onaudiostart = null;
    this.onsoundstart = null;
    this.onspeechstart = null;
    this._aborted = false;
  }

  MockSpeechRecognition.prototype.start = function () {
    var self = this;
    self._aborted = false;
    __active = self;

    if (self.onstart) self.onstart();

    var tryProcess = function () {
      if (self._aborted || __active !== self) return;
      if (__queue.length > 0) {
        var evt = __queue.shift();
        self._fire(evt);
      } else {
        setTimeout(tryProcess, 40);
      }
    };
    setTimeout(tryProcess, 40);
  };

  MockSpeechRecognition.prototype.stop = function () {
    if (__active === this) __active = null;
    var self = this;
    setTimeout(function () { if (self.onend) self.onend(); }, 10);
  };

  MockSpeechRecognition.prototype.abort = function () {
    this._aborted = true;
    if (__active === this) __active = null;
    // abort() must NOT fire onend — matches real Chrome behaviour
  };

  MockSpeechRecognition.prototype._fire = function (evt) {
    var self = this;
    if (evt.type === 'result') {
      var results = makeResults([{ transcript: evt.transcript, confidence: evt.confidence, isFinal: true }]);
      if (self.onresult) self.onresult({ resultIndex: 0, results: results });
      setTimeout(function () { if (self.onend) self.onend(); }, 20);
    } else if (evt.type === 'interim') {
      // Fire interim only — NO isFinal=true. onend fires next, triggering
      // Chrome interim-fallback path in useSpeechRecognition (confidence=0).
      var interimResults = makeResults([{ transcript: evt.transcript, confidence: 0, isFinal: false }]);
      if (self.onresult) self.onresult({ resultIndex: 0, results: interimResults });
      setTimeout(function () { if (self.onend) self.onend(); }, 20);
    } else if (evt.type === 'error') {
      if (self.onerror) self.onerror({ error: evt.code, message: evt.message || '' });
      setTimeout(function () { if (self.onend) self.onend(); }, 20);
    } else if (evt.type === 'low-confidence') {
      var lcResults = makeResults([{ transcript: evt.transcript, confidence: 0.3, isFinal: true }]);
      if (self.onresult) self.onresult({ resultIndex: 0, results: lcResults });
      setTimeout(function () { if (self.onend) self.onend(); }, 20);
    }
  };

  window.SpeechRecognition = MockSpeechRecognition;
  window.webkitSpeechRecognition = MockSpeechRecognition;

  // Control interface — call from page.evaluate() in tests
  window.__speechMock = {
    /** Fires isFinal=true result with the given transcript and confidence. */
    enqueueResult: function (transcript, confidence) {
      __queue.push({ type: 'result', transcript: transcript, confidence: confidence !== undefined ? confidence : 0.95 });
    },
    /** Fires interim only — triggers Chrome interim-fallback (confidence=0) path. */
    enqueueInterim: function (transcript) {
      __queue.push({ type: 'interim', transcript: transcript });
    },
    /** Fires a low-confidence (0.3) final result — triggers retry path. */
    enqueueBackgroundNoise: function (transcript) {
      __queue.push({ type: 'low-confidence', transcript: transcript || 'static' });
    },
    /** Fires onerror with the given code. */
    enqueueError: function (code, message) {
      __queue.push({ type: 'error', code: code, message: message });
    },
    /** Fires the no-speech error code. */
    enqueueNoSpeech: function () {
      __queue.push({ type: 'error', code: 'no-speech' });
    },
    /** Fires network error. */
    enqueueNetworkError: function () {
      __queue.push({ type: 'error', code: 'network' });
    },
    clearQueue: function () {
      __queue = [];
    },
    queueLength: function () {
      return __queue.length;
    }
  };
})();
`;
