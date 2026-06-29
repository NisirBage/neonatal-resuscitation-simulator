/**
 * Deterministic SpeechSynthesis mock for Playwright E2E tests.
 *
 * Replaces window.speechSynthesis so TTS calls complete immediately
 * (firing utterance.onend synchronously after a short delay). This
 * prevents tests from hanging while waiting for real TTS audio.
 *
 * Also stubs window.SpeechSynthesisUtterance so it can be constructed
 * without browser TTS support.
 */

export const SPEECH_SYNTHESIS_MOCK = `
(function () {
  var __speaking = false;
  var __queue = [];

  function processQueue() {
    if (__queue.length === 0) { __speaking = false; return; }
    __speaking = true;
    var utt = __queue.shift();
    // Fire onstart immediately so the watchdog timer in useSpeechSynthesis is cleared
    try { if (utt.onstart) utt.onstart({}); } catch (e) {}
    // Fire onend quickly so the voice loop proceeds
    setTimeout(function () {
      __speaking = false;
      try { if (utt.onend) utt.onend({}); } catch (e) {}
      processQueue();
    }, 30);
  }

  var mockSynthesis = {
    get speaking() { return __speaking; },
    get paused() { return false; },
    get pending() { return __queue.length > 0; },
    speak: function (utt) {
      __queue.push(utt);
      if (!__speaking) processQueue();
    },
    cancel: function () {
      __queue = [];
      __speaking = false;
    },
    pause: function () {},
    resume: function () {},
    getVoices: function () { return []; },
    addEventListener: function () {},
    removeEventListener: function () {},
    dispatchEvent: function () { return true; },
  };

  // window.speechSynthesis is read-only in Chrome — must use Object.defineProperty
  try {
    Object.defineProperty(window, 'speechSynthesis', {
      configurable: true,
      writable: true,
      value: mockSynthesis,
    });
  } catch (e) {
    // Fallback: try direct assignment (may be silently ignored)
    window.speechSynthesis = mockSynthesis;
  }
})();
`;
