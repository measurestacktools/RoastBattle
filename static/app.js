/* ROAST BATTLE frontend — vanilla JS, XSS-safe (textContent only). */
(function () {
  "use strict";

  var state = {
    target: "",
    style: "savage",
    round: 0,
    busy: false,
    playerTotal: 0,
    aiTotal: 0,
    winner: "",
    funnyVerdict: "",
    lastVerdict: ""
  };

  function $(id) { return document.getElementById(id); }

  var screens = {
    landing: $("screen-landing"),
    battle: $("screen-battle"),
    result: $("screen-result")
  };
  var roundBanner = $("round-banner");
  var redirectNotice = $("redirect-notice");
  var battleTarget = $("battle-target");
  var battleStyle = $("battle-style");
  var aiRoastText = $("ai-roast-text");
  var playerLastText = $("player-last-text");
  var verdictLine = $("verdict-line");
  var scoreChips = $("score-chips");
  var scoreYou = $("score-you");
  var scoreAi = $("score-ai");
  var funCaption = $("fun-caption");
  var reactionRow = $("reaction-row");
  var targetInput = $("target-input");
  var comebackInput = $("comeback-input");
  var startBtn = $("start-btn");
  var sendBtn = $("send-btn");
  var quitBtn = $("quit-btn");
  var landingError = $("landing-error");
  var battleError = $("battle-error");
  var resultError = $("result-error");
  var startLoading = $("start-loading");
  var battleLoading = $("battle-loading");
  var resultLoading = $("result-loading");
  var pips = Array.prototype.slice.call(document.querySelectorAll("#round-pips .pip"));
  var statusPill = $("api-status-pill");
  var modal = $("settings-modal");
  var keyInput = $("key-input");
  var saveKeyBtn = $("save-key-btn");
  var removeKeyBtn = $("remove-key-btn");
  var settingsError = $("settings-error");
  var settingsStatus = $("settings-status");
  var toastWrap = $("toast-wrap");

  var REACT_STARTERS = {
    funny: "LOL okay that was actually funny, but ",
    worse: "Oh yeah? I can take way worse than that. ",
    harder: "Is that all you've got? Watch this: "
  };

  function showScreen(name) {
    Object.keys(screens).forEach(function (k) {
      screens[k].classList.toggle("active", k === name);
    });
    window.scrollTo(0, 0);
  }

  function showError(el, msg) {
    el.textContent = msg;
    el.hidden = false;
  }

  function hideError(el) {
    el.textContent = "";
    el.hidden = true;
  }

  function toast(msg) {
    var div = document.createElement("div");
    div.className = "toast";
    div.textContent = msg;
    toastWrap.appendChild(div);
    setTimeout(function () {
      if (div.parentNode) div.parentNode.removeChild(div);
    }, 3500);
  }

  function friendlyFetchError() {
    return "Could not reach the battle server. Check your connection and try again.";
  }

  function api(path, options) {
    var opts = options || {};
    opts.headers = { "Content-Type": "application/json" };
    return fetch(path, opts).then(
      function (res) {
        return res.json().then(
          function (data) { return { status: res.status, okHttp: res.ok, data: data }; },
          function () { throw new Error(friendlyFetchError()); }
        );
      },
      function () { throw new Error(friendlyFetchError()); }
    );
  }

  function setPips(round) {
    pips.forEach(function (pip) {
      var n = parseInt(pip.getAttribute("data-pip"), 10);
      pip.classList.toggle("on", n === round);
      pip.classList.toggle("done", n < round);
    });
  }

  function setBanner(round) {
    if (round === 1) roundBanner.textContent = "ROUND 1";
    else if (round === 2) roundBanner.textContent = "ROUND 2";
    else roundBanner.textContent = "🔥 FINAL ROUND — NO MERCY MODE";
    // retrigger bounce
    roundBanner.style.animation = "none";
    void roundBanner.offsetWidth;
    roundBanner.style.animation = "";
  }

  function refreshStatus() {
    statusPill.textContent = "CHECKING…";
    statusPill.className = "status-pill";
    settingsStatus.textContent = "Status: checking…";
    api("/api/status", { method: "GET" }).then(function (r) {
      var d = r.data || {};
      if (r.okHttp && d.ok) {
        var label = d.configured ? "● READY" : "○ NO KEY";
        statusPill.textContent = label;
        statusPill.className = "status-pill " + (d.configured ? "ok" : "bad");
        var model = d.model ? " (" + d.model + ")" : "";
        var src = d.source ? " [" + d.source + "]" : "";
        settingsStatus.textContent = "Status: " + (d.message || (d.configured ? "ready" : "no key")) + model + src;
      } else {
        statusPill.textContent = "○ OFFLINE";
        statusPill.className = "status-pill bad";
        settingsStatus.textContent = "Status: server not reachable. Start the backend and try again.";
      }
    }).catch(function () {
      statusPill.textContent = "○ OFFLINE";
      statusPill.className = "status-pill bad";
      settingsStatus.textContent = "Status: server not reachable. Start the backend and try again.";
    });
  }

  function doStart(target, style) {
    if (state.busy) return;
    hideError(landingError);
    hideError(resultError);
    var t = (target || "").trim();
    if (!t) {
      showError(landingError, "Tell us what to roast first — pick a chip or type your own. 🎯");
      targetInput.focus();
      return;
    }
    state.busy = true;
    startBtn.disabled = true;
    startLoading.hidden = false;
    if (resultLoading) resultLoading.hidden = false;

    api("/api/start", { method: "POST", body: JSON.stringify({ target: t, style: style }) })
      .then(function (r) {
        var d = r.data || {};
        if (d.ok) {
          state.target = d.target || t;
          state.style = d.style || style;
          state.round = 1;
          battleTarget.textContent = state.target;
          battleStyle.textContent = state.style;
          aiRoastText.textContent = d.roast || "The AI choked… how embarrassing.";
          playerLastText.textContent = "Your move, champ. Cook it back.";
          playerLastText.className = "roast-text dim";
          verdictLine.hidden = true;
          scoreChips.hidden = true;
          funCaption.hidden = true;
          reactionRow.style.display = "";
          if (d.redirected && d.notice) {
            redirectNotice.textContent = d.notice;
            redirectNotice.hidden = false;
          } else {
            redirectNotice.textContent = "";
            redirectNotice.hidden = true;
          }
          comebackInput.value = "";
          hideError(battleError);
          battleLoading.hidden = true;
          setBanner(1);
          setPips(1);
          showScreen("battle");
          comebackInput.focus();
        } else {
          showError(landingError, d.error || "The arena gates are stuck. Try again in a moment. 🔥");
          if (!screens.result.classList.contains("active")) showScreen("landing");
          else showError(resultError, d.error || "The arena gates are stuck. Try again in a moment. 🔥");
        }
      })
      .catch(function (err) {
        var msg = (err && err.message) || friendlyFetchError();
        if (screens.result.classList.contains("active")) showError(resultError, msg);
        else showError(landingError, msg);
      })
      .then(function () {
        state.busy = false;
        startBtn.disabled = false;
        startLoading.hidden = true;
        if (resultLoading) resultLoading.hidden = true;
        var againBtn = $("again-btn");
        if (againBtn) againBtn.disabled = false;
      });
  }

  function doComeback() {
    if (state.busy) return;
    hideError(battleError);
    var text = comebackInput.value.trim();
    if (!text) {
      showError(battleError, "Empty comebacks get booed off stage — type something first. 🎤");
      comebackInput.focus();
      return;
    }
    state.busy = true;
    sendBtn.disabled = true;
    battleLoading.hidden = false;

    api("/api/comeback", { method: "POST", body: JSON.stringify({ text: text }) })
      .then(function (r) {
        var d = r.data || {};
        if (d.ok && d.round === 2) {
          playerLastText.textContent = text;
          playerLastText.className = "roast-text";
          aiRoastText.textContent = d.roast || "…";
          verdictLine.textContent = "🎤 Judge: " + (d.verdict || "spicy round!");
          verdictLine.hidden = false;
          scoreYou.textContent = String(d.player_score != null ? d.player_score : 0);
          scoreAi.textContent = String(d.ai_score != null ? d.ai_score : 0);
          scoreChips.hidden = false;
          funCaption.hidden = false;
          state.round = 2;
          setBanner(2);
          setPips(2);
          reactionRow.style.display = "none";
          comebackInput.value = "";
          comebackInput.focus();
        } else if (d.ok && d.done) {
          playerLastText.textContent = text;
          playerLastText.className = "roast-text";
          state.round = 3;
          setPips(3);
          showResult(d);
        } else {
          showError(battleError, d.error || "The judges dropped their scorecards. Try sending that again. 🎤");
        }
      })
      .catch(function (err) {
        showError(battleError, (err && err.message) || friendlyFetchError());
      })
      .then(function () {
        state.busy = false;
        sendBtn.disabled = false;
        battleLoading.hidden = true;
      });
  }

  function countUp(el, barEl, to, max) {
    var target = Math.max(0, Math.min(100, Number(to) || 0));
    var start = null;
    var dur = 1200;
    function frame(ts) {
      if (!start) start = ts;
      var p = Math.min(1, (ts - start) / dur);
      var val = Math.round(target * p);
      el.textContent = String(val);
      if (barEl) barEl.style.width = Math.round((val / (max || 100)) * 100) + "%";
      if (p < 1) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  function showResult(d) {
    state.playerTotal = d.player_total != null ? d.player_total : 0;
    state.aiTotal = d.ai_total != null ? d.ai_total : 0;
    state.winner = d.winner || "";
    state.funnyVerdict = d.funny_verdict || d.verdict || "What a battle!";
    state.lastVerdict = d.verdict || "";

    var banner = $("winner-banner");
    var w = state.winner.toLowerCase();
    banner.className = "winner-banner";
    if (w.indexOf("player") !== -1 || w.indexOf("you") !== -1 || w.indexOf("human") !== -1) {
      banner.textContent = "🏆 YOU WIN!";
      banner.classList.add("you");
    } else if (w.indexOf("ai") !== -1 || w.indexOf("robot") !== -1 || w.indexOf("machine") !== -1) {
      banner.textContent = "🤖 AI WINS!";
      banner.classList.add("ai");
    } else {
      banner.textContent = "🤝 DRAW!";
    }

    $("funny-verdict").textContent = state.funnyVerdict;
    var lv = $("last-verdict");
    lv.textContent = state.lastVerdict && state.lastVerdict !== state.funnyVerdict
      ? "Final round judge: " + state.lastVerdict
      : "";
    lv.style.display = lv.textContent ? "" : "none";

    setBanner(3);
    showScreen("result");
    var fp = $("final-player");
    var fa = $("final-ai");
    fp.textContent = "0";
    fa.textContent = "0";
    $("final-player-bar").style.width = "0";
    $("final-ai-bar").style.width = "0";
    countUp(fp, $("final-player-bar"), state.playerTotal, 100);
    countUp(fa, $("final-ai-bar"), state.aiTotal, 100);
  }

  function doRestartThen(fn) {
    api("/api/restart", { method: "POST", body: JSON.stringify({}) })
      .then(function () { fn(); })
      .catch(function () { fn(); });
  }

  function shareText() {
    var w = $("winner-banner").textContent;
    return (
      "🔥 ROAST BATTLE RESULT 🔥\n" +
      "Target: " + state.target + " (" + state.style + ")\n" +
      "YOU: " + state.playerTotal + "/100 vs AI: " + state.aiTotal + "/100\n" +
      w + "\n" +
      "Verdict: " + state.funnyVerdict
    );
  }

  /* ---- wiring ---- */

  document.querySelectorAll("#example-chips .chip").forEach(function (chip) {
    chip.addEventListener("click", function () {
      targetInput.value = chip.getAttribute("data-target") || "";
      targetInput.focus();
    });
  });

  document.querySelectorAll("#style-grid .style-card").forEach(function (card) {
    card.addEventListener("click", function () {
      document.querySelectorAll("#style-grid .style-card").forEach(function (c) {
        c.classList.remove("selected");
        c.setAttribute("aria-checked", "false");
      });
      card.classList.add("selected");
      card.setAttribute("aria-checked", "true");
      state.style = card.getAttribute("data-style") || "savage";
    });
  });

  startBtn.addEventListener("click", function () { doStart(targetInput.value, state.style); });
  targetInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter") doStart(targetInput.value, state.style);
  });

  sendBtn.addEventListener("click", doComeback);
  comebackInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter") doComeback();
  });

  document.querySelectorAll(".react-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var kind = btn.getAttribute("data-react");
      var starter = REACT_STARTERS[kind] || "";
      if (!comebackInput.value.trim()) comebackInput.value = starter;
      comebackInput.focus();
      var len = comebackInput.value.length;
      try { comebackInput.setSelectionRange(len, len); } catch (e) { /* noop */ }
    });
  });

  quitBtn.addEventListener("click", function () {
    doRestartThen(function () {
      state.round = 0;
      setPips(0);
      showScreen("landing");
    });
  });

  $("again-btn").addEventListener("click", function () {
    hideError(resultError);
    this.disabled = true;
    var self = this;
    doRestartThen(function () { doStart(state.target, state.style); self.disabled = false; });
  });

  $("new-btn").addEventListener("click", function () {
    hideError(resultError);
    doRestartThen(function () {
      state.round = 0;
      setPips(0);
      showScreen("landing");
      targetInput.focus();
    });
  });

  $("copy-btn").addEventListener("click", function () {
    var txt = shareText();
    function done() { toast("Result copied — go flex it. 📋🔥"); }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(txt).then(done, function () {
        fallbackCopy(txt);
        done();
      });
    } else {
      fallbackCopy(txt);
      done();
    }
  });

  function fallbackCopy(txt) {
    var ta = document.createElement("textarea");
    ta.value = txt;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); } catch (e) { /* noop */ }
    document.body.removeChild(ta);
  }

  /* settings modal */
  function openModal() {
    hideError(settingsError);
    modal.hidden = false;
    refreshStatus();
    keyInput.focus();
  }
  function closeModal() {
    modal.hidden = true;
    keyInput.value = "";
    hideError(settingsError);
  }
  $("open-settings").addEventListener("click", openModal);
  $("close-settings").addEventListener("click", closeModal);
  modal.addEventListener("click", function (e) {
    if (e.target === modal) closeModal();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !modal.hidden) closeModal();
  });

  saveKeyBtn.addEventListener("click", saveKey);
  keyInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter") saveKey();
  });

  function saveKey() {
    hideError(settingsError);
    var key = keyInput.value.trim();
    if (!key) {
      showError(settingsError, "Paste a key first — the arena needs fuel. 🔑");
      return;
    }
    saveKeyBtn.disabled = true;
    api("/api/key", { method: "POST", body: JSON.stringify({ key: key }) })
      .then(function (r) {
        var d = r.data || {};
        if (d.ok) {
          keyInput.value = "";
          toast(d.message || "Key saved. Let the roasting begin. 🔥");
          refreshStatus();
        } else {
          showError(settingsError, d.error || d.message || "That key did not work. Double-check and try again. 🔑");
        }
      })
      .catch(function (err) {
        showError(settingsError, (err && err.message) || friendlyFetchError());
      })
      .then(function () { saveKeyBtn.disabled = false; });
  }

  removeKeyBtn.addEventListener("click", function () {
    hideError(settingsError);
    removeKeyBtn.disabled = true;
    api("/api/key", { method: "DELETE" })
      .then(function (r) {
        var d = r.data || {};
        keyInput.value = "";
        toast(d.message || "Key removed.");
        refreshStatus();
      })
      .catch(function (err) {
        showError(settingsError, (err && err.message) || friendlyFetchError());
      })
      .then(function () { removeKeyBtn.disabled = false; });
  });

  setPips(0);
  refreshStatus();
})();
