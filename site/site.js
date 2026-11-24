'use strict';

const choices = [...document.querySelectorAll('[data-view]')];
const panels = [...document.querySelectorAll('[data-panel]')];

function showView(index) {
  if (!panels[index]) return;
  for (const [i, panel] of panels.entries()) {
    panel.hidden = i !== index;
    if (i === index) choices[i].setAttribute('aria-current', 'true');
    else choices[i].removeAttribute('aria-current');
  }
}

function followHash() {
  const match = /^#view-([0-2])$/.exec(location.hash);
  if (match) showView(Number(match[1]));
}

if (panels.length && panels.length === choices.length) {
  showView(0);
  followHash();
  for (const link of choices) {
    link.addEventListener('click', event => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      showView(Number(link.dataset.view));
      history.replaceState(null, '', link.hash);
    });
  }
  window.addEventListener('hashchange', followHash);
}
