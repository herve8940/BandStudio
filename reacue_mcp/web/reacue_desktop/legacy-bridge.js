/* Bind the preserved Studio/prompters to the project that opened the frame. */
(() => {
  const project = document.querySelector('meta[name="reacue-project"]')?.content;
  const original = window.fetch.bind(window);
  window.fetch = (input, options = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, location.href);
    if (url.origin === location.origin && url.pathname.startsWith('/_/')) {
      const headers = new Headers(options.headers || (input instanceof Request ? input.headers : undefined));
      headers.set('X-ReaCue-Project', project || '');
      options = {...options, headers};
    }
    return original(input, options);
  };
})();
