"use strict";
(() => {
  let promptEvent = null;
  let installedInSession = false;
  const button = document.getElementById("installBtn");
  const dialog = document.getElementById("installDialog");
  const action = document.getElementById("installAction");
  const status = document.getElementById("installStatus");
  const standalone = window.matchMedia("(display-mode: standalone)");
  function sync() {
    const installed = installedInSession || standalone.matches || navigator.standalone === true;
    button.textContent = installed ? "앱 사용 중" : "앱 받기";
    action.hidden = !promptEvent || installed;
  }
  window.addEventListener("beforeinstallprompt", event => {
    event.preventDefault();
    promptEvent = event;
    sync();
  });
  window.addEventListener("appinstalled", () => {
    installedInSession = true;
    promptEvent = null;
    status.textContent = "설치되었습니다. 홈 화면에서 Job Monitor를 열어 주세요.";
    sync();
  });
  standalone.addEventListener("change", sync);
  button.addEventListener("click", () => { sync(); dialog.showModal(); });
  document.getElementById("installClose").addEventListener("click", () => dialog.close());
  action.addEventListener("click", async () => {
    const pending = promptEvent;
    if (!pending) return;
    promptEvent = null;
    sync();
    try {
      await pending.prompt();
      const choice = await pending.userChoice;
      status.textContent = choice.outcome === "accepted"
        ? "설치 요청을 보냈습니다. 브라우저의 완료 안내를 확인해 주세요."
        : "설치를 취소했습니다. 브라우저 메뉴에서도 설치할 수 있습니다.";
    } catch (_) {
      status.textContent = "아래 브라우저 메뉴 안내에 따라 설치해 주세요.";
    }
  });
  function connectivity() {
    const el = document.getElementById("offlineNotice");
    el.hidden = navigator.onLine;
    el.textContent = "오프라인 · 마지막으로 저장된 국내 공고입니다. 원문 확인과 개인페이지 열기는 인터넷 연결이 필요합니다.";
  }
  window.addEventListener("online", connectivity);
  window.addEventListener("offline", connectivity);
  connectivity(); sync();
  if ("serviceWorker" in navigator && location.protocol.startsWith("http")) {
    navigator.serviceWorker.register("./sw.js").catch(() => {
      status.textContent = "오프라인 저장을 사용할 수 없습니다. 홈 화면 추가는 브라우저 메뉴를 확인해 주세요.";
    });
  }
})();
