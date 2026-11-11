"use strict";
let diagnosticCount=0;
function reportFrontendError(message,line=0){
 if(diagnosticCount++>=50)return;
 window.webkit?.messageHandlers?.studio?.postMessage({command:'diagnostic',args:{message:String(message).slice(0,2000),line}});
}
window.addEventListener('error',e=>reportFrontendError(e.message,e.lineno));
window.addEventListener('unhandledrejection',e=>reportFrontendError(e.reason?.message||String(e.reason)));
