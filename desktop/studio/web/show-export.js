'use strict';
(() => {
  const tr = (fr, en) => interfaceLanguage === 'en' ? en : fr;
  const panel = node('article', 'show-export');
  const heading = node('h2');
  const description = node('p');
  const form = node('div', 'export-fields');
  panel.append(heading, description, form);
  function field(parent, label, input) {
    const wrapper = node('label', 'export-field');
    input.setAttribute('aria-label', label);
    wrapper.append(node('span', '', label), input);
    parent.append(wrapper);
    return wrapper;
  }
  function option(value, text) {
    const element = node('option', '', text);
    element.value = value;
    return element;
  }
  function selector(parent, label, values) {
    const input = node('select');
    for (const [value, text] of values) input.append(option(value, text));
    field(parent, label, input);
    return input;
  }

  const scope = selector(form, tr('Morceaux à exporter', 'Songs to export'), []);
  const current = tr('Morceau ouvert', 'Current song');
  const selection = tr('Sélection dans la bibliothèque', 'Library selection');
  const title = node('input');
  title.maxLength = 90;
  const titleField = field(form, tr('Nom du concert', 'Show name'), title);
  const selectionPanel = node('div', 'export-selection');
  const libraryBox = node('div', 'export-song-list');
  const ordered = node('ol', 'export-order');
  const saveList = button(tr('Enregistrer la setlist','Save setlist'), () => {
    const id = scope.value.startsWith('set:') ? scope.value.slice(4) : crypto.randomUUID();
    requestedList = id;
    putSetlist({id, name:title.value.trim(), paths:[...paths]});
  });
  selectionPanel.append(libraryBox, ordered, saveList);
  const consoleSettings = node('div', 'export-fields');
  const layout = selector(consoleSettings, tr('Timecode grandMA3','grandMA3 timecode'), [
    ['both', tr('Concert et par titre','Full show and per song')],
    ['concert', tr('Concert entier','Full show')], ['songs', tr('Par titre','Per song')]]);
  const sound = selector(consoleSettings, tr('Bandes pour la façade','Front-of-house playback'), [
    ['both',tr('Mix stéréo et pistes séparées','Stereo mix and individual tracks')],
    ['mix',tr('Mix stéréo','Stereo mix')],['stems',tr('Pistes séparées','Individual tracks')]]);
  const fps = selector(consoleSettings, tr('Cadence LTC','LTC frame rate'), [
    ['25','25 fps'],['24','24 fps'],['30','30 fps']]);
  const details = node('details');
  details.append(node('summary','',tr('Repère depuis une parole ou un accord du morceau ouvert',
                                      'Mark a lyric or chord in the current song')));
  const annotations = selector(details,tr('Parole ou accord','Lyric or chord'),[]);
  const listenFeedback = node('small');
  listenFeedback.setAttribute('role','status');
  const editFeedback = node('small');
  editFeedback.setAttribute('role','status');
  function listenAt(at) {
    if (!Number.isFinite(at) || state.busy || !state.loaded) return;
    const message = guideDirty || $('notes').value !== (state.project.notes || '') ?
      uiText('Enregistre tes notes et applique tes réglages en cours avant la vérification.') : '';
    listenFeedback.textContent = editFeedback.textContent = message;
    if (message) return;
    const start = Math.max(0, at - 2), end = Math.min(state.duration, at + 2);
    if (end - start <= .05) return;
    const active = studioAudition.current();
    if (active?.start === start && active.end === end) studioAudition.stop();
    else studioAudition.play({start,end}, $('view-regie').hidden ? 'studio' : 'regie');
  }
  const listen = button(tr('Écouter ce passage','Listen to this passage'), () =>
    listenAt(Number(annotations.selectedOptions[0]?.dataset.time)));
  annotations.parentElement.after(listen);
  const markerName = node('input');
  markerName.maxLength = 160;
  field(details,tr('Nom du repère','Marker name'),markerName);
  const addCue = button(tr('Ajouter au morceau','Add to song'), () => {
    const selected = annotations.selectedOptions[0];
    if (!selected || !markerName.value.trim()) return;
    send('cue', {time:Number(selected.dataset.time),name:markerName.value.trim(),announce:false});
  });
  annotations.onchange = () => { markerName.value = annotations.selectedOptions[0]?.dataset.label || ''; updateButtons(); };
  details.append(addCue);
  const mark = button(tr('Poser un repère (M)','Mark at playhead (M)'), markAtPlayhead);
  mark.setAttribute('aria-keyshortcuts','M');
  const timelineAdd = $('newCue');
  timelineAdd.title = mark.textContent;
  timelineAdd.setAttribute('aria-label',mark.textContent);
  timelineAdd.setAttribute('aria-keyshortcuts','M');
  timelineAdd.prepend(node('kbd','cue-key','M'));
  const rundown = node('section','show-rundown');
  const rundownHeading = node('h3','',tr('Repères du morceau ouvert','Current song markers'));
  const rows = node('div','rundown-rows');
  rundown.append(rundownHeading,mark,rows,listenFeedback);
  const cueTools = node('div','cue-edit-tools');
  const preview = button(tr('Écouter ce passage','Listen to this passage'), () => listenAt($('editStart').valueAsNumber));
  const stepLabel = node('small');
  let preciseTime = 0, displayedTime = '';
  function nudge(direction) {
    const input = $('editStart');
    if (!Number.isFinite(input.valueAsNumber)) return;
    if (displayedTime !== input.value) preciseTime = input.valueAsNumber;
    preciseTime = Math.min(state.duration, Math.max(0, preciseTime + direction * (transport.rate || 1) / Number(fps.value)));
    displayedTime = input.value = preciseTime.toFixed(3);
    input.dispatchEvent(new Event('input'));
  }
  cueTools.append(preview,button(tr('−1 image','−1 frame'),()=>nudge(-1)),
    button(tr('+1 image','+1 frame'),()=>nudge(1)),stepLabel,editFeedback);
  $('editStart').closest('.range-inputs').after(cueTools);
  $('editor').addEventListener('close',()=>{displayedTime='';editFeedback.textContent='';});
  function showTimecode(seconds) {
    const rate = Number(fps.value);
    const exact = seconds * rate, low = Math.floor(exact);
    // Match Python's round-to-even used by the timecode export.
    const frame = exact - low === .5 ? low + low % 2 : Math.round(exact);
    const whole = Math.floor(frame / rate);
    return [Math.floor(whole / 3600), Math.floor(whole / 60) % 60, whole % 60, frame % rate]
      .map(n=>String(n).padStart(2,'0')).join(':');
  }
  function drawRundown() {
    rows.replaceChildren();
    const p = state.project;
    if (!state.loaded || !p.cues.length) {
      rows.append(node('small','',tr('Aucun repère dans ce morceau.','This song has no markers.')));
      return;
    }
    const rate = transport.rate || 1;
    const settings = {...guideDefaults,...p.settings}, grid = musicalGrid(p);
    const firstBar = Math.ceil(grid.coordinate(0) / grid.meter - 1e-9) * grid.meter;
    const lead = settings.exportCount ? Math.max(0,-grid.at(firstBar - settings.countBars * grid.meter)) : 0;
    const table = node('table'), head = table.createTHead().insertRow();
    for (const label of [tr('Depuis le GO QLab','From QLab GO'), 'Section',tr('Repère','Marker'),tr('Écoute','Listen')])
      head.append(node('th','',label));
    const body = table.createTBody();
    for (const cue of [...p.cues].sort((a,b)=>a.time-b.time)) {
      const row = body.insertRow();
      row.insertCell().textContent = showTimecode(2 + (lead + cue.time) / rate);
      row.insertCell().textContent = p.sections.find(s=>s.start<=cue.time && cue.time<s.end)?.name || '—';
      const editCue = button(cue.name,()=>openEditor('cue',cue));
      editCue.title = tr('Modifier le repère','Edit marker');
      editCue.disabled = !!state.busy;
      row.insertCell().append(editCue);
      const hear = button(tr('Écouter','Listen'),()=>listenAt(cue.time));
      hear.disabled = !!state.busy;
      row.insertCell().append(hear);
    }
    rows.append(table);
  }
  fps.onchange = () => {stepLabel.textContent = fps.selectedOptions[0].textContent; drawRundown();};
  stepLabel.textContent = fps.selectedOptions[0].textContent;
  const submit = button('',() => {
    const options = {kind,layout:layout.value,sound:sound.value,fps:Number(fps.value)};
    if (scope.value !== 'current') {
      options.paths = [...paths];
      options.name = title.value.trim() || tr('Concert','Show');
      if (scope.value.startsWith('set:')) options.setlist = scope.value.slice(4);
    }
    send('exportShow', options);
  },'primary');
  const reveal = button(tr('Afficher l’export','Show export'),()=>send('showExport'));
  const actions = node('div','export-actions');
  actions.append(submit,reveal);
  panel.append(selectionPanel,consoleSettings,details,rundown,actions);

  let paths = [], kind = '', signature = '', annotationSignature = '', dragIndex = -1, requestedList = '';
  function updateButtons() {
    const multi = scope.value !== 'current';
    submit.disabled = !!state.busy || (multi ? !paths.length || paths.some(p=>!state.library?.some(s=>s.path===p)) : !state.loaded);
    saveList.disabled = !!state.busy || !paths.length || !title.value.trim();
    addCue.disabled = !!state.busy || !state.loaded || !annotations.options.length || !markerName.value.trim();
    listen.disabled = !state.loaded || !!state.busy || !annotations.options.length;
    mark.disabled = !state.loaded || !!state.busy;
    reveal.disabled = !state.lastExport;
  }
  function move(from,to) {
    if (from<0 || from>=paths.length || to<0 || to>=paths.length) return;
    paths.splice(to,0,paths.splice(from,1)[0]);
    drawList();
  }
  function drawList() {
    const library = state.library || [];
    libraryBox.replaceChildren();
    for (const song of library) {
      const check = node('input');
      check.type='checkbox';
      check.checked=paths.includes(song.path);
      check.onchange=()=>{
        if (check.checked) paths.push(song.path);
        else paths=paths.filter(p=>p!==song.path);
        drawList();
      };
      const row=node('label','checkbox');
      row.append(check,node('span','',song.name));
      libraryBox.append(row);
    }
    ordered.replaceChildren();
    paths.forEach((path,index)=>{
      const name = library.find(s=>s.path===path)?.name || tr('Fichier déplacé','Missing file');
      const row = node('li');
      row.draggable=true;
      row.ondragstart=e=>{dragIndex=index;e.dataTransfer.setData('text/plain',String(index));};
      row.ondragover=e=>e.preventDefault();
      row.ondrop=e=>{e.preventDefault();move(dragIndex,index);dragIndex=-1;};
      row.ondragend=()=>{dragIndex=-1;};
      row.append(node('span','',name));
      for (const [symbol,help,action,disabled] of [
        ['↑',tr('Monter','Move up'),()=>move(index,index-1),index===0],
        ['↓',tr('Descendre','Move down'),()=>move(index,index+1),index===paths.length-1],
        ['×',tr('Retirer','Remove'),()=>{paths.splice(index,1);drawList();},false]]) {
        const b=button(symbol,action);
        b.disabled=disabled;
        b.setAttribute('aria-label',help+' · '+name);
        row.append(b);
      }
      ordered.append(row);
    });
    updateButtons();
  }
  function chooseScope() {
    const list=(state.setlists||[]).find(s=>'set:'+s.id===scope.value);
    paths=list ? [...list.paths] : [];
    title.value=list?.name || '';
    titleField.hidden=selectionPanel.hidden=scope.value==='current';
    drawList();
  }
  scope.onchange=chooseScope;
  title.oninput=markerName.oninput=updateButtons;

  function refresh() {
    if (!kind) return;
    const listSignature=JSON.stringify([(state.library||[]).map(s=>[s.path,s.name]),state.setlists]);
    if (listSignature!==signature || requestedList) {
      signature=listSignature;
      const value=scope.value;
      scope.replaceChildren(option('current',current),option('selection',selection));
      for (const list of state.setlists||[]) scope.append(option('set:'+list.id,list.name));
      if (requestedList && (state.setlists||[]).some(s=>s.id===requestedList)) {
        scope.value='set:'+requestedList;
        requestedList='';
        chooseScope();
      } else if ([...scope.options].some(o=>o.value===value)) {
        scope.value=value;drawList();
      } else chooseScope();
    }
    const project=state.project;
    if (kind === 'regie') drawRundown();
    if (annotationSignature!==project.id+'|'+state.revision) {
      const previous = annotationSignature.startsWith(project.id+'|') ? annotations.selectedOptions[0]?.dataset : null;
      const draft = markerName.value;
      annotationSignature=project.id+'|'+state.revision;
      const entries=[...(project.lyrics||[]).flatMap(l=>l.words?.length?l.words:[l]),...(project.chords||[])];
      annotations.replaceChildren();
      for (const entry of entries.sort((a,b)=>a.start-b.start)) {
        const o=option(String(annotations.options.length),time(entry.start,true)+' · '+entry.text);
        o.dataset.time=entry.start;
        o.dataset.label=entry.text;
        annotations.append(o);
      }
      const kept = previous && [...annotations.options].find(o=>o.dataset.time===previous.time && o.dataset.label===previous.label);
      if (kept) annotations.value=kept.value;
      markerName.value=kept ? draft : (entries[0]?.text || '');
    }
    updateButtons();
  }
  document.addEventListener('studio:view-changed',e=>{
    kind=['regie','live'].includes(e.detail)?e.detail:'';
    if (!kind) return;
    const show=kind==='regie';
    heading.textContent=uiText(show?'Régie QLab + grandMA3':'Projet Ableton Live');
    description.textContent=show ?
      tr('Un groupe QLab et une séquence lumière par titre.','One QLab group and one lighting sequence per song.') :
      tr('Un Set Arrangement avec ses médias par morceau. Compatibilité Live 11 et 12 à vérifier en répétition.',
         'One Arrangement Set with its media per song. Check compatibility in Live 11 or 12 during rehearsal.');
    submit.textContent=show?tr('Exporter pour la régie','Export show'):tr('Exporter le projet Live','Export Live Set');
    consoleSettings.hidden=details.hidden=rundown.hidden=!show;
    $('view-'+kind).append(panel);
    refresh();
  });
  let lastRate = transport.rate || 1;
  const priorTransport = renderTransport;
  renderTransport = function() {
    priorTransport();
    if (lastRate !== (transport.rate || 1)) {
      lastRate = transport.rate || 1;
      if (kind === 'regie') drawRundown();
    }
  };
  const previousRender=render;
  render=function(){previousRender();refresh();};
})();
