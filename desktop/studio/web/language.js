'use strict';

const interfaceLanguage = (window.bandStudioLanguage || document.documentElement.lang) === 'en' ? 'en' : 'fr';
document.documentElement.lang = interfaceLanguage;

function uiText(source) {
  return interfaceLanguage === 'en' && Object.prototype.hasOwnProperty.call(bandStudioEnglish, source) ? bandStudioEnglish[source] : source;
}

function uiFormat(parts, ...values) {
  const translated = interfaceLanguage === 'en' && bandStudioEnglish[parts.join('{}')];
  if (translated) return translated.replace(/\{(\d+)\}/g, (_, index) => String(values[Number(index)]));
  return parts.reduce((result, part, index) => result + (index ? values[index - 1] : '') + part, '');
}

// Called only on application-authored markup, before any project data is rendered.
function localizeStatic(root) {
  if (interfaceLanguage !== 'en') return;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let node;
  while ((node = walker.nextNode())) {
    if (node.parentElement?.closest('[translate="no"],script,style')) continue;
    const source = node.nodeValue.trim();
    if (source && Object.prototype.hasOwnProperty.call(bandStudioEnglish, source)) {
      node.nodeValue = node.nodeValue.replace(source, () => uiText(source));
    }
  }
  for (const element of root.querySelectorAll('[title],[alt],[aria-label],[placeholder]')) {
    for (const attribute of ['title','alt','aria-label','placeholder']) {
      if (element.hasAttribute(attribute)) element.setAttribute(attribute, uiText(element.getAttribute(attribute)));
    }
  }
}

function uiMarkup(markup) {
  if (interfaceLanguage !== 'en') return markup;
  const template = document.createElement('template');
  template.innerHTML = markup;
  localizeStatic(template.content);
  return template.innerHTML;
}

localizeStatic(document.body);
const languageControl = document.getElementById('interfaceLanguage');
languageControl.value = interfaceLanguage;
const languageHint = document.getElementById('interfaceLanguageHint');
languageHint.textContent = interfaceLanguage === 'en' ? 'Language changes take effect after restarting BandStudio.' : 'Le changement de langue prend effet au prochain démarrage de BandStudio.';
languageControl.addEventListener('change', () => send('uiLanguage', {language: languageControl.value}));
