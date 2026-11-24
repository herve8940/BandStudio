'use strict';

const steps = [...document.querySelectorAll('[data-step]')];
const links = [...document.querySelectorAll('[data-step-link]')];
const previous = document.getElementById('tutorialPrevious');
const next = document.getElementById('tutorialNext');
const statusText = document.getElementById('tutorialStatus');
let current = 0;

function show(index, navigate = false) {
  if (!Number.isInteger(index) || !steps[index]) index = 0;
  current = index;
  steps.forEach((step, i) => { step.hidden = i !== index; });
  links.forEach((link, i) => {
    if (i === index) link.setAttribute('aria-current', 'step');
    else link.removeAttribute('aria-current');
  });
  previous.disabled = index === 0;
  next.disabled = index === steps.length - 1;
  const word = document.documentElement.lang === 'fr' ? 'Étape' : 'Step';
  statusText.textContent = word + ' ' + (index + 1) + ' / ' + steps.length;
  if (navigate) {
    history.pushState(null, '', '#step-' + (index + 1));
    const heading = steps[index].querySelector('h2');
    heading.tabIndex = -1;
    heading.focus({preventScroll: true});
    steps[index].scrollIntoView({block: 'start'});
  }
}

function followHash() {
  const match = /^#step-(\d+)$/.exec(location.hash);
  show(match ? Number(match[1]) - 1 : 0);
}

links.forEach((link, i) => link.addEventListener('click', event => {
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  show(i, true);
}));
previous.addEventListener('click', () => show(current - 1, true));
next.addEventListener('click', () => show(current + 1, true));
window.addEventListener('hashchange', followHash);
followHash();
document.querySelector('.tutorial-controls').hidden = false;
