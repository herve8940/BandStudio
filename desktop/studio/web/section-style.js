'use strict';
// One musical colour vocabulary for the arrangement and its proposed version.
function sectionStyle(name){
 const value=String(name||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
 const key=/pre.?refrain|pre.?chorus/.test(value)?'prechorus':/post.?refrain|post.?chorus/.test(value)?'postchorus':/refrain|chorus|refrao|estribillo/.test(value)?'chorus':/couplet|verse/.test(value)?'verse':/pont|bridge|puente/.test(value)?'bridge':/break|arret/.test(value)?'break':/solo|instrument|interlude|riff/.test(value)?'instrumental':/outro|coda|final/.test(value)?'outro':'intro';
 const palette={intro:['#99abc5','Intro'],verse:['#b7a0ed','Couplet'],prechorus:['#efc77c','Pré-refrain'],chorus:['#63d5bc','Refrain'],postchorus:['#7bbfdc','Post-refrain'],bridge:['#efa58c','Pont'],break:['#ec9fca','Break'],instrumental:['#8bb8f4','Instrumental'],outro:['#adb8cb','Outro']};
 return {kind:key,color:palette[key][0],label:palette[key][1]};
}
